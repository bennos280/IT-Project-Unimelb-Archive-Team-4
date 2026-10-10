"""The API lists the PDFs that can be run and queues pipeline jobs for backend/worker.py."""
import re

import pytest

from backend.api import main
from backend.common import ROOT
from backend.db import models
from backend.db.loader import stored_path


@pytest.fixture
def data(tmp_path, monkeypatch):
    """DATA with two bundles, as the archive's PDFs are stored: <bundle number>/<pdf>."""
    for number, stem in (("216441", "a"), ("216444", "b")):
        (tmp_path / number).mkdir()
        (tmp_path / number / f"{stem}.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(main, "settings", lambda: {"DATA": str(tmp_path)})
    return tmp_path


def test_bundles_list_each_pdf_whether_it_is_loaded_and_its_surveys(client, db, data):
    db.add(models.Bundle(bundle_id="b", source_pdf="b.pdf"))
    db.flush()
    db.add_all([models.Survey(survey_id="b-9", bundle_id="b"), models.Survey(survey_id="b-7", bundle_id="b")])
    db.flush()
    db.add_all([models.Page(page_id=f"b_0000{n}", survey_id=survey, bundle_id="b", category="main", import_path="x.png")
                for n, survey in ((1, "b-9"), (2, "b-9"), (3, "b-7"))])
    db.commit()
    assert [(b["name"], b["bundle"], b["loaded"], b["surveys"], b["job"]) for b in client.get("/bundles").json()] == [
        ("216441", "a", False, [], None), ("216444", "b", True, ["b-9", "b-7"], None)]  # surveys in scan order


def test_started_job_waits_for_the_worker(client, data):
    pdf = stored_path(data / "216441" / "a.pdf")
    response = client.post("/jobs", json={"pdf": pdf})
    assert response.status_code == 202
    job = response.json()
    assert (job["pdf"], job["status"], job["donePages"], job["totalPages"]) == (pdf, "waiting", 0, 0)
    assert job["updatedAt"].endswith("+00:00")  # UTC, like every other time the API sends
    assert client.get("/bundles").json()[0]["job"] == job
    assert client.get(f"/jobs/{job['id']}").json() == job
    assert client.get("/jobs/999").status_code == 404
    assert client.post("/jobs", json={"pdf": pdf}).status_code == 409  # already waiting


def test_pdfs_inside_the_repo_are_named_relative_to_it(client, data, monkeypatch):
    """The usual setup, DATA=data/raw/Surveys: the job stores a path any checkout can use."""
    from backend.db import loader
    monkeypatch.setattr(main, "ROOT", data.parent)
    monkeypatch.setattr(loader, "ROOT", data.parent)
    monkeypatch.setattr(main, "settings", lambda: {"DATA": data.name})
    pdf = f"{data.name}/216441/a.pdf"
    assert client.get("/bundles").json()[0]["pdf"] == pdf
    assert client.post("/jobs", json={"pdf": pdf}).json()["pdf"] == pdf


def test_jobs_only_for_unloaded_pdfs_in_data(client, db, data):
    db.add(models.Bundle(bundle_id="b", source_pdf="b.pdf"))
    db.commit()
    assert client.post("/jobs", json={"pdf": "C:/Windows/notepad.pdf"}).status_code == 404
    assert client.post("/jobs", json={"pdf": stored_path(data / "216444" / "b.pdf")}).status_code == 409  # loaded


def test_the_archives_bundles_whose_pdf_is_not_here_are_listed_and_can_run(client, data, monkeypatch):
    from backend import scans
    monkeypatch.setattr(scans, "ARCHIVE_PDFS", ["216441/a.pdf", "216450/c.pdf"])
    bundles = client.get("/bundles").json()
    assert [(b["name"], b["bundle"]) for b in bundles] == [("216441", "a"), ("216444", "b"), ("216450", "c")]  # a.pdf once
    pdf = stored_path(data / "216450" / "c.pdf")
    assert bundles[2]["pdf"] == pdf
    assert client.post("/jobs", json={"pdf": pdf}).status_code == 202


def test_the_real_archive_list_names_each_bundle_as_the_archive_does():
    from backend.scans import ARCHIVE
    names = (ROOT / "backend" / "archive_pdfs.txt").read_text(encoding="utf-8").split()
    assert len(names) == len(set(names)) == 45 and ARCHIVE.startswith("https://")
    assert all(re.fullmatch(r"\d+/\d+_[\w.-]+\.pdf", name) for name in names)  # <bundle number>/<file id>_<file name>
