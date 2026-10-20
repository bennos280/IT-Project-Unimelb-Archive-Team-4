"""Runs the jobs queued through the API, oldest first, one at a time: uv run worker. Logs to the terminal and
OUTPUT/worker.log, with the full error of a failed job."""
import logging
import logging.handlers
import sys
import threading
import time
from collections import Counter
from pathlib import Path

from filelock import FileLock, Timeout
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert

from backend import scans
from backend.db import app_settings, database, instructions, loader, models
from backend.pipeline import run as pipeline
from backend.common import ROOT, settings

LOCK = Path(__file__).parent / "worker.lock"
log = logging.getLogger("worker")
MIN_CONFIRMED = 10 #pages of a new page type reviewers must settle before page sorting can learn it
HEARTBEAT = "worker.alive" #in OUTPUT: touched every BEAT seconds while a worker runs, so the API can tell (api.main.worker_running)
BEAT = 10

#exits if another worker is running (two would write the same output folder)
def only_worker():
    try:
        return FileLock(LOCK).acquire(timeout=0).lock
    except Timeout:
        sys.exit("another worker is already running")

#a running worker's heartbeat, from its own thread so a long step doesn't stop it; a touch that fails (the file held open a moment)
#waits for the next beat
def beat(path):
    while True:
        try:
            path.touch()
        except OSError:
            pass
        time.sleep(BEAT)

#a job still running at startup was cut off: mark it failed
def recover(db):
    db.query(models.Job).filter(models.Job.status == "running").update(
        {"status": "failed", "error": "the worker stopped during this job; run it again"})
    db.commit()

def fail(db, job, reason):
    db.rollback()
    job.status, job.error = "failed", reason
    db.commit()

#a job's own model, provider and effort, else the choice saved in the app; a field with neither fails the job
def transcription_choice(db, job):
    saved = app_settings.transcription_defaults(db) or {}
    chosen = {field: getattr(job, f"transcription_{field}") or saved.get(field) for field in app_settings.FIELDS}
    if None in chosen.values():
        raise SystemExit(app_settings.NOT_SET)
    return chosen

def work_once(db):
    job = db.query(models.Job).filter(models.Job.status == "waiting").order_by(models.Job.job_id).first()
    if job is None:
        return False
    job.status = "running"
    db.commit()
    log.info("job %s started: %s %s", job.job_id, job.kind, job.pdf or job.page_id or "")

    #a step start reports 0 pages: keep the last count. Each new step is logged (the task's page lists its lines).
    def progress(step, done, total):
        if step != job.step:
            log.info("job %s step: %s", job.job_id, step)
        job.step = step
        if total:
            job.done_pages, job.total_pages = done, total
        db.commit()

    try:
        {"bundle": run_bundle, "page": read_page_again, "train": train_sorting, "items": add_items}[job.kind](db, job, progress)
    except KeyboardInterrupt:
        log.warning("job %s stopped during %s", job.job_id, job.step)
        fail(db, job, "the worker was stopped during this job; run it again")
        raise
    except BaseException as error: #a failed model call raises SystemExit
        log.exception("job %s failed during %s", job.job_id, job.step)
        fail(db, job, str(error) or type(error).__name__)
        return True
    job.status, job.step = "done", None
    db.commit()
    log.info("job %s done", job.job_id)
    return True

PAUSE = 1  #seconds between requests to the archive
LISTED_MAX = 10_000  #the most the archive shows of one list

#a series' items added to its list from the archive (all of them, or a search's), 24 at a time: each downloadable one no series
#lists yet, saved and logged as it goes. A list the archive can't show whole is gone through a unit (box) at a time.
def add_items(db, job, progress):
    series = db.get(models.Collection, job.collection_id)
    search = job.search or ""

    def read(link, page, words=search):  #a page of a list; the archive is asked again twice, a while later, before giving up
        for attempt in range(3):
            time.sleep(PAUSE if attempt == 0 else PAUSE * 30)
            try:
                return scans.archive_listing(link, page, words)
            except scans.ARCHIVE_ERRORS:
                if attempt == 2:
                    raise

    def pages(link, words=search, first=None):  #every page of a list
        listing, page = first or read(link, 1, words), 1
        while True:
            yield listing
            if page >= listing["pages"]:
                return
            page += 1
            listing = read(link, page, words)

    progress("adding", 0, 0)
    link = scans.listing_link(series.archive_series)
    first = read(link, 1)
    units = []
    if first["total"] < LISTED_MAX:
        lists, total = [pages(link, first=first)], first["total"]
    else:
        boxes = scans.listing_link(series.archive_series, "Units in this series")
        units = [unit["node"] for listing in pages(boxes, words="") for unit in listing["items"]]
        lists = (pages(scans.listing_link(unit, "Items in this unit")) for unit in units)
        total = first["total"] if search else series.archive_items or first["total"]
    listed = {node for (node,) in db.query(models.ArchiveItem.node)}
    seen = added = 0
    for box, listing_pages in enumerate(lists, 1):
        for listing in listing_pages:
            new = [i for i in listing["items"] if i["scanned"] and i["node"] not in listed]
            inserted = 0  #not those a series listed meanwhile
            if new:
                inserted = len(db.execute(insert(models.ArchiveItem).on_conflict_do_nothing().returning(models.ArchiveItem.node), [
                    {"node": i["node"], "collection_id": series.collection_id, "identifier": i["identifier"], "title": i["title"],
                     "pdf": f"{i['node']}/{i['node']}.pdf"} for i in new]).all())
                listed.update(i["node"] for i in new)
            seen, added = seen + len(listing["items"]), added + inserted
            progress("adding", seen, max(total, seen))
            log.info("job %s: %s%s read, %s added", job.job_id, f"box {box:,} of {len(units):,}: " if units else "", f"{seen:,}", f"{added:,}")
    log.info("job %s: %s read, %s added, %s skipped (listed already, Reading Room only or not scanned)", job.job_id, f"{seen:,}",
             f"{added:,}", f"{seen - added:,}")

def run_bundle(db, job, progress):
    pdf = ROOT / job.pdf
    out = ROOT / settings()["OUTPUT"] / pdf.stem
    active = db.query(models.SortingModel).filter(models.SortingModel.active).first()
    if active and not (ROOT / active.path).is_file():
        raise SystemExit(f"page sorting model {active.model_id}'s file {active.path} is missing: choose another model, or retrain")
    run = pipeline.Run(pdf, out, progress=progress, texts=instructions.texts(db), #the newest versions, as the job starts
                       sorting_model=ROOT / active.path if active else None)
    run.transcription_config = {field.upper(): value for field, value in transcription_choice(db, job).items()}
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
    answer = transcribe(scan, job.page_type, texts={kind: v.body for kind, v in newest.items()}, **transcription_choice(db, job))
    con = db.connection()
    con.exec_driver_sql("UPDATE pages SET page_id = page_id WHERE 0") #the write lock first: no review lands between check and swap
    if job.base_revision is not None:
        current = con.exec_driver_sql("SELECT revision_no, category FROM pages WHERE page_id = ?", (page.page_id,)).one()
        if current[0] != job.base_revision or current[1] != job.page_type:
            raise SystemExit("The page changed during transcription; its existing data was kept. Refresh and retry.")
        from backend.db.page_history import snapshot
        snapshot(db, page.page_id, job.reviewer_id, "transcribe")
    elif con.exec_driver_sql("SELECT 1 FROM edits WHERE page_id = ?", (page.page_id,)).first():
        raise SystemExit("the page was reviewed while it was being read again, so it was left as it was")
    loader.clear_content(page.page_id, con)
    loader.insert_content(page.page_id, answer, job.page_type, con)
    con.exec_driver_sql("UPDATE pages SET needs_transcription = 0, checked_revision = NULL, category = ?, revision_no = revision_no + 1, provider = ?, model = ?, effort = ?, runtime = ?,"
                        " prompt_version_id = ?, template_version_id = ? WHERE page_id = ?",
                        (job.page_type, *(answer.get(key) for key in loader.META), newest[instructions.PROMPT].version_id,
                         newest[job.page_type].version_id, page.page_id))

#refits page sorting on the pages reviewers settled; kept and used only if it passes the check
def train_sorting(db, job, progress):
    from backend.pipeline.identify.identify import retrain
    progress("train", 0, 0)
    built_in = {name for (name,) in db.query(models.PageType.name).filter(models.PageType.built_in)}
    found, no_scan = [], 0
    # Moves advance the revision for stale-edit protection, not page-type confirmation.
    # Each move records one event and increments the revision once.
    move_counts = dict(db.query(models.PageMove.page_id, func.count(models.PageMove.move_id))
                       .group_by(models.PageMove.page_id))
    unknown = db.query(models.PageType.name).filter(models.PageType.unknown)
    for page in db.query(models.Page).filter(models.Page.revision_no > 0, models.Page.category.not_in(unknown)):
        if page.revision_no <= move_counts.get(page.page_id, 0):
            continue
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
    output = ROOT / settings()["OUTPUT"]
    output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s",  #other libraries: problems only
                        handlers=[logging.StreamHandler(),  #worker.log up to 1 MB, then worker.log.1 to .3: never more than 4 MB
                                  logging.handlers.RotatingFileHandler(output / "worker.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")])
    log.setLevel(logging.INFO)
    database.migrate()
    threading.Thread(target=beat, args=(output / HEARTBEAT,), daemon=True).start()
    db = database.SessionLocal()
    recover(db)
    log.info("waiting for pipeline jobs (Ctrl+C to stop); log: %s", output / "worker.log")
    while True:
        if not work_once(db):
            time.sleep(3)

if __name__ == "__main__":
    main()
