"""Duplicate PDF identities must not relabel existing bundles."""
import fitz
import pytest
from backend.api import uploads
from backend.db import models

@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "settings", lambda: {"DATA": str(tmp_path)})
    monkeypatch.setattr(uploads.scans, "ARCHIVE_PDFS", [])
    return tmp_path

@pytest.fixture
def pdf():
    with fitz.open() as document:
        document.new_page()
        return document.tobytes()

def send(client, pdf, bundle="1"):
    return client.post("/bundles/upload", params={"bundle": bundle, "filename": "A.pdf"}, content=pdf)

def test_loaded_pdf_cannot_be_uploaded_under_another_bundle(client, db, storage, pdf):
    db.add(models.Bundle(bundle_id="A", source_pdf="data/216412/A.pdf"))
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

def test_archive_pdf_requires_original_bundle_number(client, storage, pdf, monkeypatch):
    monkeypatch.setattr(uploads.scans, "ARCHIVE_PDFS", ["216412/A.pdf"])
    assert send(client, pdf).status_code == 409
    assert send(client, pdf, "216412").status_code == 201

@pytest.mark.parametrize("existing_kind", ["database", "local", "archive"])
def test_different_pdf_cannot_reuse_bundle_number(client, db, storage, pdf, monkeypatch, existing_kind):
    if existing_kind == "database":
        db.add(models.Bundle(bundle_id="B", source_pdf="data/216412/B.pdf"))
        db.commit()
    elif existing_kind == "local":
        (storage / "216412").mkdir()
        (storage / "216412/B.pdf").write_bytes(pdf)
    else:
        monkeypatch.setattr(uploads.scans, "ARCHIVE_PDFS", ["216412/B.pdf"])
    response = send(client, pdf, "216412")
    assert response.status_code == 409
    assert "216412" in response.json()["detail"]
    assert not (storage / "216412/A.pdf").exists()
    if existing_kind == "local":
        assert (storage / "216412/B.pdf").read_bytes() == pdf


def test_new_bundle_number_accepts_upload(client, storage, pdf):
    assert send(client, pdf, "999999").status_code == 201
    assert (storage / "999999/A.pdf").read_bytes() == pdf
