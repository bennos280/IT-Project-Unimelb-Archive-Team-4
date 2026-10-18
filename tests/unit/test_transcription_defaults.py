"""The transcription choice the team makes on the Settings page (saved in the db), which has no default, and everything that
starts a transcription without a choice of its own using it or refusing with the same message."""
import pytest

from backend import worker
from backend.api import main
from backend.common import ROOT
from backend.db import app_settings, models
from backend.db.loader import stored_path
from backend.pipeline.transcribe import transcribe as transcription
from tests.unit.test_page_transcription import setup_page

APP = {"provider": "codex", "model": "gpt-test", "effort": "medium"}
NOT_SET = "Choose a transcription model on the Settings page first."


@pytest.fixture
def pdf(tmp_path, monkeypatch):
    (tmp_path / "216441").mkdir()
    (tmp_path / "216441" / "a.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(main, "settings", lambda: {"DATA": str(tmp_path)})
    return stored_path(tmp_path / "216441" / "a.pdf")


def job_choice(db, job_id):
    row = db.get(models.Job, job_id)
    return row.transcription_provider, row.transcription_model, row.transcription_effort


# the helper
def test_nothing_saved_is_none_and_so_is_part_of_a_choice(db):
    assert app_settings.transcription_defaults(db) is None
    db.add(models.AppSetting(key="transcription.model", value="only-one"))
    db.commit()
    assert app_settings.transcription_defaults(db) is None
    app_settings.save_transcription_defaults(db, **APP)
    assert app_settings.transcription_defaults(db) == APP


def test_saving_again_replaces_and_leaves_other_settings(db):
    db.add(models.AppSetting(key="other.setting", value="kept"))
    app_settings.save_transcription_defaults(db, **APP)
    app_settings.save_transcription_defaults(db, "claude", "opus", "low")
    assert app_settings.transcription_defaults(db) == {"provider": "claude", "model": "opus", "effort": "low"}
    assert {s.key: s.value for s in db.query(models.AppSetting)}["other.setting"] == "kept"


# the endpoints
def test_nothing_is_configured_until_a_choice_is_saved(client):
    assert client.get("/transcription-models").json()["configured"] is None


def test_put_saves_all_three_trimmed_and_returns_the_choice(client, db):
    response = client.put("/transcription-defaults", json={"provider": " codex ", "model": " gpt-test ", "effort": " medium "})
    assert response.status_code == 200 and response.json() == APP
    assert client.get("/transcription-models").json()["configured"] == APP
    assert {s.key: s.value for s in db.query(models.AppSetting)} == {f"transcription.{k}": v for k, v in APP.items()}


def test_there_is_no_reset(client):
    client.put("/transcription-defaults", json=APP)
    assert client.delete("/transcription-defaults").status_code == 405
    assert client.get("/transcription-models").json()["configured"] == APP


def test_folders_are_the_data_and_output_folders_inside_the_project(client):
    assert client.get("/folders").json() == {"data": str((ROOT / "data").resolve()), "output": str((ROOT / "output").resolve())}


INVALID = [("model", ""), ("model", "two words"), ("model", "-option"), ("model", "m" * 201), ("model", "a+b"),
           ("provider", "unknown"), ("effort", " "), ("effort", "two words"), ("effort", "-low"), ("effort", "e" * 41)]


@pytest.mark.parametrize("field, value", INVALID)
def test_put_and_post_jobs_reject_the_same_values_with_the_same_message(client, db, pdf, field, value):
    saved = client.put("/transcription-defaults", json={**APP, field: value})
    queued = client.post("/jobs", json={"pdf": pdf, **APP, field: value})
    assert saved.status_code == queued.status_code == 400
    assert saved.json() == queued.json()
    assert db.query(models.AppSetting).count() == 0 and db.query(models.Job).count() == 0


def test_put_needs_all_three_fields(client, db):
    assert client.put("/transcription-defaults", json={"provider": "claude", "model": "opus"}).status_code == 422
    assert db.query(models.AppSetting).count() == 0


def test_put_rejects_a_body_that_is_not_json(client):
    assert client.put("/transcription-defaults", content="{}", headers={"Content-Type": "text/plain"}).status_code == 422


# everything that starts a transcription without a choice
@pytest.mark.parametrize("payload", [{}, {"model": None, "provider": None, "effort": None}, {"model": "mine"},
                                     {"model": "mine", "provider": "claude"}])
def test_a_job_without_a_full_choice_and_nothing_saved_is_refused(client, db, pdf, payload):
    response = client.post("/jobs", json={"pdf": pdf, **payload})
    assert (response.status_code, response.json()["detail"]) == (409, NOT_SET)
    assert db.query(models.Job).count() == 0


def test_a_job_with_an_explicit_choice_works_with_nothing_saved(client, db, pdf):
    response = client.post("/jobs", json={"pdf": pdf, **APP})
    assert response.status_code == 202
    assert job_choice(db, response.json()["id"]) == ("codex", "gpt-test", "medium")
    assert app_settings.transcription_defaults(db) is None


def test_a_job_started_without_a_choice_uses_the_saved_one(client, db, pdf):
    client.put("/transcription-defaults", json=APP)
    assert job_choice(db, client.post("/jobs", json={"pdf": pdf}).json()["id"]) == ("codex", "gpt-test", "medium")


def test_a_job_with_part_of_a_choice_takes_the_rest_from_the_saved_one(client, db, pdf):
    client.put("/transcription-defaults", json=APP)
    assert job_choice(db, client.post("/jobs", json={"pdf": pdf, "model": "mine"}).json()["id"]) == ("codex", "mine", "medium")


def test_a_page_transcription_cannot_leave_out_its_choice(client, db, monkeypatch):
    setup_page(db, monkeypatch)
    response = client.post("/page-transcription/b/p4", json={"reviewerId": 1, "revision": 0})
    assert response.status_code == 422


# the worker
def test_a_bundle_job_with_no_choice_runs_with_the_saved_one(db, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "settings", lambda: {"OUTPUT": str(tmp_path / "output")})
    app_settings.save_transcription_defaults(db, **APP)
    db.add(models.Job(pdf=str(tmp_path / "a.pdf")))
    db.add(models.Job(pdf=str(tmp_path / "b.pdf"), transcription_model="its-own"))
    db.commit()
    seen = []
    monkeypatch.setattr(worker.pipeline, "run_steps", lambda run, names: seen.append(run.transcription_config) or run.pages.append({}))
    monkeypatch.setattr(worker.loader, "dump_into_db", lambda manifest: None)
    worker.work_once(db)
    worker.work_once(db)
    assert seen == [{"PROVIDER": "codex", "MODEL": "gpt-test", "EFFORT": "medium"},
                    {"PROVIDER": "codex", "MODEL": "its-own", "EFFORT": "medium"}]


@pytest.mark.parametrize("fields", [{}, {"transcription_model": "its-own"}])
def test_a_bundle_job_without_a_full_choice_and_nothing_saved_fails_with_the_message(db, tmp_path, monkeypatch, fields):
    monkeypatch.setattr(worker, "settings", lambda: {"OUTPUT": str(tmp_path / "output")})
    job = models.Job(pdf=str(tmp_path / "a.pdf"), **fields)
    db.add(job)
    db.commit()
    monkeypatch.setattr(worker.pipeline, "run_steps", lambda run, names: pytest.fail("the pipeline ran"))
    assert worker.work_once(db)
    db.refresh(job)
    assert (job.status, job.error) == ("failed", NOT_SET)


def test_a_page_job_with_no_choice_and_nothing_saved_fails_with_the_message(db, monkeypatch):
    setup_page(db, monkeypatch)
    monkeypatch.setattr(transcription, "transcribe", lambda *args, **kwargs: pytest.fail("a model was called"))
    job = models.Job(kind="page", page_id="b/p4", page_type="main", reviewer_id=1, base_revision=0)
    db.add(job)
    db.commit()
    assert worker.work_once(db)
    db.refresh(job)
    assert (job.status, job.error) == ("failed", NOT_SET)


def test_a_page_job_with_no_choice_reads_with_the_saved_one(db, monkeypatch):
    setup_page(db, monkeypatch)
    calls = []
    monkeypatch.setattr(transcription, "transcribe", lambda *args, **kwargs: calls.append({k: kwargs[k] for k in ('provider', 'model', 'effort') if k in kwargs}) or {"address": "New", "model": kwargs.get("model")})
    app_settings.save_transcription_defaults(db, **APP)
    db.add(models.Job(kind="page", page_id="b/p4", page_type="main", reviewer_id=1, base_revision=0))
    db.commit()
    assert worker.work_once(db)
    assert calls == [APP]


def test_a_page_job_with_a_choice_keeps_it(db, monkeypatch):
    setup_page(db, monkeypatch)
    calls = []
    monkeypatch.setattr(transcription, "transcribe", lambda *args, **kwargs: calls.append({k: kwargs[k] for k in ('provider', 'model', 'effort') if k in kwargs}) or {"address": "New", "model": kwargs.get("model")})
    app_settings.save_transcription_defaults(db, **APP)
    db.add(models.Job(kind="page", page_id="b/p4", page_type="main", reviewer_id=1, base_revision=0,
                      transcription_model="chosen-model", transcription_provider="claude", transcription_effort="low"))
    db.commit()
    assert worker.work_once(db)
    assert calls == [{"provider": "claude", "model": "chosen-model", "effort": "low"}]
