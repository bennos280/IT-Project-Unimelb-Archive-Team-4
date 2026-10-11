"""Runs the jobs queued through the API, oldest first, one at a time: uv run worker"""
import sys
import time
from pathlib import Path

from filelock import FileLock, Timeout

from backend.db import database, loader, models
from backend.pipeline import run as pipeline
from backend.common import ROOT, settings

LOCK = Path(__file__).parent / "worker.lock"

#exits if another worker is running (two would write the same output folder)
def only_worker():
    try:
        return FileLock(LOCK).acquire(timeout=0).lock
    except Timeout:
        sys.exit("another worker is already running")

#a job still running at startup was cut off: mark it failed
def recover(db):
    db.query(models.Job).filter(models.Job.status == "running").update(
        {"status": "failed", "error": "the worker stopped during this job; run it again"})
    db.commit()

def fail(db, job, reason):
    db.rollback()
    job.status, job.error = "failed", reason
    db.commit()

def work_once(db):
    job = db.query(models.Job).filter(models.Job.status == "waiting").order_by(models.Job.job_id).first()
    if job is None:
        return False
    job.status = "running"
    db.commit()

    #a step start reports 0 pages: keep the last count
    def progress(step, done, total):
        job.step = step
        if total:
            job.done_pages, job.total_pages = done, total
        db.commit()

    try:
        {"bundle": run_bundle}[job.kind](db, job, progress)
    except KeyboardInterrupt:
        fail(db, job, "the worker was stopped during this job; run it again")
        raise
    except BaseException as error: #a failed model call raises SystemExit
        fail(db, job, str(error) or type(error).__name__)
        return True
    job.status, job.step = "done", None
    db.commit()
    return True

def run_bundle(db, job, progress):
    pdf = ROOT / job.pdf
    out = ROOT / settings()["OUTPUT"] / pdf.stem
    run = pipeline.Run(pdf, out, progress=progress)
    pipeline.run_steps(run, pipeline.FULL)
    if not run.pages:
        raise SystemExit("the PDF has no pages")
    progress("load", 0, 0)
    loader.dump_into_db(out / "manifest.json")

def main():
    lock = only_worker()
    database.migrate()
    db = database.SessionLocal()
    recover(db)
    print("worker: waiting for pipeline jobs (Ctrl+C to stop)")
    while True:
        if not work_once(db):
            time.sleep(3)

if __name__ == "__main__":
    main()
