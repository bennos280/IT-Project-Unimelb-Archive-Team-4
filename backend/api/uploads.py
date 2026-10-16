"""Store uploaded source files without changing the review database."""
import os
import re
import tempfile
from pathlib import Path

import fitz
from PIL import Image
from fastapi import HTTPException, Request
from backend.db import models
from backend import scans
from filelock import FileLock

from backend.common import ROOT, settings

MAX_BYTES = 250 * 1024 * 1024


def check_bundle_number(db, data, bundle, filename):
    """A bundle number cannot be reused for a different uploaded source."""
    for existing in db.query(models.Bundle):
        number = Path(existing.source_pdf.replace("\\", "/")).parent.name
        if number == bundle or existing.bundle_id == bundle:
            raise HTTPException(409, f"Bundle number {bundle} is already in use. Choose a different bundle number.")
    folder = data / bundle
    if folder.exists() and (not folder.is_dir() or any(
            path.suffix.lower() != ".upload" for path in folder.iterdir())):
        raise HTTPException(409, f"Bundle number {bundle} already has uploaded files. Choose a different bundle number.")
    for source in scans.ARCHIVE_PDFS:
        path = Path(source)
        # Allow downloading the exact registered source, not a new bundle with its number.
        if path.parent.name == bundle and path.name != filename:
            raise HTTPException(409, f"Bundle number {bundle} belongs to an archive PDF. Choose a different bundle number.")


def check_pdf_identity(db, data, filename, bundle):
    """PDF stems are bundle IDs throughout discovery and processing."""
    stem = Path(filename).stem
    existing = db.get(models.Bundle, stem)
    if existing:
        number = Path(existing.source_pdf.replace("\\", "/")).parent.name
        raise HTTPException(409, f"This PDF is already loaded in bundle {number}. It has not been uploaded.")
    for path in data.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".pdf" and path.stem == stem:
            raise HTTPException(409, f"This PDF already exists in bundle {path.parent.name}. It has not been uploaded.")
    for source in scans.ARCHIVE_PDFS:
        path = Path(source)
        if path.stem == stem and path.parent.name != bundle:
            raise HTTPException(409, f"This PDF belongs to archive bundle {path.parent.name}. Use that bundle number.")


async def upload_bundle(request: Request, bundle: str, filename: str, db):
    """Stream one file to a temporary path, validate it, then publish without overwrite."""
    if not re.fullmatch(r"[0-9]{1,30}", bundle):
        raise HTTPException(400, "Bundle number must contain 1–30 digits.")
    if (not filename or len(filename) > 200 or filename in {".", ".."}
            or any(c in filename for c in '/\\') or any(ord(c) < 32 for c in filename)):
        raise HTTPException(400, "Invalid filename.")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(400, "Choose a PDF, JPG or PNG file.")
    data = (ROOT / settings()["DATA"]).resolve()
    if suffix == ".pdf":
        check_pdf_identity(db, data, filename, bundle)
    folder = data / bundle
    if folder.is_symlink():
        raise HTTPException(400, "Invalid bundle directory.")
    check_bundle_number(db, data, bundle, filename)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / (Path(filename).stem + suffix)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, suffix=".upload", delete=False) as stream:
            temporary = Path(stream.name)
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "Files must be 250 MB or smaller.")
                stream.write(chunk)
        if not size:
            raise HTTPException(400, "The file is empty.")
        try:
            if suffix == ".pdf":
                with fitz.open(temporary, filetype="pdf") as document:
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
            with FileLock(str(data / ".upload.lock")):
                check_bundle_number(db, data, bundle, filename)
                if suffix == ".pdf":
                    check_pdf_identity(db, data, filename, bundle)
                os.link(temporary, destination)
        except FileExistsError:
            raise HTTPException(409, "A file with this name already exists in this bundle. Rename it before uploading.")
        return {"filename": destination.name, "bundle": bundle, "size": size}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
