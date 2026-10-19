"""Store uploaded source files without changing the review database. A bundle is one PDF, or a folder of page images
that share a bundle number."""
import logging
import os
import re
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image
from fastapi import HTTPException, Request
from backend.db import models
from backend import scans
from filelock import FileLock

from backend.common import IMAGES, ROOT, settings

MAX_BYTES = 500 * 1024 * 1024
log = logging.getLogger("uploads")


def archive_sources(db):
    """The archive's PDFs this app knows, as <item number>/<file id>_<name>.pdf: the Prest survey's and those added to a series."""
    return [*scans.ARCHIVE_PDFS, *(pdf for (pdf,) in db.query(models.ArchiveItem.pdf).filter(models.ArchiveItem.pdf.is_not(None)))]


def check_bundle_number(db, data, bundle, filename):
    """A bundle number cannot be reused for a different uploaded source; more page images may join an image bundle."""
    for existing in db.query(models.Bundle):
        number = Path(existing.source_pdf.replace("\\", "/")).parent.name
        if number == bundle or existing.bundle_id == bundle:
            raise HTTPException(409, f"Item number {bundle} is already in use. Choose a different item number.")
    folder = data / bundle
    if folder.exists():
        kinds = [path.suffix.lower() for path in folder.iterdir()] if folder.is_dir() else [None]
        image = Path(filename).suffix.lower() in IMAGES
        if kinds and not (image and all(kind in IMAGES for kind in kinds)):
            raise HTTPException(409, f"Item number {bundle} already has uploaded files. Choose a different item number.")
    for source in archive_sources(db):
        path = Path(source)
        # Allow downloading the exact registered source, not a new bundle with its number.
        if path.parent.name == bundle and path.name.casefold() != filename.casefold():
            raise HTTPException(409, f"Item number {bundle} belongs to an archive PDF. Choose a different item number.")


def check_pdf_identity(db, data, filename, bundle):
    """PDF stems are bundle IDs and output folder names, and Windows folder names ignore case."""
    stem = Path(filename).stem.casefold()
    existing = next((b for b in db.query(models.Bundle) if b.bundle_id.casefold() == stem), None)
    if existing:
        number = Path(existing.source_pdf.replace("\\", "/")).parent.name
        raise HTTPException(409, f"This PDF is already loaded in item {number}. It has not been uploaded.")
    for path in data.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".pdf" and path.stem.casefold() == stem:
            raise HTTPException(409, f"This PDF already exists in item {path.parent.name}. It has not been uploaded.")
    for source in archive_sources(db):
        path = Path(source)
        if path.stem.casefold() == stem and path.parent.name != bundle:
            raise HTTPException(409, f"This PDF belongs to archive item {path.parent.name}. Use that item number.")


async def upload_bundle(request: Request, bundle: str, filename: str, db):
    """Stream one file to a temporary path, validate it, then publish without overwrite."""
    if not re.fullmatch(r"[0-9]{1,30}", bundle):
        raise HTTPException(400, "Item number must contain 1–30 digits.")
    # Characters Windows can't store in a name; it also drops a trailing dot or space.
    if not filename or len(filename) > 200 or re.search(r'[<>:"/\\|?*\x00-\x1f]', filename) or filename[-1] in ". ":
        raise HTTPException(400, "Invalid filename.")
    suffix = Path(filename).suffix.lower()
    if suffix != ".pdf" and suffix not in IMAGES:
        raise HTTPException(400, "Choose a PDF, JPG or PNG file.")
    data = (ROOT / settings()["DATA"]).resolve()
    if suffix == ".pdf":
        check_pdf_identity(db, data, filename, bundle)
    folder = data / bundle
    if folder.is_symlink():
        raise HTTPException(400, "Invalid item directory.")
    check_bundle_number(db, data, bundle, filename)
    # Page IDs are page image names, so an image is named after its bundle to keep them unique.
    stem = Path(filename).stem if suffix == ".pdf" else f"{bundle}_{Path(filename).stem}"
    destination = folder / (stem + suffix)
    staging = data / ".uploads"
    staging.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=staging, suffix=".upload", delete=False) as stream:
            temporary = Path(stream.name)
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "Files must be 500 MB or smaller.")
                stream.write(chunk)
        if not size:
            raise HTTPException(400, "The file is empty.")
        try:
            if suffix == ".pdf":
                # Opened from memory: on Windows a PDF that fails to open from a path stays locked.
                with pymupdf.open(stream=temporary.read_bytes(), filetype="pdf") as document:
                    if not document.is_pdf or document.needs_pass or document.page_count == 0:
                        raise ValueError("Unreadable PDF")
            else:
                with Image.open(temporary) as image:
                    expected = "PNG" if suffix == ".png" else "JPEG"
                    if image.format != expected:
                        raise ValueError("Image format does not match extension")
                    image.verify()
        except Exception as error:
            raise HTTPException(400, "The file is damaged, password-protected or does not match its extension.") from error
        try:
            with FileLock(str(staging / "upload.lock")):
                check_bundle_number(db, data, bundle, filename)
                if suffix == ".pdf":
                    check_pdf_identity(db, data, filename, bundle)
                folder.mkdir(parents=True, exist_ok=True)
                os.link(temporary, destination)
        except FileExistsError:
            raise HTTPException(409, "A file with this name already exists in this item. Rename it before uploading.")
        return {"filename": destination.name, "bundle": bundle, "size": size}
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:  # a virus scanner can still hold a new file open; the upload's result stands
                log.warning("could not remove %s", temporary)
