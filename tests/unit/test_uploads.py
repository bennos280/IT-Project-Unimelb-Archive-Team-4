"""Duplicate PDF identities must not relabel existing bundles; page images make up a bundle of their own."""
import io

import pymupdf
import pytest
from PIL import Image
from backend.api import main, uploads
from backend.db import models

@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "settings", lambda: {"DATA": str(tmp_path)})
    monkeypatch.setattr(main, "settings", lambda: {"DATA": str(tmp_path)})
    return tmp_path

@pytest.fixture
def pdf():
    with pymupdf.open() as document:
        document.new_page()
        return document.tobytes()

def send(client, pdf, bundle="1", filename="A.pdf", collection=1):
    return client.post("/bundles/upload", params={"bundle": bundle, "filename": filename, "collection": collection}, content=pdf)

def add_archive_pdf(db, pdf):
    """An archive item of series 1 whose PDF is <item number>/<file name>."""
    node = int(pdf.split("/")[0])
    db.add(models.ArchiveItem(node=node, collection_id=1, identifier=f"UMA-ITE-{node}", title=f"Item {node}", pdf=pdf))
    db.commit()

def png():
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(out, "PNG")
    return out.getvalue()

def test_loaded_pdf_cannot_be_uploaded_under_another_bundle(client, db, storage, pdf):
    db.add(models.Bundle(bundle_id="A", source_pdf="data/216412/A.pdf", collection_id=1))
    db.commit()
    response = send(client, pdf)
    assert response.status_code == 409
    assert "216412" in response.json()["detail"]
    assert not (storage / "1/A.pdf").exists()
    db.expire_all()
    assert db.get(models.Bundle, "A").source_pdf == "data/216412/A.pdf"
    assert db.query(models.Bundle).count() == 1

def test_local_pdf_identity_is_unique_across_folders(client, storage, pdf):
    assert send(client, pdf, "216412").status_code == 201
    assert send(client, pdf).status_code == 409
    assert (storage / "216412/A.pdf").read_bytes() == pdf
    assert not (storage / "1/A.pdf").exists()

def test_archive_pdf_requires_original_bundle_number(client, db, storage, pdf):
    add_archive_pdf(db, "216412/A.pdf")
    assert send(client, pdf).status_code == 409
    assert send(client, pdf, "216412").status_code == 201

@pytest.mark.parametrize("existing_kind", ["database", "local", "archive"])
def test_different_pdf_cannot_reuse_bundle_number(client, db, storage, pdf, existing_kind):
    if existing_kind == "database":
        db.add(models.Bundle(bundle_id="B", source_pdf="data/216412/B.pdf", collection_id=1))
        db.commit()
    elif existing_kind == "local":
        (storage / "216412").mkdir()
        (storage / "216412/B.pdf").write_bytes(pdf)
    else:
        add_archive_pdf(db, "216412/B.pdf")
    response = send(client, pdf, "216412")
    assert response.status_code == 409
    assert "216412" in response.json()["detail"]
    assert not (storage / "216412/A.pdf").exists()
    if existing_kind == "local":
        assert (storage / "216412/B.pdf").read_bytes() == pdf


def test_new_bundle_number_accepts_upload(client, storage, pdf):
    assert send(client, pdf, "999999").status_code == 201
    assert (storage / "999999/A.pdf").read_bytes() == pdf


def test_page_images_make_one_bundle_named_after_it(client, storage, pdf):
    assert send(client, png(), "900", "p2.png").status_code == 201
    assert send(client, png(), "900", "p1.png").status_code == 201
    assert sorted(path.name for path in (storage / "900").iterdir()) == ["900_p1.png", "900_p2.png"]
    assert send(client, png(), "900", "p1.png").status_code == 409
    assert send(client, pdf, "900").status_code == 409
    listed = [b for b in client.get("/bundles").json() if b["name"] == "900"]
    assert [b["bundle"] for b in listed] == ["900"]

def test_an_image_cannot_join_a_pdf_bundle(client, storage, pdf):
    assert send(client, pdf, "901").status_code == 201
    assert send(client, png(), "901", "p1.png").status_code == 409
    assert sorted(path.name for path in (storage / "901").iterdir()) == ["A.pdf"]

def test_a_damaged_pdf_is_refused_and_leaves_nothing_behind(client, storage):
    response = send(client, b"%PDF-1.4 not really" * 50, "902")
    assert response.status_code == 400
    assert "damaged" in response.json()["detail"]
    assert not (storage / "902").exists()
    assert not list(storage.rglob("*.upload"))

def test_a_file_over_the_limit_is_refused_and_leaves_nothing_behind(client, storage, pdf, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_BYTES", len(pdf) - 1)
    assert send(client, pdf, "903").status_code == 413
    assert not (storage / "903").exists()
    assert not list(storage.rglob("*.upload"))

@pytest.mark.parametrize("filename", ["what?.pdf", "a:b.pdf", "a|b.pdf", 'a"b.pdf', "A.pdf.", "A.pdf "])
def test_names_windows_cannot_store_are_refused(client, storage, pdf, filename):
    assert send(client, pdf, "904", filename).status_code == 400
    assert not (storage / "904").exists()

def test_pdf_names_that_differ_only_by_case_are_the_same_bundle(client, db, storage, pdf):
    assert send(client, pdf, "905").status_code == 201
    assert send(client, pdf, "906", "a.pdf").status_code == 409
    db.add(models.Bundle(bundle_id="Loaded", source_pdf="data/216412/Loaded.pdf", collection_id=1))
    db.commit()
    assert send(client, pdf, "907", "LOADED.pdf").status_code == 409
    add_archive_pdf(db, "216413/Archived.pdf")
    assert send(client, pdf, "908", "archived.pdf").status_code == 409
    assert send(client, pdf, "216413", "archived.PDF").status_code == 201

def test_an_upload_needs_a_series_and_an_item_number_stays_with_its_first(client, db, storage, pdf):
    assert send(client, pdf, "910", collection=99).json()["detail"] == "Choose the series these files are for."
    assert client.post("/bundles/upload", params={"bundle": "910", "filename": "A.pdf"}, content=pdf).status_code == 422
    db.add(models.Collection(collection_id=2, name="Ships", archive_series=7))
    db.commit()
    assert send(client, pdf, "910").status_code == 201
    assert db.get(models.UploadedItem, "910").collection_id == 1
    other = send(client, png(), "910", "p1.png", collection=2)
    assert (other.status_code, other.json()["detail"]) == (409, "Item number 910 was uploaded to another series. Choose a different item number.")
    assert db.query(models.UploadedItem).count() == 1
