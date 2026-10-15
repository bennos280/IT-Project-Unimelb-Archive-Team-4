"""backend/worker.py runs queued jobs through the pipeline (faked here: no model calls) and loads their surveys."""
import logging
import pytest

from backend.db import models
from backend import worker


@pytest.fixture(autouse=True)
def output(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "settings", lambda: {"OUTPUT": str(tmp_path / "output")})


@pytest.fixture
def committed(sessions):
    """The job as another connection (the API) sees it."""
    def read(job):
        with sessions() as other:
            return other.get(models.Job, job.job_id)
    return read


def queue(db, tmp_path, status="waiting"):
    job = models.Job(pdf=str(tmp_path / "216441" / "a.pdf"), status=status)
    db.add(job)
    db.commit()
    return job


def fake_pipeline(monkeypatch, steps):
    """run_steps replaced by `steps(run)`; the loader records what it was asked to load."""
    loaded = []
    monkeypatch.setattr(worker.pipeline, "run_steps", lambda run, names: steps(run))
    monkeypatch.setattr(worker.loader, "dump_into_db", loaded.append)
    return loaded


def test_job_runs_the_pipeline_reports_progress_and_loads_its_surveys(db, committed, tmp_path, monkeypatch):
    job = queue(db, tmp_path)

    def steps(run):  # reports as the real run_steps does: each step's start, then pages done / to do
        assert run.out == tmp_path / "output" / "a"
        run.pages.append({"file": "a_00001.png"})
        for step in ("split", "identify", "transcribe"):
            run.progress(step, 0, 0)
        run.progress("transcribe", 1, 2)
        seen = committed(job)
        assert (seen.status, seen.step, seen.done_pages, seen.total_pages) == ("running", "transcribe", 1, 2)
        run.progress("transcribe", 2, 2)
        run.progress("group", 0, 0)

    loaded = fake_pipeline(monkeypatch, steps)
    assert worker.work_once(db)
    seen = committed(job)
    assert (seen.status, seen.step, seen.done_pages, seen.total_pages, seen.error) == ("done", None, 2, 2, None)
    assert loaded == [tmp_path / "output" / "a" / "manifest.json"]
    assert not worker.work_once(db)  # nothing left waiting


def test_a_job_runs_every_step(db, tmp_path, monkeypatch):
    queue(db, tmp_path)
    asked = []
    monkeypatch.setattr(worker.pipeline, "run_steps",
                        lambda run, names: asked.append(names) or run.pages.append({"file": "a_00001.png"}))
    monkeypatch.setattr(worker.loader, "dump_into_db", lambda manifest: None)
    worker.work_once(db)
    assert asked == [["split", "identify", "transcribe", "group", "validate"]]


def test_failed_run_is_marked_failed_with_its_reason_and_loads_nothing(db, committed, tmp_path, monkeypatch):
    job = queue(db, tmp_path)

    def steps(run):
        raise SystemExit("claude failed: usage limit reached")

    loaded = fake_pipeline(monkeypatch, steps)
    assert worker.work_once(db)
    assert (committed(job).status, committed(job).error, loaded) == ("failed", "claude failed: usage limit reached", [])


def test_a_failed_job_is_logged_with_its_full_error(db, committed, tmp_path, monkeypatch, caplog):
    job = queue(db, tmp_path)

    def steps(run):
        raise SystemExit("claude failed: usage limit reached")

    fake_pipeline(monkeypatch, steps)
    with caplog.at_level(logging.INFO, logger="worker"):
        worker.work_once(db)
    assert [r.getMessage() for r in caplog.records] == [f"job {job.job_id} started: bundle {job.pdf}", f"job {job.job_id} failed during None"]
    assert caplog.records[1].exc_info[0] is SystemExit  # the traceback is kept, not just the message


def test_pdf_with_no_pages_fails_instead_of_loading_nothing(db, committed, tmp_path, monkeypatch):
    job = queue(db, tmp_path)
    loaded = fake_pipeline(monkeypatch, lambda run: None)
    assert worker.work_once(db)
    assert (committed(job).status, committed(job).error, loaded) == ("failed", "the PDF has no pages", [])


def test_stopping_the_worker_marks_its_job_failed(db, committed, tmp_path, monkeypatch):
    job = queue(db, tmp_path)

    def steps(run):
        raise KeyboardInterrupt

    fake_pipeline(monkeypatch, steps)
    with pytest.raises(KeyboardInterrupt):
        worker.work_once(db)
    assert committed(job).status == "failed" and "run it again" in committed(job).error


def test_job_cut_off_by_a_stopped_worker_can_be_run_again(db, committed, tmp_path):
    job = queue(db, tmp_path, status="running")
    worker.recover(db)
    assert committed(job).status == "failed" and "run it again" in committed(job).error


def test_only_one_worker_runs_at_a_time(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "LOCK", tmp_path / "worker.lock")
    lock = worker.only_worker()
    with pytest.raises(SystemExit, match="another worker"):
        worker.only_worker()
    lock.release()
    worker.only_worker().release()  # free again once the first worker has stopped


def test_a_job_reads_with_the_newest_prompt_and_templates(db, tmp_path, monkeypatch):
    db.add_all([models.InstructionVersion(kind="prompt", body="old", sha256="a"),
                models.InstructionVersion(kind="main", body="{}", sha256="b"),
                models.InstructionVersion(kind="prompt", body="new", sha256="c")])
    queue(db, tmp_path)
    used = []
    monkeypatch.setattr(worker.pipeline, "run_steps",
                        lambda run, names: used.append(run.texts) or run.pages.append({"file": "a_00001.png"}))
    monkeypatch.setattr(worker.loader, "dump_into_db", lambda manifest: None)
    worker.work_once(db)
    assert used == [{"prompt": "new", "main": "{}"}]
