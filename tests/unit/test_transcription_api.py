"""Job model choices and progress data, with isolated SQLite and output files."""
import hashlib
import json

import pytest

from backend.api import main
from backend.db import models
from backend.db.loader import stored_path


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Point the API at a temporary PDF, output folder and fixed model settings.

    This avoids depending on local configuration or real survey files. The PDF
    only needs to be discoverable: these tests queue jobs without running them.
    """
    pdf = tmp_path / "survey.pdf"
    pdf.write_bytes(b"%PDF")
    values = {"DATA": str(tmp_path), "OUTPUT": str(tmp_path / "output"),
              "MODEL": "sonnet", "PROVIDER": "claude", "EFFORT": "high"}
    monkeypatch.setattr(main, "settings", lambda: values)
    return pdf, tmp_path / "output"


# ---------------------------------------------------------------- POST /jobs
@pytest.mark.parametrize("choices,expected", [
    ({}, ("sonnet", "claude", "high")),
    ({"model": None, "provider": None, "effort": None}, ("sonnet", "claude", "high")),
    ({"model": " custom-model "}, ("custom-model", "claude", "high")),
    ({"model": " gpt-test ", "provider": " codex ", "effort": " medium "},
     ("gpt-test", "codex", "medium")),
])
def test_job_persists_model_choices_and_defaults(client, sessions, config, choices, expected):
    """Save explicit choices after trimming whitespace, and use defaults for omitted or null values.

    Read the job through a separate connection to check that the choices were
    committed for the worker, rather than only held in the request session.
    """
    pdf, _ = config
    response = client.post("/jobs", json={"pdf": stored_path(pdf), **choices})
    assert response.status_code == 202
    # Read from another connection, as the worker does.
    with sessions() as db:
        job = db.get(models.Job, response.json()["id"])
        assert (job.transcription_model, job.transcription_provider, job.transcription_effort) == expected
        assert job.status == "waiting"


@pytest.mark.parametrize("field,value", [
    ("model", ""), ("model", "two words"), ("model", "-option"), ("model", "m" * 201),
    ("provider", "unknown"), ("provider", ""),
    ("effort", " "), ("effort", "two words"), ("effort", "-option"), ("effort", "e" * 41),
])
def test_invalid_model_settings_do_not_queue_a_job(client, db, config, field, value):
    """Reject invalid settings without leaving a queued job behind.

    A valid retry for the same PDF must succeed, so the rejected request cannot
    leave a job that blocks the reviewer from trying again.
    """
    pdf, _ = config
    response = client.post("/jobs", json={"pdf": stored_path(pdf), field: value})
    assert response.status_code == 400
    assert db.query(models.Job).count() == 0
    assert client.post("/jobs", json={"pdf": stored_path(pdf)}).status_code == 202


# ------------------------------------------------ GET /transcription-models
def test_model_list_includes_configuration_without_history(client, config):
    """Return configured model settings even when no pages have been transcribed.
    """
    response = client.get("/transcription-models")
    assert response.status_code == 200
    assert response.json() == {"configured": {"model": "sonnet", "provider": "claude", "effort": "high"},
                               "models": []}


def test_model_history_groups_versions_and_averages_available_runtimes(client, db, config):
    """Keep different template versions separate when summarising model history.

    Pages without a runtime still count, but do not lower the average. Pages
    without a recorded model are excluded from the model history.
    """
    db.add(models.Bundle(bundle_id="bundle", source_pdf="bundle.pdf"))
    versions = [models.InstructionVersion(kind=kind, body="test", sha256="test")
                for kind in ("prompt", "main", "main")]
    db.add_all(versions)
    db.flush()
    prompt, template, newer = [v.version_id for v in versions]
    for index, (runtime, version) in enumerate([(10, template), (30, template), (None, template), (None, newer)]):
        db.add(models.Page(page_id=str(index), bundle_id="bundle", category="main", import_path="test.png",
                           provider="claude", model="sonnet", effort="high", runtime=runtime,
                           prompt_version_id=prompt, template_version_id=version))
    db.add(models.Page(page_id="legacy", bundle_id="bundle", category="main", import_path="old.png"))
    db.commit()
    response = client.get("/transcription-models")
    assert response.status_code == 200
    rows = sorted(response.json()["models"], key=lambda row: row["templateVersion"])
    assert rows == [
        {"provider": "claude", "model": "sonnet", "effort": "high", "promptVersion": prompt,
         "templateVersion": template, "pages": 3, "averageSeconds": 20.0},
        {"provider": "claude", "model": "sonnet", "effort": "high", "promptVersion": prompt,
         "templateVersion": newer, "pages": 1, "averageSeconds": None},
    ]


# ------------------------------------------------ GET /jobs/{id}/transcripts
@pytest.fixture
def job_output(db, config):
    """Create a running bundle job and its temporary output directories.

    Individual tests publish their own images and manifest entries here, so
    they can represent an unfinished run without starting the pipeline.
    """
    pdf, output = config
    job = models.Job(pdf=stored_path(pdf), status="running")
    db.add(job)
    db.commit()
    folder = output / pdf.stem
    (folder / "pages").mkdir(parents=True)
    (folder / "transcribe").mkdir()
    return job, folder


def test_transcripts_require_an_existing_job(client):
    """Return 404 when the requested job does not exist.
    """
    assert client.get("/jobs/999/transcripts").status_code == 404


@pytest.mark.parametrize("kind,pdf", [("page", None), ("train", None), ("bundle", None)])
def test_transcripts_reject_jobs_without_a_bundle(client, db, kind, pdf):
    """Reject page jobs, training jobs and bundle jobs without a PDF.
    """
    job = models.Job(kind=kind, pdf=pdf)
    db.add(job)
    db.commit()
    assert client.get(f"/jobs/{job.job_id}/transcripts").status_code == 400


def test_transcripts_before_output_exists_are_empty(client, db, config):
    """A queued job has no pages yet; missing output is not an API error.
    """
    pdf, _ = config
    job = models.Job(pdf=stored_path(pdf))
    db.add(job)
    db.commit()
    response = client.get(f"/jobs/{job.job_id}/transcripts")
    assert response.status_code == 200
    assert response.json() == {"jobId": job.job_id, "status": "waiting", "pages": []}


def test_partial_transcripts_show_sorted_pages_and_only_verified_data(client, job_output):
    """Show partial pipeline progress in page order, including pages without transcripts.

    Only the completed page has transcript data. Blank, unidentified and
    awaiting-transcription pages retain their distinct progress statuses.
    """
    job, folder = job_output
    content = {"address": "Example street"}
    raw = json.dumps(content).encode()
    (folder / "transcribe" / "001.json").write_bytes(raw)
    # An extracted page can exist before its identification result is published.
    (folder / "pages" / "005.png").write_bytes(b"image")
    manifest = {"pages": [{"file": f"{name}.png", "label": label} for name, label in
                          [("004", "other"), ("003", "notes"), ("002", "blank"), ("001", "main")]],
                "transcripts": {"001.png": {"result": hashlib.sha256(raw).hexdigest(),
                                            "request": {"label": "main"}}}}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    response = client.get(f"/jobs/{job.job_id}/transcripts")
    assert response.status_code == 200
    assert response.json() == {"jobId": job.job_id, "status": "running", "pages": [
        {"id": "001", "category": "main", "status": "Transcribed — not grouped", "data": content},
        {"id": "002", "category": "blank", "status": "Not required", "data": None},
        {"id": "003", "category": "notes", "status": "Awaiting transcription", "data": None},
        {"id": "004", "category": "other", "status": "Needs identification", "data": None},
        {"id": "005", "category": "unidentified", "status": "Needs identification", "data": None},
    ]}


@pytest.mark.parametrize("damage", ["missing", "changed", "invalid-json", "unsafe-name", "invalid-entry"])
def test_unusable_transcripts_are_not_exposed(client, job_output, damage):
    """Skip unusable transcript entries instead of returning unverified data.

    Cover missing files, checksum mismatches, invalid JSON, filenames that
    escape the transcript directory and incomplete manifest entries.
    """
    job, folder = job_output
    raw = b'{"address":"private"}'
    entry = {"result": hashlib.sha256(raw).hexdigest(), "request": {"label": "main"}}
    name = "001.png"
    path = folder / "transcribe" / "001.json"
    if damage == "changed":
        path.write_bytes(b'{"address":"changed"}')
    elif damage == "invalid-json":
        path.write_bytes(b"not json")
        entry["result"] = hashlib.sha256(b"not json").hexdigest()
    elif damage == "unsafe-name":
        name = "../001.png"
        (folder / "001.json").write_bytes(raw)
    elif damage == "invalid-entry":
        entry = "unfinished"
    (folder / "manifest.json").write_text(json.dumps({"transcripts": {name: entry}}))
    response = client.get(f"/jobs/{job.job_id}/transcripts")
    assert response.status_code == 200
    assert response.json()["pages"] == []
