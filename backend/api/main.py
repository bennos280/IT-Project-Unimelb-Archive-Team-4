from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel
from functools import cache
import json
from backend.db import database, loader, models
from backend.db.loader import CODED_DICT, stored_path
from backend import scans
from backend.api.sections import groupings_main, groupings_coded
from datetime import datetime, timezone
from backend.common import ROOT, settings

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

#takes the db's write lock now, so another save can't land between a check and the write it guards (freed at commit)
def write_lock(db):
    db.connection().exec_driver_sql("UPDATE pages SET page_id = page_id WHERE 0")

#db session dependency generator
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

#request bodies
class CreateReviewerRequest(BaseModel):
    id: int | None = None #None: the next free id
    name: str

class Review(BaseModel):
    value: str | None #None: the reviewer cleared the field
    reviewer: str | None = None #needed only for a new reviewer
    reviewerId: int

class SaveReviewsRequest(BaseModel):
    reviews: dict[str, dict[str, Review]] #(pageid, (field_id, review)), one page per save
    revisions: dict[str, int] #(pageid, its revision_no after this save: the one the edits were made on, plus 1)

#each field's printed label, from data_dict.json
@cache
def printed_labels(category):
    pages = json.loads(CODED_DICT.read_text(encoding="utf-8"))["pages"]
    fields = pages.get({"main": "1", "coded": "3"}.get(category), {}).get("fields", {})
    return {title: field["label_text"] for title, field in fields.items() if "label_text" in field}

#shown on a page of unknown type (stored as other)
OTHER_PAGE = ("The computer couldn't tell what this page is, so it wasn't read. It is in this survey because it comes "
              "after the survey's main form in the scan: check it belongs here, and type anything worth keeping.")

#a page's fields as the review screen shows them: id, label, group, value
def page_fields(db, p):
    fields_list = []
    for f in db.query(models.Field).filter(models.Field.page_id == p.page_id):
        #nested fields go under their parent, others by sections.py
        parent, _, leaf = f.field_title.rpartition(".")
        group = (parent.replace('_', ' ').capitalize() if parent
                 else (groupings_coded if p.category == "coded" else groupings_main).get(leaf, "Miscellaneous"))
        fields_list.append({"id": f.field_title, "label": leaf.replace('_', ' ').capitalize(),
                            "labelText": printed_labels(p.category).get(f.field_title), "group": group, "value": f.text_raw,
                            "decoded": f.decoded_value})

    residents = db.query(models.ResidentField).filter(models.ResidentField.page_id == p.page_id)
    for rf in residents.order_by(models.ResidentField.resident_no):
        fields_list.append({"id": f"residents.{rf.resident_no}.{rf.resident_field_title}",
                            "label": rf.resident_field_title.replace('_', ' ').capitalize(),
                            "labelText": printed_labels("main").get("residents." + rf.resident_field_title),
                            "group": f"Residents {rf.resident_no + 1}", "value": rf.text_raw})

    children = db.query(models.OtherChild).filter(models.OtherChild.page_id == p.page_id)
    for c in children.order_by(models.OtherChild.residence, models.OtherChild.child_no):
        fields_list.append({"id": f"other_children.{c.residence}.{c.child_no}",
                            "label": "Other children: " + c.residence.replace('_', ' '),
                            "labelText": printed_labels("main").get("other_children." + c.residence),
                            "group": "Other children", "value": c.text_raw})

    annotations = db.query(models.Annotation).filter(models.Annotation.page_id == p.page_id)
    for a in annotations.order_by(models.Annotation.annotation_no):
        fields_list.append({"id": f"annotations.{a.annotation_no}", "label": "Annotation", "labelText": None,
                            "group": "Annotations", "value": a.text_raw, "location": a.location})
    return fields_list

#what to check on a page: stored flags, unreadable ([?]) text, and an other page
def page_flags(db, p, fields_list):
    flags = [{"id": f"flag-{fl.flag_id}", "fieldId": fl.field_title, "kind": fl.kind, "reason": fl.reason}
             for fl in db.query(models.Flag).filter(models.Flag.page_id == p.page_id).order_by(models.Flag.flag_id)]
    flags += [{"id": f"unreadable-{f['id']}", "fieldId": f["id"], "kind": "uncertain",
               "reason": "The model couldn't read part of this ([?]): compare it with the scan."}
              for f in fields_list if "[?]" in (f["value"] or "")]
    if p.category == loader.OTHER_CAT:
        flags.append({"id": "other-page", "fieldId": "text", "kind": "uncertain", "reason": OTHER_PAGE})
    return flags

#a survey's pages in scan order, with fields, flags and scan URL; an other page shows as an empty notes page
@app.get("/survey/{survey_id}")
def get_survey(survey_id: str, request: Request, db: Session = Depends(get_db)):
    if not db.get(models.Survey, survey_id):
        raise HTTPException(status_code=404, detail="Survey not found")

    pages_list = []
    for p in db.query(models.Page).filter(models.Page.survey_id == survey_id).order_by(models.Page.page_id):
        fields_list = page_fields(db, p)
        pages_list.append({
            "id": p.page_id,
            "type": "notes" if p.category == loader.OTHER_CAT else p.category,
            "imageUrl": str(request.url_for("page_image", page_id=p.page_id)),
            "fields": fields_list,
            "flags": page_flags(db, p, fields_list),
        })
    return {"id":survey_id, "title":"Wilfred Prest Survey", "pages":pages_list}

#a page's scan: the one this computer's pipeline run made, else the archive's
@app.get("/pages/{page_id}/image", name="page_image")
def page_image(page_id: str, db: Session = Depends(get_db)):
    page = db.get(models.Page, page_id)
    scan = page and scans.page_scan(page.import_path, db.get(models.Bundle, page.bundle_id).source_pdf, page_id)
    if not scan:
        raise HTTPException(status_code=404, detail="No scan for this page.")
    return FileResponse(scan)


#returns list of {id, name}
@app.get("/reviewers")
def get_reviewers(db: Session = Depends(get_db)):
    return [{"id": r.reviewer_id, "name": r.name} for r in db.query(models.Reviewer).order_by(models.Reviewer.reviewer_id)]

#inserts reviewer into db; a name already there is that reviewer
@app.post("/reviewers")
def create_reviewer(payload: CreateReviewerRequest, db: Session = Depends(get_db)):
    clean_name = payload.name.strip()
    if not clean_name: #if empty
        raise HTTPException(status_code=400, detail="Enter a reviewer name.")

    write_lock(db)
    existing = db.query(models.Reviewer).filter(models.Reviewer.name == clean_name).first()
    if existing:
        return {"id": existing.reviewer_id, "name": existing.name}

    id = payload.id if payload.id is not None else (db.query(func.max(models.Reviewer.reviewer_id)).scalar() or 0) + 1
    if db.get(models.Reviewer, id):
        raise HTTPException(status_code=400, detail="Reviewer id already exists.")

    db.add(models.Reviewer(reviewer_id=id, name=clean_name))
    db.commit()
    return {"id": id, "name": clean_name}

#the review screen's id for an edit, and the value the model read
def edited_field(db, e):
    if e.field_title is not None:
        return e.field_title, db.query(models.Field.text_raw).filter_by(
            page_id=e.page_id, field_title=e.field_title).scalar()
    if e.resident_no is not None:
        return f"residents.{e.resident_no}.{e.resident_field_title}", db.query(models.ResidentField.text_raw).filter_by(
            page_id=e.page_id, resident_no=e.resident_no, resident_field_title=e.resident_field_title).scalar()
    if e.child_no is not None:
        return f"other_children.{e.child_residence}.{e.child_no}", db.query(models.OtherChild.text_raw).filter_by(
            page_id=e.page_id, residence=e.child_residence, child_no=e.child_no).scalar()
    return f"annotations.{e.annotation_no}", db.query(models.Annotation.text_raw).filter_by(
        page_id=e.page_id, annotation_no=e.annotation_no).scalar()

#the edit columns for a review screen id
def edit_target(field_id):
    match field_id.split("."):
        case ["residents", no, title] if no.isascii() and no.isdigit():
            return {"resident_no": int(no), "resident_field_title": title}
        case ["other_children", residence, no] if no.isascii() and no.isdigit():
            return {"child_residence": residence, "child_no": int(no)}
        case ["annotations", no] if no.isascii() and no.isdigit():
            return {"annotation_no": int(no)}
    return {"field_title": field_id}

#each page's revision number and the latest edit of each field (a coded field's with its meaning)
@app.get("/reviews/{survey_id}")
def get_reviews(survey_id: str, db: Session = Depends(get_db)):
    pages = db.query(models.Page).filter(models.Page.survey_id == survey_id).order_by(models.Page.page_id).all()
    reviews_dict = {p.page_id: {} for p in pages} #page_id, (field id, review)
    coded = {p.page_id for p in pages if p.category == "coded"}
    names = dict(db.query(models.Reviewer.reviewer_id, models.Reviewer.name))
    #oldest first, so a later edit of a field replaces an earlier one
    for e in db.query(models.Edit).filter(models.Edit.page_id.in_(reviews_dict)).order_by(models.Edit.edit_id):
        field_id, original = edited_field(db, e)
        reviews_dict[e.page_id][field_id] = {
            "value": e.edit_text,
            "decoded": loader.decode(field_id, e.edit_text) if e.page_id in coded else None,
            "original": original,
            "reviewer": names.get(e.reviewer_id),
            "reviewerId": e.reviewer_id,
            "savedAt": e.time.replace(tzinfo=timezone.utc).isoformat() if e.time else "",
        }
    return {"reviews": reviews_dict, "revisions": {p.page_id: p.revision_no for p in pages}}

#saves edits to one page, all or nothing, only if the page is still at the revision they were made on
@app.post("/reviews/{survey_id}")
def save_reviews(survey_id: str, payload: SaveReviewsRequest, db: Session = Depends(get_db)):
    if len(payload.reviews) != 1:
        raise HTTPException(status_code=400, detail="Save one page at a time.")
    [(page_id, reviews)] = payload.reviews.items()
    if not db.query(models.Page).filter(models.Page.page_id == page_id, models.Page.survey_id == survey_id).first():
        raise HTTPException(status_code=404, detail=f"Page {page_id} is not in this survey.")
    if page_id not in payload.revisions:
        raise HTTPException(status_code=400, detail="Page not in revisions.")
    revision = payload.revisions[page_id]

    timestamp = datetime.now(timezone.utc)
    try:
        #only the first of two saves on the same revision counts
        if not db.query(models.Page).filter(models.Page.page_id == page_id, models.Page.revision_no == revision - 1).update(
                {"revision_no": revision, "checked_revision": revision}):
            raise HTTPException(status_code=409, detail="Revision number is outdated.")
        for field_id, review in reviews.items():
            if not db.get(models.Reviewer, review.reviewerId):
                if review.reviewer is None:
                    raise HTTPException(status_code=400, detail=f"Unknown reviewer {review.reviewerId}.")
                db.add(models.Reviewer(reviewer_id=review.reviewerId, name=review.reviewer))
                db.flush() #the reviewer must exist before their edits
            db.add(models.Edit(page_id=page_id, edit_text=review.value, reviewer_id=review.reviewerId, time=timestamp,
                               **edit_target(field_id)))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="An edit is on a field that isn't on its page.")
    except HTTPException:
        db.rollback()
        raise
    return {"revision": revision, "savedAt": timestamp.isoformat()}


#--PIPELINE JOBS--# (queued here, done by backend/worker.py)
class StartJobRequest(BaseModel):
    pdf: str #as listed by GET /bundles

#every survey PDF under DATA in .env, and each of the archive's bundles whose PDF isn't there, as
#DATA/<bundle number>/<its PDF> (running it downloads the PDF)
def pdfs():
    data = ROOT / settings()["DATA"]
    here = list(data.rglob("*.pdf"))
    names = {p.name for p in here}
    return sorted(here + [p for p in (data / pdf for pdf in scans.ARCHIVE_PDFS) if p.name not in names])

def job_json(job):
    return {"id": job.job_id, "kind": job.kind, "pdf": job.pdf, "pageId": job.page_id, "pageType": job.page_type,
            "status": job.status, "step": job.step,
            "donePages": job.done_pages, "totalPages": job.total_pages, "error": job.error,
            "updatedAt": job.updated_at.replace(tzinfo=timezone.utc).isoformat() if job.updated_at else ""}

#every runnable PDF, with its loaded survey ids and latest job; name is the bundle number (the PDF's folder)
@app.get("/bundles")
def get_bundles(db: Session = Depends(get_db)):
    loaded = {bundle_id for (bundle_id,) in db.query(models.Bundle.bundle_id)}
    surveys = {}
    for survey_id, bundle_id in (db.query(models.Page.survey_id, models.Page.bundle_id)
                                 .filter(models.Page.survey_id.is_not(None))
                                 .group_by(models.Page.survey_id, models.Page.bundle_id)
                                 .order_by(func.min(models.Page.page_id))):
        surveys.setdefault(bundle_id, []).append(survey_id)
    latest = {job.pdf: job for job in db.query(models.Job).order_by(models.Job.job_id)}
    data = ROOT / settings()["DATA"]
    bundles = []
    for p in pdfs():
        job = latest.get(stored_path(p))
        bundles.append({"pdf": stored_path(p), "bundle": p.stem, "name": p.stem if p.parent == data else p.parent.name,
                        "loaded": p.stem in loaded, "surveys": surveys.get(p.stem, []), "job": job_json(job) if job else None})
    return bundles

#queues a pipeline run of one PDF; the worker picks it up
@app.post("/jobs", status_code=202)
def start_job(payload: StartJobRequest, db: Session = Depends(get_db)):
    pdf = next((p for p in pdfs() if stored_path(p) == payload.pdf), None)
    if pdf is None:
        raise HTTPException(status_code=404, detail="No such PDF in DATA or on the archive.")
    write_lock(db)
    #a rerun could lose saved reviews
    if db.query(models.Bundle).filter(models.Bundle.bundle_id == pdf.stem).first():
        raise HTTPException(status_code=409, detail="This bundle is already loaded.")
    if db.query(models.Job).filter(models.Job.pdf == payload.pdf, models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(status_code=409, detail="This bundle is already waiting or running.")

    job = models.Job(pdf=payload.pdf)
    db.add(job)
    db.commit()
    return job_json(job)

#one job of any kind, so a screen can follow it until it is done or failed
@app.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    return job_json(job)
