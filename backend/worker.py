"""Runs the jobs queued through the API, oldest first, one at a time: uv run worker"""
import sys
import time
from collections import Counter
from pathlib import Path

from filelock import FileLock, Timeout
from sqlalchemy import func

from backend import scans
from backend.db import database, instructions, loader, models
from backend.pipeline import run as pipeline
from backend.common import ROOT, settings

LOCK = Path(__file__).parent / "worker.lock"
MIN_CONFIRMED = 10 #pages of a new page type reviewers must settle before page sorting can learn it

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
        {"bundle": run_bundle, "page": read_page_again, "train": train_sorting}[job.kind](db, job, progress)
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
    active = db.query(models.SortingModel).filter(models.SortingModel.active).first()
    if active and not (ROOT / active.path).is_file():
        raise SystemExit(f"page sorting model {active.model_id}'s file {active.path} is missing: choose another model, or retrain")
    run = pipeline.Run(pdf, out, progress=progress, texts=instructions.texts(db), #the newest versions, as the job starts
                       sorting_model=ROOT / active.path if active else None)
    pipeline.run_steps(run, pipeline.FULL)
    if not run.pages:
        raise SystemExit("the PDF has no pages")
    progress("load", 0, 0)
    loader.dump_into_db(out / "manifest.json")

#one page read again as job.page_type, with the newest prompt and template; what was read off it is swapped all or nothing
def read_page_again(db, job, progress):
    from backend.pipeline.transcribe.transcribe import transcribe
    page = db.get(models.Page, job.page_id)
    newest = instructions.newest(db)
    if job.page_type not in newest:
        raise SystemExit(f"{job.page_type} has no template")
    scan = scans.page_scan(page.import_path, db.get(models.Bundle, page.bundle_id).source_pdf, page.page_id)
    if scan is None:
        raise SystemExit("there is no scan of this page on this computer or on the archive")
    progress("transcribe", 0, 1)
    answer = transcribe(scan, job.page_type, texts={kind: v.body for kind, v in newest.items()})
    con = db.connection()
    con.exec_driver_sql("UPDATE pages SET page_id = page_id WHERE 0") #the write lock first: no review lands between check and swap
    if con.exec_driver_sql("SELECT 1 FROM edits WHERE page_id = ?", (page.page_id,)).first():
        raise SystemExit("the page was reviewed while it was being read again, so it was left as it was")
    loader.clear_content(page.page_id, con)
    loader.insert_content(page.page_id, answer, job.page_type, con)
    con.exec_driver_sql("UPDATE pages SET category = ?, revision_no = revision_no + 1, provider = ?, model = ?, effort = ?, runtime = ?,"
                        " prompt_version_id = ?, template_version_id = ? WHERE page_id = ?",
                        (job.page_type, *(answer.get(key) for key in loader.META), newest[instructions.PROMPT].version_id,
                         newest[job.page_type].version_id, page.page_id))

#refits page sorting on the pages reviewers settled; kept and used only if it passes the check
def train_sorting(db, job, progress):
    from backend.pipeline.identify.identify import retrain
    progress("train", 0, 0)
    built_in = {name for (name,) in db.query(models.PageType.name).filter(models.PageType.built_in)}
    found, no_scan = [], 0
    for page in db.query(models.Page).filter(models.Page.revision_no > 0, models.Page.category != loader.OTHER_CAT):
        scan = scans.page_scan(page.import_path, db.get(models.Bundle, page.bundle_id).source_pdf, page.page_id)
        found += [(scan, page.category)] if scan else []
        no_scan += not scan
    counts = Counter(page_type for _, page_type in found)
    too_few = {t: n for t, n in counts.items() if t not in built_in and n < MIN_CONFIRMED}
    confirmed = [(scan, page_type) for scan, page_type in found if page_type not in too_few]
    output = ROOT / settings()["OUTPUT"]
    out = output / "sorting-models" / f"model-{(db.query(func.max(models.SortingModel.model_id)).scalar() or 0) + 1}.npz"
    result, page_types = retrain(confirmed, out, output / "fingerprints")
    passed = result.passes()
    if passed:
        db.query(models.SortingModel).update({"active": False})
    notes = [f"{t} left out: {n} settled pages of the {MIN_CONFIRMED} it needs" for t, n in sorted(too_few.items())]
    if no_scan:
        notes.append(f"{no_scan} settled pages have no scan here or on the archive")
    db.add(models.SortingModel(path=loader.stored_path(out) if passed else None, page_types=",".join(page_types),
                               pages=result.total, answered=result.answered, wrong=len(result.wrong), passed=passed, active=passed,
                               note="; ".join(notes) or None, reviewer_id=job.reviewer_id))

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
