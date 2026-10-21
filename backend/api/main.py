from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session
from pydantic import BaseModel, Field
from typing import Literal
from functools import cache
import io
import json
import os
import re
import shlex
import socket
from pathlib import Path, PurePosixPath
import sqlite3
import sys
import threading
import uuid
import zipfile
from backend.db import app_settings, checks, database, grouping, instructions, loader, models
from backend.db.loader import CODED_DICT, stored_path
from backend import scans
from backend.api.sections import groupings_main, groupings_coded
from datetime import datetime, timezone
from urllib.error import URLError
from backend.common import ROOT, find_images, settings
from backend.pipeline.transcribe import areas, providers
from backend.pipeline.transcribe.transcribe import ALL_PROVIDERS

from backend.api.uploads import archive_sources, upload_bundle
from backend.api import connections, local_sorting, transcription_options

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(connections.router)
app.include_router(transcription_options.router)
app.include_router(local_sorting.router)

#takes the db's write lock now, so another save can't land between a check and the write it guards (freed at commit)
def write_lock(db):
    db.connection().exec_driver_sql("UPDATE pages SET page_id = page_id WHERE 0")

get_db = database.get_db #the db session dependency, defined there so connections.py can use it too

@app.post("/bundles/upload", status_code=201)
async def import_bundle(request: Request, bundle: str, filename: str, collection: int, db: Session = Depends(get_db)):
    return await upload_bundle(request, bundle, filename, collection, db)


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

#shown on a page of unknown type; one grouped with other pages is in their record because it follows its first page
OTHER_PAGE = "The computer couldn't tell what this page is, so it wasn't read. "
OTHER_PAGE_GROUPED = ("It is in this {0} because it comes after the {0}'s first page in the scan: check it belongs here, and "
                      "type anything worth keeping.")
OTHER_PAGE_ALONE = "Check what it is, and type anything worth keeping."

#what the record a page is in is called on screen (its level's name)
def page_record_name(db, p):
    return grouping.record_name(db, db.get(models.Bundle, p.bundle_id).collection_id, p.survey_id)

#a page's fields as the review screen shows them: id, label, group, value; free text is under "<record> details"
def page_fields(db, p):
    fields_list = []
    for f in db.query(models.Field).filter(models.Field.page_id == p.page_id):
        #nested fields go under their parent, others by sections.py
        parent, _, leaf = f.field_title.rpartition(".")
        group = (parent.replace('_', ' ').capitalize() if parent
                 else (groupings_coded if p.category == "coded" else groupings_main).get(leaf)
                 or (f"{page_record_name(db, p)} details".capitalize() if leaf == "text" else "Miscellaneous"))
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
        box = areas.shown(p.category, a.area, a.region)
        fields_list.append({"id": f"annotations.{a.annotation_no}", "label": "Annotation", "labelText": None,
                            "group": "Annotations", "value": a.text_raw, "location": a.location, "area": a.area,
                            **({"areaLabel": areas.label(p.category, a.area), "sourceRegion": box} if box else {})})
    return fields_list

#what to check on a page: stored flags, unreadable ([?]) text, and a page of its collection's Unknown type
def page_flags(db, p, fields_list):
    flags = [{"id": f"flag-{fl.flag_id}", "fieldId": fl.field_title, "kind": fl.kind, "reason": fl.reason}
             for fl in db.query(models.Flag).filter(models.Flag.page_id == p.page_id).order_by(models.Flag.flag_id)]
    flags += [{"id": f"unreadable-{f['id']}", "fieldId": f["id"], "kind": "uncertain",
               "reason": "The model couldn't read part of this ([?]): compare it with the scan."}
              for f in fields_list if "[?]" in (f["value"] or "")]
    if db.get(models.PageType, p.category).unknown and any(f["id"] == "text" for f in fields_list):
        grouped = grouping.grouped(db, db.get(models.Bundle, p.bundle_id).collection_id) and p.survey_id and db.query(models.Page).filter_by(survey_id=p.survey_id).count() > 1
        flags.append({"id": "other-page", "fieldId": "text", "kind": "uncertain",
                      "reason": OTHER_PAGE + (OTHER_PAGE_GROUPED.format(page_record_name(db, p)) if grouped else OTHER_PAGE_ALONE)})
    return flags

#a survey's pages in scan order, with fields, flags and scan URL, whether it is its whole item (all the item's pages), the
#record it sits in (None: at the top), and the records it sits inside, top first, each with its level's name
@app.get("/survey/{survey_id}")
def get_survey(survey_id: str, request: Request, db: Session = Depends(get_db)):
    survey = db.get(models.Survey, survey_id)
    if not survey:
        raise HTTPException(status_code=404, detail="No such record.")

    pages_list = []
    for p in db.query(models.Page).filter(models.Page.survey_id == survey_id).order_by(models.Page.page_id):
        fields_list, page_type = page_fields(db, p), db.get(models.PageType, p.category)
        pages_list.append({
            "id": p.page_id,
            "type": p.category,
            "typeLabel": page_type.label,
            "needsTranscription": p.needs_transcription,
            "imageUrl": str(request.url_for("page_image", page_id=p.page_id)),
            "fields": fields_list,
            "flags": page_flags(db, p, fields_list),
        })
    bundle = db.get(models.Bundle, survey.bundle_id)
    collection = db.get(models.Collection, bundle.collection_id)
    number = PurePosixPath(bundle.source_pdf.replace("\\", "/")).parent.name
    name = number if number.isdigit() else bundle.bundle_id  #as the dashboard names it
    item = db.get(models.ArchiveItem, int(name)) if name.isascii() and name.isdigit() and len(name) < 19 else None
    return {"id":survey_id, "bundleId":survey.bundle_id, "collectionId":collection.collection_id, "title":collection.name,
            "item": {"name": name, "archive": {"identifier": item.identifier, "title": item.title} if item else None},
            "recordName": grouping.record_name(db, collection.collection_id, survey_id), "grouped": grouping.grouped(db, collection.collection_id),
            "wholeItem": db.query(models.Page).filter_by(bundle_id=bundle.bundle_id).count() == len(pages_list),
            "parentId": survey.parent_id, "ancestors": ancestors(db, collection.collection_id, survey.parent_id), "pages":pages_list}

#a record and the records it sits inside, top first, each its id, its level's name and the record it sits in, but not one
#holding just one record and no pages of its own (the item's page opens past it); [] for none
def ancestors(db, collection_id, survey_id):
    found = []
    while survey_id is not None:
        held = (db.query(models.Survey).filter_by(parent_id=survey_id).count(), db.query(models.Page).filter_by(survey_id=survey_id).count())
        parent = db.get(models.Survey, survey_id).parent_id
        if held != (1, 0):
            found.insert(0, {"id": survey_id, "name": grouping.record_name(db, collection_id, survey_id), "parent": parent})
        survey_id = parent
    return found

#a page's scan: the one this computer's pipeline run made, else the archive's; preprocessed=true: straightened, cropped
#and black and white (the scan itself if that fails)
@app.get("/pages/{page_id:path}/image", name="page_image")
def page_image(page_id: str, preprocessed: bool = False, db: Session = Depends(get_db)):
    page = db.get(models.Page, page_id)
    scan = page and scans.page_scan(page.import_path, db.get(models.Bundle, page.bundle_id).source_pdf, page_id)
    if not scan:
        raise HTTPException(status_code=404, detail="No scan for this page.")
    if preprocessed:
        from backend.pipeline.preprocess.preprocess import cleaned
        scan = cleaned(scan, page_id)
    return FileResponse(scan)


#a page's scan, small, for a preview: from its item's PDF or its scan on this computer (never the archive); 404 if neither is here
@app.get("/pages/{page_id:path}/thumbnail")
def page_thumbnail(page_id: str, db: Session = Depends(get_db)):
    page = db.get(models.Page, page_id)
    image = page and scans.page_thumbnail(db.get(models.Bundle, page.bundle_id).source_pdf, page.import_path, page_id)
    if not image:
        raise HTTPException(status_code=404, detail="No scan of this page here.")
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

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
        raise HTTPException(status_code=404, detail=f"Page {page_id} is not in this record.")
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

#each model's accuracy on the pages reviewers have saved since they were last read, per page type, prompt and template version: a field
#whose final edit differs from what the model read counts as wrong, every other field on those pages as right
@app.get("/accuracy")
def get_accuracy(db: Session = Depends(get_db)):
    scores = {}
    for p in db.query(models.Page).filter(models.Page.checked_revision == models.Page.revision_no, models.Page.model.is_not(None)):
        final = {}
        for e in db.query(models.Edit).filter(models.Edit.page_id == p.page_id).order_by(models.Edit.edit_id):
            field_id, original = edited_field(db, e)
            final[field_id] = (e.edit_text or "") != (original or "")
        score = scores.setdefault((p.model, p.effort, p.category, p.prompt_version_id, p.template_version_id), {
            "model": p.model, "effort": p.effort, "pageType": p.category,
            "promptVersion": p.prompt_version_id, "templateVersion": p.template_version_id,
            "pages": 0, "fields": 0, "changed": 0})
        score["pages"] += 1
        score["fields"] += len(page_fields(db, p))
        score["changed"] += sum(final.values())
    for score in scores.values():
        score["accuracy"] = round(100 * (score["fields"] - score["changed"]) / score["fields"], 1) if score["fields"] else None
    return sorted(scores.values(), key=lambda score: -(score["accuracy"] or 0))


#--TRANSCRIPTION PROMPT AND TEMPLATES--# (backend/db/instructions.py: saved as versions; jobs use the newest of each)
class InstructionRequest(BaseModel):
    body: str
    basedOn: int | None #the version the edit started from (None: a page type's first template); refused if a newer one was saved since
    reviewerId: int
    note: str | None = None
    rules: dict = {} #a template's fields' rules (backend/db/checks.py); the prompt has none

def version_json(v, names):
    return {"id": v.version_id, "kind": v.kind, "body": v.body, "rules": json.loads(v.rules) if v.rules else {},
            "reviewerId": v.reviewer_id, "reviewer": names.get(v.reviewer_id), "note": v.note,
            "createdAt": v.created_at.replace(tzinfo=timezone.utc).isoformat() if v.created_at else ""}

#the newest prompt, and the newest template of each page type
@app.get("/instructions")
def get_instructions(db: Session = Depends(get_db)):
    names = dict(db.query(models.Reviewer.reviewer_id, models.Reviewer.name))
    return {kind: version_json(v, names) for kind, v in instructions.newest(db).items()}

#every version of the prompt or of one template, newest first; number counts the kind's versions from 1, oldest first
@app.get("/instructions/{kind}")
def get_instruction_versions(kind: str, db: Session = Depends(get_db)):
    versions = (db.query(models.InstructionVersion).filter(models.InstructionVersion.kind == kind)
                .order_by(models.InstructionVersion.version_id.desc()).all())
    if not versions:
        raise HTTPException(status_code=404, detail=f"No prompt or template called {kind}.")
    names = dict(db.query(models.Reviewer.reviewer_id, models.Reviewer.name))
    return [{**version_json(v, names), "number": len(versions) - i} for i, v in enumerate(versions)]

#every version of the prompt and the templates, oldest first, with its number in its kind, the kind's label and whether it is the kind's newest
@app.get("/instruction-versions")
def get_all_instruction_versions(db: Session = Depends(get_db)):
    names = dict(db.query(models.Reviewer.reviewer_id, models.Reviewer.name))
    labels = dict(db.query(models.PageType.name, models.PageType.label))
    current, counts, rows = instructions.newest(db), {}, []
    for v in db.query(models.InstructionVersion).order_by(models.InstructionVersion.version_id):
        counts[v.kind] = counts.get(v.kind, 0) + 1
        rows.append({**version_json(v, names), "number": counts[v.kind],
                     "label": "Prompt" if v.kind == instructions.PROMPT else labels.get(v.kind, v.kind),
                     "current": current[v.kind].version_id == v.version_id})
    return rows

#saves a new version of the prompt or of a page type's template (an Unknown type has none), used from the next job on; checked first
@app.post("/instructions/{kind}", status_code=201)
def save_instruction(kind: str, payload: InstructionRequest, db: Session = Depends(get_db)):
    write_lock(db)
    current = instructions.newest(db)
    page_type = db.get(models.PageType, kind)
    if kind != instructions.PROMPT and (not page_type or page_type.unknown):
        raise HTTPException(status_code=404, detail=f"No prompt or page type called {kind}.")
    reviewer = db.get(models.Reviewer, payload.reviewerId)
    if reviewer is None:
        raise HTTPException(status_code=400, detail=f"Unknown reviewer {payload.reviewerId}.")
    if payload.basedOn != (current[kind].version_id if kind in current else None):
        raise HTTPException(status_code=409, detail="Someone saved a newer version: reload it and make your change again.")
    if kind == instructions.PROMPT and payload.rules:
        raise HTTPException(status_code=400, detail="The prompt has no fields to set rules on.")
    if (kind in current and payload.body.replace("\r\n", "\n") == current[kind].body.replace("\r\n", "\n")
            and payload.rules == (json.loads(current[kind].rules) if current[kind].rules else {})):
        raise HTTPException(status_code=400, detail="Nothing changed.")
    found = instructions.problems(kind, payload.body, {k: v.body for k, v in current.items()}, grouping.required_fields(db))
    if found := found or (checks.rule_problems(payload.rules, json.loads(payload.body)) if kind != instructions.PROMPT else []):
        raise HTTPException(status_code=400, detail=found)
    version = models.InstructionVersion(kind=kind, body=payload.body, rules=json.dumps(payload.rules) if payload.rules else None,
                                        sha256=instructions.sha256(payload.body), reviewer_id=reviewer.reviewer_id, note=payload.note)
    db.add(version)
    db.commit()
    return version_json(version, {reviewer.reviewer_id: reviewer.name})


#--A SERIES' CHECKS--# (backend/db/checks.py: rules across its fields, saved as versions; the newest is used)
class ChecksRequest(BaseModel):
    checks: list
    basedOn: int | None #the version the edit started from (None: the series' first); refused if a newer one was saved since
    reviewerId: int
    note: str | None = None

def check_version_json(v, number, names):
    return {"id": v.version_id, "number": number, "checks": json.loads(v.body), "reviewer": names.get(v.reviewer_id), "note": v.note,
            "createdAt": v.created_at.replace(tzinfo=timezone.utc).isoformat() if v.created_at else ""}

#each of a series' page types -> the fields of its newest template, which its checks may name
def series_fields(db, collection_id):
    newest = instructions.newest(db)
    return {t.name: set(checks.fields(json.loads(newest[t.name].body)))
            for t in db.query(models.PageType).filter_by(collection_id=collection_id) if t.name in newest}

def series_check_versions(db, collection_id):
    if not db.get(models.Collection, collection_id):
        raise HTTPException(status_code=404, detail=f"There's no series {collection_id}.")
    return (db.query(models.CheckVersion).filter_by(collection_id=collection_id)
            .order_by(models.CheckVersion.version_id.desc()).all())

#every version of a series' checks, newest first, numbered from 1
@app.get("/collections/{collection_id}/checks")
def get_series_checks(collection_id: int, db: Session = Depends(get_db)):
    versions = series_check_versions(db, collection_id)
    names = dict(db.query(models.Reviewer.reviewer_id, models.Reviewer.name))
    return [check_version_json(v, len(versions) - n, names) for n, v in enumerate(versions)]

#saves a new version of a series' checks, used from the next check on (an older one brought back is saved as the newest)
@app.post("/collections/{collection_id}/checks", status_code=201)
def save_series_checks(collection_id: int, payload: ChecksRequest, db: Session = Depends(get_db)):
    write_lock(db)
    versions = series_check_versions(db, collection_id)
    reviewer = db.get(models.Reviewer, payload.reviewerId)
    if reviewer is None:
        raise HTTPException(status_code=400, detail=f"Unknown reviewer {payload.reviewerId}.")
    if payload.basedOn != (versions[0].version_id if versions else None):
        raise HTTPException(status_code=409, detail="Someone saved newer checks: reload them and make your change again.")
    if payload.checks == (json.loads(versions[0].body) if versions else []):
        raise HTTPException(status_code=400, detail="Nothing changed.")
    if found := checks.check_problems(payload.checks, series_fields(db, collection_id)):
        raise HTTPException(status_code=400, detail=found)
    version = models.CheckVersion(collection_id=collection_id, body=json.dumps(payload.checks), reviewer_id=reviewer.reviewer_id,
                                  note=payload.note)
    db.add(version)
    db.commit()
    return check_version_json(version, len(versions) + 1, {reviewer.reviewer_id: reviewer.name})

#queues the worker to check every page of a series again against its page types' rules and its checks
@app.post("/collections/{collection_id}/check", status_code=202)
def check_series_again(collection_id: int, db: Session = Depends(get_db)):
    write_lock(db)
    series_check_versions(db, collection_id)
    if db.query(models.Job).filter(models.Job.kind == "check", models.Job.collection_id == collection_id,
                                   models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(status_code=409, detail="This series is already being checked.")
    job = models.Job(kind="check", collection_id=collection_id)
    db.add(job)
    db.commit()
    return job_json(job)


#--PAGE TYPES--# (the four built in, and any added here; a page type's pages are read with its template)
class PageTypeRequest(BaseModel):
    reviewerId: int
    collectionId: int = 1
    label: str | None = None #what people see; the name if not given
    name: str | None = None #its id; made from the label if not given

class PageTypeSettings(BaseModel):
    label: str | None = None

class CollectionSettings(BaseModel):
    name: str | None = None
    archiveSeries: str | None = None #its series' address on the archive, or the number at its end
    archiveIdentifier: str | None = None #and the series' identifier, title and items from /archive-series, with archiveSeries
    archiveTitle: str | None = None
    archiveItems: int | None = None

#a level of record: what one is called, the page types that start one and those that join the one showing the same number,
#and the field holding that number (None or "": page order only)
#one part of what a level's record is made of: a page type, how many of it one has, and how its pages are found: one starts it,
#the next follow the page before them, or are matched by number wherever they were filed
class LevelPart(BaseModel):
    type: str
    count: Literal["one", "one_or_more", "any", "at_most_one"] = "one"
    how: Literal["starts", "follows", "matched"] = "follows"

class LevelSettings(BaseModel):
    name: str
    parts: list[LevelPart] = []
    key: str | None = None

class LevelsSettings(BaseModel):
    levels: list[LevelSettings]

class LevelsPreview(LevelsSettings):
    item: str #the bundle id of an item already read

class NewCollection(BaseModel):
    name: str
    archiveSeries: str
    archiveIdentifier: str | None = None #the series' identifier, title and items from /archive-series; None: not looked up
    archiveTitle: str | None = None
    archiveItems: int | None = None

class PageTypeChange(BaseModel):
    pageType: str
    reviewerId: int
    model: str | None = None
    provider: str | None = None
    effort: str | None = None

RESERVED = {instructions.PROMPT, "blank", "review"} #the prompt's kind, and what page sorting answers for no page type

def page_type_json(t, templates):
    return {"name": t.name, "label": t.label, "builtIn": t.built_in, "unknown": t.unknown,
            "templateVersion": templates[t.name].version_id if t.name in templates else None}

#the page types, each with its newest template's version (None: it has none, so its pages aren't read)
@app.get("/page-types")
def get_page_types(collection: int | None = None, db: Session = Depends(get_db)):
    templates = instructions.newest(db)
    types = db.query(models.PageType).order_by(models.PageType.built_in.desc(), models.PageType.name)
    return [page_type_json(t, templates) for t in (types if collection is None else types.filter_by(collection_id=collection))]

#a free id for a page type, from its label: "Follow-up visit" -> follow_up_visit, then follow_up_visit_2, ...
def new_name(db, label):
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    base = base if instructions.KEY.fullmatch(base) else f"type_{base}".rstrip("_")
    name, n = base, 1
    while name in RESERVED or db.get(models.PageType, name):
        n += 1
        name = f"{base}_{n}"
    return name

#adds a page type; POST /instructions/{name} gives it a template, and only then can pages be read as it
@app.post("/page-types", status_code=201)
def create_page_type(payload: PageTypeRequest, db: Session = Depends(get_db)):
    label = (payload.label or payload.name or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="A page type's label can't be empty.")
    write_lock(db)
    name = payload.name.strip() if payload.name else new_name(db, label)
    if not instructions.KEY.fullmatch(name) or name in RESERVED:
        raise HTTPException(status_code=400, detail="A page type's name is lower-case letters, digits and _, starting with a letter.")
    if db.get(models.PageType, name):
        raise HTTPException(status_code=409, detail=f"There is already a page type called {name}.")
    if not db.get(models.Reviewer, payload.reviewerId):
        raise HTTPException(status_code=400, detail=f"Unknown reviewer {payload.reviewerId}.")
    if not db.get(models.Collection, payload.collectionId):
        raise HTTPException(status_code=400, detail="No such series.")
    try:
        db.add(models.PageType(name=name, label=label, reviewer_id=payload.reviewerId, collection_id=payload.collectionId))
        db.commit()
    except IntegrityError: #the label is taken in the collection
        db.rollback()
        raise HTTPException(status_code=409, detail=f"There is already a page type labelled {label}.")
    return page_type_json(db.get(models.PageType, name), {})

#changes a page type's label (how its pages group is its collection's levels')
@app.patch("/page-types/{name}")
def update_page_type(name: str, payload: PageTypeSettings, db: Session = Depends(get_db)):
    write_lock(db)
    t = db.get(models.PageType, name)
    if not t:
        raise HTTPException(status_code=404, detail=f"No page type called {name}.")
    label = t.label if payload.label is None else payload.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="A page type's label can't be empty.")
    t.label = label
    try:
        db.commit()
    except IntegrityError: #the label is taken in the collection
        db.rollback()
        raise HTTPException(status_code=409, detail=f"There is already a page type labelled {label}.")
    return page_type_json(t, instructions.newest(db))

#a collection's bundle jobs: those waiting or running, and the PDFs whose latest job failed and that aren't loaded
def bundle_jobs(db, collection_id):
    owners = loader.archive_owners(db)
    latest = {job.pdf: job for job in db.query(models.Job).filter_by(kind="bundle").order_by(models.Job.job_id)
              if loader.series_of(owners, job.pdf) == collection_id}
    loaded = {bundle_id for (bundle_id,) in db.query(models.Bundle.bundle_id)}
    return {"running": sum(job.status in ("waiting", "running") for job in latest.values()),
            "failed": sum(job.status == "failed" and PurePosixPath(job.pdf.replace("\\", "/")).stem not in loaded for job in latest.values())}

#a collection, and with db how far along it is: bundles loaded (processed), being processed or failed; pages, those in a survey
#(reviewable) and reviewed; what needs a person (pages of its Unknown type, open flags); how far it is set up (page types
#other than Unknown, and how many of them have a template); and whether its pages group into records (a type starts one of
#its top level); with its levels of record, top first, and what one record is called
def collection_json(c, db=None):
    found = {}
    if db is not None:
        pages = [p for b in cached_progress(db) if b["collectionId"] == c.collection_id for p in b["pages"]]
        reviewable = [p for p in pages if p["surveyId"] is not None]
        templates = instructions.newest(db)
        types = db.query(models.PageType).filter_by(collection_id=c.collection_id).all()
        unknown = {t.name for t in types if t.unknown}
        jobs = bundle_jobs(db, c.collection_id)
        found = {"bundles": db.query(models.Bundle).filter_by(collection_id=c.collection_id).count(), **jobs, "pages": len(pages),
                 "reviewable": len(reviewable), "reviewed": sum(p["status"] == "Reviewed" for p in reviewable),
                 "unknownPages": db.query(models.Page).filter(models.Page.category.in_(unknown)).count(),
                 "flagged": sum(p["flagCount"] for p in pages),
                 "pageTypes": len(types) - len(unknown), "templates": sum(t.name in templates for t in types if not t.unknown),
                 "grouped": grouping.grouped(db, c.collection_id)}
    levels = grouping.levels(object_session(c), c.collection_id)
    return {"id": c.collection_id, "name": c.name, "levels": [grouping.level_json(level) for level in levels],
            "recordName": levels[-1].name if levels else "record", "archiveSeries": c.archive_series,
            "archiveIdentifier": c.archive_identifier, "archiveTitle": c.archive_title, "archiveItems": c.archive_items, **found}

def series_text(text):
    return (text or "").strip()[:300] or None

#a series' node id on archives.library.unimelb.edu.au, from its address (.../nodes/view/499420) or the number itself; None: neither
def series_node(text):
    found = re.fullmatch(r"\s*(?:https?://archives\.library\.unimelb\.edu\.au/nodes/view/)?([1-9]\d{0,8})/?\s*", text or "")
    return int(found.group(1)) if found else None

SERIES_HELP = "Paste the series' address from archives.library.unimelb.edu.au (.../nodes/view/<number>), or just its number."

#every collection, with how many bundles and pages it has
#every series with its counts; brief: each one's id and name only (the header's series switcher), without counting
@app.get("/collections")
def get_collections(brief: bool = False, db: Session = Depends(get_db)):
    found = db.query(models.Collection).order_by(models.Collection.collection_id)
    return [{"id": c.collection_id, "name": c.name} for c in found] if brief else [collection_json(c, db) for c in found]

#a new collection, linked to its series on the archive, starts with its Unknown page type
@app.post("/collections", status_code=201)
def create_collection(payload: NewCollection, db: Session = Depends(get_db)):
    name, node = payload.name.strip(), series_node(payload.archiveSeries)
    if not name:
        raise HTTPException(status_code=400, detail="A series needs a name.")
    if node is None:
        raise HTTPException(status_code=400, detail=SERIES_HELP)
    write_lock(db)
    collection = models.Collection(name=name, archive_series=node, archive_identifier=series_text(payload.archiveIdentifier),
                                   archive_title=series_text(payload.archiveTitle), archive_items=payload.archiveItems)
    db.add(collection)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"There is already a series called {name}.")
    db.add(models.PageType(name=new_name(db, "Unknown"), label="Unknown", unknown=True, built_in=True, collection_id=collection.collection_id))
    db.commit()
    return collection_json(collection, db)

@app.get("/collections/{collection_id}")
def get_collection(collection_id: int, db: Session = Depends(get_db)):
    c = db.get(models.Collection, collection_id)
    if not c:
        raise HTTPException(status_code=404, detail="No such series.")
    return collection_json(c, db)

#renames a collection or relinks its series; a field left out of the request stays as it is
@app.patch("/collections/{collection_id}")
def update_collection(collection_id: int, payload: CollectionSettings, db: Session = Depends(get_db)):
    write_lock(db)
    c = db.get(models.Collection, collection_id)
    if not c:
        raise HTTPException(status_code=404, detail="No such series.")
    given = payload.model_fields_set
    if "name" in given:
        if not (payload.name or "").strip():
            raise HTTPException(status_code=400, detail="A series needs a name.")
        c.name = payload.name.strip()
    if "archiveSeries" in given:
        if series_node(payload.archiveSeries) is None:
            raise HTTPException(status_code=400, detail=SERIES_HELP)
        c.archive_series = series_node(payload.archiveSeries)
        c.archive_identifier, c.archive_title = series_text(payload.archiveIdentifier), series_text(payload.archiveTitle)
        c.archive_items = payload.archiveItems
    name = c.name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"There is already a series called {name}.")
    return collection_json(c, db)

LEVEL_NAME = re.compile(r"[a-z]+(['-][a-z]+)*( [a-z]+(['-][a-z]+)*)?")

#why a level can't be saved, or None: its name (a word or two, lower case, after names), what one is made of (the collection's
#own read page types, each once, the first and only the first starting one), and its number field, which matching pages by
#number needs and which is read from its page types
def level_problem(level, name, names, types):
    roles, a = [part.type for part in level.parts], grouping.a_record(name)
    key = (level.key or "").strip()
    return ("A level's name is a word or two, like survey or letter." if not (len(name) <= 40 and LEVEL_NAME.fullmatch(name)) else
            f"There is already a level called {name}." if name in names else
            "A level's page types must be this series' own." if any(t not in types for t in roles) else
            f"Unknown pages aren't read, so {a} can't be made of them." if any(types[t].unknown for t in roles) else
            f"Each page type is in {a} once." if len(set(roles)) < len(roles) else
            f"The first page type starts {a}, and only it." if any((p.how == "starts") != (i == 0) for i, p in enumerate(level.parts)) else
            "A field name is lower-case letters, digits and _, starting with a letter." if key and not instructions.KEY.fullmatch(key) else
            f"Pages are matched to {a} by its number field: set one first." if any(p.how == "matched" for p in level.parts) and not key else
            f"{a.capitalize()}'s number is read from its page types: add one first, or choose no number field." if key and not level.parts else None)

#a collection's levels of record as they would be stored, top first, unsaved; refused with the first problem (level_problem),
#and a level's number field must be a field of its own (not a list or group) in the templates of the page types that start one
#or are matched to it
def checked_levels(db, collection_id, levels):
    if not db.get(models.Collection, collection_id):
        raise HTTPException(status_code=404, detail="No such series.")
    types = {t.name: t for t in db.query(models.PageType).filter_by(collection_id=collection_id)}
    templates, rows = instructions.newest(db), []
    for position, level in enumerate(levels, start=1):
        name, key = " ".join(level.name.lower().split()), (level.key or "").strip() or None
        if problem := level_problem(level, name, {row.name for row in rows}, types):
            raise HTTPException(status_code=400, detail=problem)
        missing = sorted(types[p.type].label for p in level.parts if p.how != "follows" and key and p.type in templates
                         and not isinstance(json.loads(templates[p.type].body).get(key, []), str | None))
        if missing:
            raise HTTPException(status_code=400, detail=f"These page types' templates don't have '{key}': {', '.join(missing)}.")
        rows.append(models.RecordLevel(collection_id=collection_id, position=position, name=name, record_key=key,
                                       parts=json.dumps([part.model_dump() for part in level.parts])))
    return rows

#a collection's levels of record, top first, in place of the ones it had. Items read from now on group by them
@app.put("/collections/{collection_id}/levels")
def put_levels(collection_id: int, payload: LevelsSettings, db: Session = Depends(get_db)):
    write_lock(db)
    rows = checked_levels(db, collection_id, payload.levels)
    db.query(models.RecordLevel).filter_by(collection_id=collection_id).delete()
    db.add_all(rows)
    db.commit()
    return collection_json(db.get(models.Collection, collection_id), db)

#how one of a collection's items already read would group by these levels, saving nothing: the records grouping would make,
#parents first, each its id, the record it sits in and its pages; the pages in none; each page's type; and the problems
#grouping would flag, each on a page, with the record it's about (none: pages in no record) and what it is.
#It reads the item's page types and its pages' number fields as reviewers last saved them, as the group step does a run's; a
#page waiting to be read again as another type has none yet
@app.post("/collections/{collection_id}/levels/preview")
def preview_levels(collection_id: int, payload: LevelsPreview, db: Session = Depends(get_db)):
    from backend.pipeline.run import Run, step_group
    rows = checked_levels(db, collection_id, payload.levels)
    bundle = db.get(models.Bundle, payload.item)
    if not bundle or bundle.collection_id != collection_id:
        raise HTTPException(status_code=404, detail="No such item read in this series.")
    ids = [page_id for (page_id,) in db.query(models.Page.page_id).filter_by(bundle_id=bundle.bundle_id).order_by(models.Page.page_id)]
    unread = {page_id for (page_id,) in db.query(models.Page.page_id).filter_by(bundle_id=bundle.bundle_id, needs_transcription=True)}
    keys, values = {row.record_key for row in rows if row.record_key}, {}
    for page_id, key, text in db.query(models.Field.page_id, models.Field.field_title, models.Field.text_raw).filter(
            models.Field.page_id.in_(ids), models.Field.field_title.in_(keys)):
        values.setdefault(page_id, {})[key] = text
    for edit in db.query(models.Edit).filter(models.Edit.page_id.in_(ids), models.Edit.field_title.in_(keys)).order_by(models.Edit.edit_id):
        values.setdefault(edit.page_id, {})[edit.field_title] = edit.edit_text
    categories = dict(db.query(models.Page.page_id, models.Page.category).filter_by(bundle_id=bundle.bundle_id))
    types = db.query(models.PageType).filter_by(collection_id=collection_id).all()
    labels = {t.name: t.label for t in types}
    run = Run(Path(f"{bundle.bundle_id}.pdf"), Path(bundle.bundle_id), grouping={
        "levels": [grouping.level_json(row) for row in rows],
        "labels": labels, "unknown": [t.name for t in types if t.unknown]})
    run.pages = [{"file": f"{page_id}.png", "label": categories[page_id], "values": {} if page_id in unread else values.get(page_id, {}),
                  "id": page_id} for page_id in ids]
    step_group(run)
    problems = [{"page": entry["file"].removesuffix(".png"), "record": entry.get("record"),
                 "reason": entry["reason"].split(": ", 1)[-1] if entry.get("record") else entry["reason"]} for entry in run.review]
    return {"records": [{**record, "pages": [p["id"] for p in run.pages if p["survey"] == record["id"]]} for record in run.records],
            "loose": [p["id"] for p in run.pages if p["survey"] is None],
            "pageTypes": {page_id: labels.get(category, category) for page_id, category in categories.items()}, "problems": problems}

#a series on the archive, to check before a collection links to it
@app.get("/archive-series/{node}")
def get_archive_series(node: int):
    try:
        series = scans.archive_series(node)
    except scans.ARCHIVE_ERRORS as error:
        raise HTTPException(status_code=502, detail=f"Couldn't reach the archive ({error}).")
    if series is None:
        raise HTTPException(status_code=404, detail="The archive has no page with that number.")
    return series

#a series' items on the archive, a page of 24 at a time, each saying whether it has scans and whether a series lists it already
@app.get("/collections/{collection_id}/archive-items")
def list_archive_items(collection_id: int, page: int = 1, search: str = "", db: Session = Depends(get_db)):
    c = linked_collection(db, collection_id)
    try:
        listing = scans.archive_listing(scans.listing_link(c.archive_series), max(page, 1), search.strip()[:200])
    except scans.ARCHIVE_ERRORS as error:
        raise HTTPException(status_code=502, detail=f"Couldn't reach the archive ({error}).")
    added = {node for (node,) in db.query(models.ArchiveItem.node)}
    return {**listing, "items": [{**item, "added": item["node"] in added} for item in listing["items"]]}

class NewItems(BaseModel):
    nodes: list[int]

#adds up to 25 of a series' archive items to its list, each checked on the archive first to be an item of this series; an item
#another series lists already, or that the archive doesn't show, is said why instead. Its PDF is looked up when it is run.
@app.post("/collections/{collection_id}/items")
def add_items(collection_id: int, payload: NewItems, db: Session = Depends(get_db)):
    c = linked_collection(db, collection_id)
    nodes = list(dict.fromkeys(payload.nodes))
    if not 1 <= len(nodes) <= 25:
        raise HTTPException(status_code=400, detail="Add between 1 and 25 items at a time.")
    if not all(0 < node < 2**31 for node in nodes):
        raise HTTPException(status_code=400, detail="An item's number is a whole number from 1.")
    try:  #the series' identifier, as linked or else as the archive has it, to check each item's against
        series = c.archive_identifier or (scans.archive_series(c.archive_series) or {}).get("identifier")
    except scans.ARCHIVE_ERRORS as error:
        raise HTTPException(status_code=502, detail=f"Couldn't reach the archive ({error}).")
    if not series:
        raise HTTPException(status_code=400, detail="The archive shows no identifier for this series to check items against.")
    listed = {node for (node,) in db.query(models.ArchiveItem.node).filter(models.ArchiveItem.node.in_(nodes))}
    rows, added, refused = [], [], []
    for node in nodes:
        if node in listed:
            refused.append({"node": node, "reason": "A series lists it already."})
            continue
        try:
            item = scans.archive_item(node)
        except scans.ARCHIVE_ERRORS as error:
            refused.append({"node": node, "reason": f"Couldn't reach the archive ({error})."})
            continue
        reason = ("The archive has no item with that number." if item is None else
                  "It belongs to another series on the archive." if not item["series"].startswith(f"[{series}]") else None)
        if reason:
            refused.append({"node": node, "reason": reason})
        else:
            rows.append(models.ArchiveItem(node=node, collection_id=collection_id, identifier=item["identifier"], title=item["title"],
                                           pdf=f"{node}/{node}.pdf"))
            added.append({"node": node, "title": item["title"]})
    write_lock(db)
    db.add_all(rows)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A series listed one of these items while they were being checked. Try again.")
    return {"added": added, "refused": refused}

class AllItems(BaseModel):
    search: str = ""

#queues the worker to add every item of a series' list on the archive (the whole list, or a search's results) that can be
#downloaded and that no series lists yet, trusting the archive's list for which series they are in (worker.add_items)
@app.post("/collections/{collection_id}/items/all", status_code=202)
def add_all_items(collection_id: int, payload: AllItems, db: Session = Depends(get_db)):
    linked_collection(db, collection_id)
    write_lock(db)
    if db.query(models.Job).filter(models.Job.kind == "items", models.Job.collection_id == collection_id,
                                   models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(status_code=409, detail="This series is already adding items.")
    job = models.Job(kind="items", collection_id=collection_id, search=payload.search.strip()[:200] or None)
    db.add(job)
    db.commit()
    return job_json(job)

def linked_collection(db, collection_id):
    c = db.get(models.Collection, collection_id)
    if not c:
        raise HTTPException(status_code=404, detail="No such series.")
    if not c.archive_series:
        raise HTTPException(status_code=400, detail="This series isn't linked to the archive.")
    return c

#reads a page again as another page type, replacing what was read off it: queued for the worker, or for other done now (an
#empty page to type into). A page with saved reviews keeps its type, as reading it again would lose them.
@app.put("/pages/{page_id:path}/type")
def change_page_type(page_id: str, payload: PageTypeChange, db: Session = Depends(get_db)):
    write_lock(db)
    page = db.get(models.Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    new_type = db.get(models.PageType, payload.pageType)
    if not new_type or new_type.collection_id != db.get(models.Bundle, page.bundle_id).collection_id:
        raise HTTPException(status_code=400, detail=f"No page type called {payload.pageType} in this page's series.")
    if not db.get(models.Reviewer, payload.reviewerId):
        raise HTTPException(status_code=400, detail=f"Unknown reviewer {payload.reviewerId}.")
    if payload.pageType == page.category:
        raise HTTPException(status_code=400, detail="The page is already that type.")
    if db.query(models.Edit).filter(models.Edit.page_id == page_id).first():
        raise HTTPException(status_code=409, detail="This page has saved reviews, which reading it again would lose.")
    if db.query(models.Job).filter(models.Job.page_id == page_id, models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(status_code=409, detail="This page is already waiting to be read again.")
    if new_type.unknown:
        loader.clear_content(page_id, db.connection())
        loader.insert_content(page_id, None, new_type.name, db.connection())
        page.category, page.revision_no = new_type.name, (page.revision_no or 0) + 1
        page.provider = page.model = page.effort = page.runtime = page.prompt_version_id = page.template_version_id = None
        db.commit()
        return {"pageType": page.category, "job": None}
    if payload.pageType not in instructions.newest(db):
        raise HTTPException(status_code=400, detail=f"Give {payload.pageType} a template first.")
    chosen = chosen_transcription(db, payload.provider, payload.model, payload.effort) #what's missing comes from the saved choice
    model, provider, effort = chosen["model"], chosen["provider"], chosen["effort"]
    if not model or len(model) > 200 or any(c.isspace() for c in model) or model.startswith("-") or "+" in model:
        raise HTTPException(400, "Select a valid model.")
    if provider not in ALL_PROVIDERS or not effort or len(effort) > 40 or any(c.isspace() for c in effort) or effort.startswith("-"):
        raise HTTPException(400, "Select a valid provider and effort.")
    job = models.Job(kind="page", page_id=page_id, page_type=payload.pageType, reviewer_id=payload.reviewerId,
                     **{f"transcription_{field}": value for field, value in chosen.items()})
    db.add(job)
    db.commit()
    return {"pageType": page.category, "job": job_json(job)}


#--PAGE SORTING--# (retrained with the pages reviewers settled; new bundles are sorted by the active model, else the shipped one)
class TrainRequest(BaseModel):
    reviewerId: int

class ActiveModelRequest(BaseModel):
    modelId: int | None #None: back to the shipped model
    reviewerId: int

def sorting_model_json(m, names):
    return {"id": m.model_id, "pageTypes": m.page_types.split(","), "pages": m.pages, "answered": m.answered, "wrong": m.wrong,
            "passed": m.passed, "active": m.active, "note": m.note, "reviewer": names.get(m.reviewer_id),
            "createdAt": m.created_at.replace(tzinfo=timezone.utc).isoformat() if m.created_at else ""}

#every retraining, newest first, with its check: pages each sorted by a model that never saw them, answered, wrong
@app.get("/sorting-models")
def get_sorting_models(db: Session = Depends(get_db)):
    names = dict(db.query(models.Reviewer.reviewer_id, models.Reviewer.name))
    return [sorting_model_json(m, names) for m in db.query(models.SortingModel).order_by(models.SortingModel.model_id.desc())]

#queues a retraining for the worker; a model that passes its check becomes the active one
@app.post("/sorting-models", status_code=202)
def train_sorting_model(payload: TrainRequest, db: Session = Depends(get_db)):
    if not db.get(models.Reviewer, payload.reviewerId):
        raise HTTPException(status_code=400, detail=f"Unknown reviewer {payload.reviewerId}.")
    write_lock(db)
    if db.query(models.Job).filter(models.Job.kind == "train", models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(status_code=409, detail="Page sorting is already waiting to be retrained.")
    job = models.Job(kind="train", reviewer_id=payload.reviewerId)
    db.add(job)
    db.commit()
    return job_json(job)

#makes a model that passed its check the one new bundles use, or (None) goes back to the shipped model
@app.put("/sorting-models/active")
def set_active_sorting_model(payload: ActiveModelRequest, db: Session = Depends(get_db)):
    if not db.get(models.Reviewer, payload.reviewerId):
        raise HTTPException(status_code=400, detail=f"Unknown reviewer {payload.reviewerId}.")
    chosen = payload.modelId is not None and db.get(models.SortingModel, payload.modelId)
    if payload.modelId is not None and not chosen:
        raise HTTPException(status_code=404, detail="No such model.")
    if chosen and not chosen.passed:
        raise HTTPException(status_code=400, detail="That model failed its check, so it wasn't kept.")
    db.query(models.SortingModel).update({"active": False})
    if chosen:
        chosen.active = True
    db.commit()
    return {"active": payload.modelId}


#--PIPELINE JOBS--# (queued here, done by backend/worker.py)
#where the scans are read from and the results written, as absolute paths (inside the project)
@app.get("/folders")
def get_folders():
    return {key.lower(): str((ROOT / settings()[key]).resolve()) for key in ("DATA", "OUTPUT")}

#opens the scans' or the results' folder in Explorer or Finder, on the computer PrestCribe runs on
@app.post("/folders/{which}/open", status_code=204)
def open_folder(which: Literal["data", "output"]):
    import subprocess
    folder = (ROOT / settings()[which.upper()]).resolve()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"The folder couldn't be opened: {error}"[:300])

#a transcription's provider, model and effort: the ones given, else the saved choice; 409 when either is still missing
def chosen_transcription(db, provider, model, effort):
    saved = app_settings.transcription_defaults(db) or {}
    chosen = {field: given.strip() if given is not None else saved.get(field)
              for field, given in zip(app_settings.FIELDS, (provider, model, effort))}
    if None in chosen.values():
        raise HTTPException(status_code=409, detail=app_settings.NOT_SET)
    return chosen

def check_transcription(provider, model, effort):
    if not model or len(model) > 200 or any(c.isspace() for c in model) or model.startswith("-") or "+" in model:
        raise HTTPException(status_code=400, detail="Enter a valid model name.")
    if provider not in ALL_PROVIDERS:
        raise HTTPException(status_code=400, detail="Choose a provider.")
    if not effort or len(effort) > 40 or any(c.isspace() for c in effort) or effort.startswith("-"):
        raise HTTPException(status_code=400, detail="Enter a valid effort level.")

class StartJobRequest(BaseModel):
    model: str | None = None
    provider: str | None = None
    effort: str | None = None
    pdf: str #as listed by GET /bundles

#every runnable PDF, in order and one per bundle id, as (its stored path, bundle id, bundle number, the folder that numbers it):
#each survey PDF under DATA (the data folder), each DATA/<bundle number>/ folder of page images, and each of the archive's
#bundles whose PDF isn't there (the Prest survey's and those added to a series), as DATA/<bundle number>/<its PDF> (running it
#downloads the PDF). The archive's, which can be tens of thousands, are made from their names, without a path object each.
def runnables(db):
    data = ROOT / settings()["DATA"]
    here = list(data.rglob("*.pdf")) + [p for p in (data.iterdir() if data.is_dir() else ())
                                        if p.is_dir() and p.name.isdigit() and find_images(p)]
    names = {p.name for p in here}
    prefix = stored_path(data)
    under = (lambda pdf: prefix + os.sep + pdf.replace("/", os.sep)) if Path(prefix).is_absolute() else (lambda pdf: f"{prefix}/{pdf}")
    found = [(stored_path(p), p.stem, p.stem if p.parent == data else p.parent.name,
              p.parent.name if p.suffix.lower() == ".pdf" else p.name) for p in here]
    for pdf in archive_sources(db):
        number, _, file = pdf.rpartition("/")
        if file not in names:
            found.append((under(pdf), file.rsplit(".", 1)[0], number, number))
    once = {}
    for entry in sorted(found):
        once.setdefault(entry[1], entry)  #a PDF found twice: its first copy
    return list(once.values())

def job_json(job):
    return {"id": job.job_id, "kind": job.kind, "pdf": job.pdf, "pageId": job.page_id, "pageType": job.page_type,
            "status": job.status, "step": job.step,
            "donePages": job.done_pages, "totalPages": job.total_pages, "error": job.error, "collectionId": job.collection_id,
            "search": job.search, "updatedAt": job.updated_at.replace(tzinfo=timezone.utc).isoformat() if job.updated_at else ""}

#the worker's tasks for the Tasks panel, newest first: each waiting or running one, then the 20 latest done or failed
@app.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    active = db.query(models.Job).filter(models.Job.status.in_(("waiting", "running"))).order_by(models.Job.job_id.desc()).all()
    recent = (db.query(models.Job).filter(models.Job.status.in_(("done", "failed"))).order_by(models.Job.job_id.desc())
              .limit(20).all())
    owners, names = loader.archive_owners(db), dict(db.query(models.Collection.collection_id, models.Collection.name))
    return [task_json(db, job, owners, names) for job in active + recent]

#a task as its own page shows it: its lines in the worker's log from its last "started" line on, oldest first, each without its
#"job N" (an id can be another job's in an older db: a waiting task has none); the items its latest count line says it has added
#and skipped; an items task's series' items now; and whether a worker is running. worker.log rotates at 1 MB into worker.log.1 to
#.3, so an old task's lines may be gone.
@app.get("/jobs/{job_id}/log")
def job_log(job_id: int, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"There's no task {job_id}.")
    output = ROOT / settings()["OUTPUT"]
    line = re.compile(rf"(\d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ \w+ job {job_id}:? (.*)")
    found = [m.groups() for path in [output / f"worker.log.{n}" for n in (3, 2, 1)] + [output / "worker.log"] if path.is_file()
             for m in map(line.match, path.read_text(encoding="utf-8", errors="replace").splitlines()) if m]
    log = [{"time": datetime.strptime(at, "%Y-%m-%d %H:%M:%S").astimezone(timezone.utc).isoformat(), "text": text.strip()}
           for at, text in found]  #the worker logs local time
    started = [n for n, entry in enumerate(log) if entry["text"].startswith("started")]
    log = [] if job.status == "waiting" else log[started[-1]:] if started else log
    counts = next(filter(None, (re.search(r"([\d,]+) read, ([\d,]+) added", entry["text"]) for entry in reversed(log))), None)
    read, added = (int(n.replace(",", "")) for n in counts.groups()) if counts else (None, None)
    names = dict(db.query(models.Collection.collection_id, models.Collection.name))
    return {**task_json(db, job, loader.archive_owners(db), names), "log": log,
            "startedAt": log[0]["time"] if started and log else None,
            "added": added, "skipped": read - added if counts else None,
            "seriesItems": db.query(models.ArchiveItem).filter_by(collection_id=job.collection_id).count() if job.kind == "items" else None,
            "workerRunning": worker_running(output)}

#whether a worker is running, from how lately it touched its heartbeat (worker.beat); None if none has run since it got one
def worker_running(output):
    beat = output / "worker.alive"
    return datetime.now().timestamp() - beat.stat().st_mtime < 30 if beat.is_file() else None

#a task as the Tasks page shows it: what it is (label), its series, how far it has got, in items or pages, and where to see it (href)
def task_json(db, job, owners, names):
    series, href, unit = None, None, "pages"
    if job.kind == "items":
        series, unit = job.collection_id, "items"
        label = f"Adding items to {names.get(series, 'a series')}" + (f' matching "{job.search}"' if job.search else "")
        href = f"/?series={series}"
    elif job.kind == "bundle":
        path = PurePosixPath((job.pdf or "").replace("\\", "/"))
        number = path.parent.name if path.parent.name.isdigit() else path.stem
        series = loader.series_of(owners, job.pdf or "")
        item = db.get(models.ArchiveItem, int(number)) if number.isascii() and number.isdigit() and len(number) < 19 else None
        label, href = f"Transcribing {item.title if item else f'item {number}'}", f"/?series={series}&item={number}"
    elif job.kind == "page":
        page = db.get(models.Page, job.page_id)
        label = f"Reading page {job.page_id} again"
        if page:
            series = db.get(models.Bundle, page.bundle_id).collection_id
            href = f"/?survey={page.survey_id}&page={page.page_id}" if page.survey_id else f"/?series={series}"
    elif job.kind == "check":
        series, href = job.collection_id, f"/?series={job.collection_id}"
        label = f"Checking {names.get(series, 'a series')}"
    else:
        label = "Training page sorting"
    return {"id": job.job_id, "kind": job.kind, "label": label, "status": job.status, "step": job.step, "done": job.done_pages,
            "total": job.total_pages, "unit": unit, "error": job.error, "collectionId": series, "series": names.get(series), "href": href,
            "updatedAt": job.updated_at.replace(tzinfo=timezone.utc).isoformat() if job.updated_at else ""}

#a series' items, loaded or not, in order of their PDFs: bundle id, name (the bundle number: the PDF's folder), stored PDF,
#archive (its identifier and title when that number is one of the series' archive items), whether it's loaded, and latest job
#ponytail: made afresh each request (about 0.5 s for 60,000 items); keep it per db data_version, as cached_progress does, if slower
def series_items(db, collection):
    items = {str(node): {"identifier": identifier, "title": title} for node, identifier, title in
             db.query(models.ArchiveItem.node, models.ArchiveItem.identifier, models.ArchiveItem.title).filter_by(collection_id=collection)}
    owners = loader.archive_owners(db)
    loaded = {bundle_id for (bundle_id,) in db.query(models.Bundle.bundle_id).filter_by(collection_id=collection)}
    elsewhere = {bundle_id for (bundle_id,) in db.query(models.Bundle.bundle_id).filter(models.Bundle.collection_id != collection)}
    latest = {job.pdf: job for job in db.query(models.Job).order_by(models.Job.job_id)}
    rows = []
    for stored, bundle, name, folder in runnables(db):
        if bundle in elsewhere or (bundle not in loaded and owners.get(folder) != collection):
            continue
        job = latest.get(stored)
        rows.append({"pdf": stored, "bundle": bundle, "name": name, "archive": items.get(name), "loaded": bundle in loaded,
                     "job": job_json(job) if job else None})
    return rows

#every runnable PDF of a collection, as series_items, with its loaded survey ids
@app.get("/bundles")
def get_bundles(collection: int = 1, db: Session = Depends(get_db)):
    surveys = {}
    for survey_id, bundle_id in (db.query(models.Page.survey_id, models.Page.bundle_id)
                                 .filter(models.Page.survey_id.is_not(None))
                                 .group_by(models.Page.survey_id, models.Page.bundle_id)
                                 .order_by(func.min(models.Page.page_id))):
        surveys.setdefault(bundle_id, []).append(survey_id)
    return [{**row, "surveys": surveys.get(row["bundle"], [])} for row in series_items(db, collection)]

#how many of some pages there are, are in a record (reviewable), aren't, are reviewed and are ready to review, and how many
#records they make up
def page_counts(pages):
    reviewable = [p for p in pages if p.get("surveyId") is not None]
    return {"total": len(pages), "reviewable": len(reviewable), "unassigned": sum(p["status"] == "Not in a survey" for p in pages),
            "reviewed": sum(p["status"] == "Reviewed" for p in reviewable),
            "ready": sum(p["status"] == "Ready to review" for p in reviewable),
            "records": len({p["surveyId"] for p in reviewable})}

#an item's record when it is the whole item, all its pages; the dashboard opens it straight away. None: it has none or several
def whole_record(pages):
    records = {p.get("surveyId") for p in pages}
    return records.pop() if len(records) == 1 and None not in records else None

#each of a series' items' pages: a loaded one's as /progress gives them, one being transcribed its finished ones so far
def items_pages(db, collection, rows):
    loaded = {b["id"]: b["pages"] for b in cached_progress(db) if b["collectionId"] == collection}
    return {row["bundle"]: loaded.get(row["bundle"], []) if row["loaded"] else
            partial_pages(db, db.get(models.Job, row["job"]["id"])) if row["job"] and row["job"]["kind"] == "bundle" else []
            for row in rows}

#whether an item shows under the dashboard's search (its number, bundle id, title or identifier) and status
def item_matches(row, pages, search, status):
    if search not in " ".join([row["name"], row["bundle"], *(row["archive"] or {}).values()]).lower():
        return False
    if status == "All" or (status == "Awaiting transcription" and not row["loaded"]):
        return True
    if status == "Transcription in progress":
        return not row["loaded"] and (row["job"] or {}).get("status") == "running"
    if status == "Reviewed":
        counted = page_counts(pages)
        return counted["reviewable"] > 0 and counted["reviewed"] == counted["reviewable"]
    return any(p["status"] == status for p in pages)

#a page of a series' items for its dashboard: those its search and status match, in order of their numbers (216412 before
#2164120), each with its pages' counts and its record if it is one; with how many match, how many it has, how many of all its
#items are transcribed (loaded), the counts of all its pages, and the most pages and records any of its items has, so the dashboard
#leaves out a level none has more than one of
@app.get("/collections/{collection_id}/items")
def list_items(collection_id: int, page: int = 0, size: int = 9, search: str = "", status: str = "All", db: Session = Depends(get_db)):
    if not db.get(models.Collection, collection_id):
        raise HTTPException(status_code=404, detail="No such series.")
    rows = series_items(db, collection_id)
    pages = items_pages(db, collection_id, rows)
    search, size = search.strip().lower(), min(max(size, 1), 100)
    natural = lambda row: ((0, int(row["name"]), []) if row["name"].isdigit() else
                           (1, 0, [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", row["name"])]))
    matching = sorted((row for row in rows if item_matches(row, pages[row["bundle"]], search, status)), key=natural)
    page = min(max(page, 0), max(len(matching) - 1, 0) // size)
    return {"items": [{**row, "counts": page_counts(pages[row["bundle"]]), "record": whole_record(pages[row["bundle"]]) if row["loaded"] else None}
                      for row in matching[page * size:(page + 1) * size]],
            "page": page, "total": len(matching), "all": len(rows), "transcribed": sum(row["loaded"] for row in rows),
            "totals": page_counts([p for row in rows for p in pages[row["bundle"]]]),
            "most": {"pages": max((len(p) for p in pages.values()), default=0),
                     "records": max((page_counts(p)["records"] for p in pages.values()), default=0)}}

#one of a series' items, by its number or bundle id, with its pages as /progress gives them (none until it's loaded) and its
#records, each with the record it sits in (None: at the top)
@app.get("/collections/{collection_id}/items/{name}")
def get_item(collection_id: int, name: str, db: Session = Depends(get_db)):
    row = next((row for row in series_items(db, collection_id) if name in (row["name"], row["bundle"])), None)
    if row is None:
        raise HTTPException(status_code=404, detail="No such item.")
    records = db.query(models.Survey.survey_id, models.Survey.parent_id).filter_by(bundle_id=row["bundle"]).order_by(models.Survey.survey_id)
    return {**row, "pages": next((b["pages"] for b in cached_progress(db) if b["id"] == row["bundle"]), []),
            "records": [{"id": record, "parent": parent} for record, parent in records]}

_downloading = threading.Lock()  #ponytail: one item's PDF downloaded at a time; a second ask for it waits, then finds it here

#one of a series' archive items, by its number; 404 if the series doesn't list it
def series_item(db, collection_id, name):
    item = db.get(models.ArchiveItem, int(name)) if name.isascii() and name.isdigit() and len(name) < 10 else None
    if not item or item.collection_id != collection_id:
        raise HTTPException(status_code=404, detail="This series doesn't list that item.")
    return item

#where a series' archive item's PDF is, or goes once downloaded (as reading it puts it); 404 if the series doesn't list it
def item_pdf(db, collection_id, name):
    item = series_item(db, collection_id, name)
    pdf = item.pdf
    if not pdf:
        raise HTTPException(status_code=404, detail="There's no PDF of that item to get.")
    return ROOT / settings()["DATA"] / pdf

#how many pages an item has, to look at before it is read (a series set up on a sample): its PDF is downloaded from the
#archive first if it isn't here, into the place reading it would put it
@app.get("/collections/{collection_id}/items/{name}/scans")
def item_scans(collection_id: int, name: str, db: Session = Depends(get_db)):
    pdf = item_pdf(db, collection_id, name)
    if not pdf.is_file():
        with _downloading:
            if not pdf.is_file():
                try:
                    scans.fetch_pdf(pdf)
                except scans.ARCHIVE_ERRORS as error:
                    raise HTTPException(status_code=502, detail=f"Couldn't get its scans from the archive ({error}).")
    import pymupdf
    with pymupdf.open(pdf) as doc:
        return {"pages": doc.page_count}

#page n of an item's PDF as a JPEG, 240 pixels wide (kept drawn) or, asked for wider, 1200 (the browser keeps it); 404 until its
#PDF is here (item_scans)
@app.get("/collections/{collection_id}/items/{name}/scans/{n}")
def item_scan(collection_id: int, name: str, n: int, width: int = 240, db: Session = Depends(get_db)):
    large = width > 240
    image = n > 0 and scans.page_thumbnail(str(item_pdf(db, collection_id, name)), "", f"{name}_{n}", 1200 if large else 240, keep=not large)
    if not image:
        raise HTTPException(status_code=404, detail="No scan of this page here.")
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

class SuggestRequest(BaseModel):
    item: str #one of the series' items, by number
    count: int = Field(16, ge=1, le=30) #how many of its pages to show
    pick: Literal["spread", "random", "range"] = "spread"
    first: int | None = Field(None, ge=1) #the range, for pick "range"
    last: int | None = Field(None, ge=1)
    hint: str = Field("", max_length=1000) #told to the model as is

#page types suggested for a series by the transcription model (Settings), from some of one of its items' pages shown side by
#side (its PDF is downloaded first if it isn't here, as item_scans does); nothing is added: {pages, types: [{label, description,
#pages}]}. 409 until a transcription model is chosen; 502 when the model can't answer
@app.post("/collections/{collection_id}/page-types/suggest")
def suggest_page_types(collection_id: int, payload: SuggestRequest, db: Session = Depends(get_db)):
    from backend.pipeline.identify import suggest
    chosen = chosen_transcription(db, None, None, None)
    total = item_scans(collection_id, payload.item, db)["pages"]
    pages = suggest.pick(total, payload.count, payload.pick, payload.first, payload.last)
    if not pages:  #a range past the item's end, or ending before it starts
        raise HTTPException(status_code=400, detail=f"That item has {total} page{'' if total == 1 else 's'}: choose pages within them.")
    known = [t["label"] for t in get_page_types(collection_id, db) if not t["unknown"]]
    try:
        types = suggest.suggest(item_pdf(db, collection_id, payload.item), pages, chosen, known, payload.hint)
    except BaseException as error:  #a failed model call raises SystemExit
        if isinstance(error, (KeyboardInterrupt, GeneratorExit)):
            raise
        raise HTTPException(status_code=502, detail=f"Page types couldn't be suggested: {error}"[:400])
    return {"pages": pages, "types": types}

#the page types said of an item's pages before it is read (setting its series up on it): page number -> page type
@app.get("/collections/{collection_id}/items/{name}/labels")
def item_labels(collection_id: int, name: str, db: Session = Depends(get_db)):
    item = series_item(db, collection_id, name)
    return {str(label.page): label.page_type for label in db.query(models.SampleLabel).filter_by(node=item.node)}

class SampleLabelRequest(BaseModel):
    pageType: str | None #None: unsaid

#says which of its series' page types (not its Unknown one) a page of an item is, or unsays it; its labels as item_labels
@app.put("/collections/{collection_id}/items/{name}/labels/{page}")
def label_page(collection_id: int, name: str, page: int, payload: SampleLabelRequest, db: Session = Depends(get_db)):
    write_lock(db)
    item = series_item(db, collection_id, name)
    if not 0 < page < 100_000:
        raise HTTPException(status_code=400, detail="A page is numbered from 1.")
    page_type = payload.pageType and db.get(models.PageType, payload.pageType)
    if payload.pageType and (not page_type or page_type.collection_id != collection_id or page_type.unknown):
        raise HTTPException(status_code=400, detail=f"No page type called {payload.pageType} in this series.")
    label = db.get(models.SampleLabel, (item.node, page))
    if not payload.pageType:
        if label:
            db.delete(label)
    elif label:
        label.page_type = payload.pageType
    else:
        db.add(models.SampleLabel(node=item.node, page=page, page_type=payload.pageType))
    db.commit()
    return item_labels(collection_id, name, db)

#queues a pipeline run of one PDF; the worker picks it up
@app.post("/jobs", status_code=202)
def start_job(payload: StartJobRequest, db: Session = Depends(get_db)):
    pdf = next((found for found in runnables(db) if found[0] == payload.pdf), None)
    if pdf is None:
        raise HTTPException(status_code=404, detail="No such PDF in DATA or on the archive.")
    write_lock(db)
    #a rerun could lose saved reviews
    if db.query(models.Bundle).filter(models.Bundle.bundle_id == pdf[1]).first():
        raise HTTPException(status_code=409, detail="This item is already loaded.")
    if db.query(models.Job).filter(models.Job.pdf == payload.pdf, models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(status_code=409, detail="This item is already waiting or running.")

    chosen = chosen_transcription(db, payload.provider, payload.model, payload.effort)
    check_transcription(**chosen)
    job = models.Job(pdf=payload.pdf, **{f"transcription_{field}": value for field, value in chosen.items()})
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


#each db file's last progress answer, with the data_version it was worked out at, and the connection that reads it
_progress, _watchers, _progress_lock = {}, {}, threading.Lock()


@app.get("/progress")
def get_progress(collection: int | None = None, db: Session = Depends(get_db)):
    progress = cached_progress(db)
    return [b for b in progress if collection is None or b["collectionId"] == collection]

def cached_progress(db):
    from backend.api.progress import review_progress
    path = db.get_bind().url.database
    #an in-memory db can't be watched from another connection
    if not path or path == ":memory:":
        return review_progress(db)
    #data_version changes when any other connection or process commits; the watcher never writes, so it sees every change
    with _progress_lock:
        if path not in _watchers:
            _watchers[path] = sqlite3.connect(path, check_same_thread=False, timeout=15)
        version = _watchers[path].execute("PRAGMA data_version").fetchone()[0]
        if path not in _progress or _progress[path][0] != version:
            _progress[path] = (version, review_progress(db))
        return _progress[path][1]


@app.get("/transcription-models")
def get_transcription_models(db: Session = Depends(get_db)):
    columns = (models.Page.provider, models.Page.model, models.Page.effort,
               models.Page.prompt_version_id, models.Page.template_version_id)
    rows = (db.query(*columns, func.count(models.Page.page_id), func.avg(models.Page.runtime))
            .filter(models.Page.model.is_not(None)).group_by(*columns)
            .order_by(models.Page.provider, models.Page.model, models.Page.effort))
    return {"configured": app_settings.transcription_defaults(db),
            "models": [{"provider": provider, "model": model, "effort": effort,
                        "promptVersion": prompt, "templateVersion": template,
                        "pages": pages, "averageSeconds": float(seconds) if seconds is not None else None}
                       for provider, model, effort, prompt, template, pages, seconds in rows]}


class TranscriptionDefaults(BaseModel):
    provider: str
    model: str
    effort: str

#the choice every transcription started without one uses (POST /jobs, the worker and the command line)
@app.put("/transcription-defaults")
def put_transcription_defaults(payload: TranscriptionDefaults, db: Session = Depends(get_db)):
    provider, model, effort = payload.provider.strip(), payload.model.strip(), payload.effort.strip()
    check_transcription(provider, model, effort)
    write_lock(db) #two saves at once can't both insert the same keys
    app_settings.save_transcription_defaults(db, provider, model, effort)
    return app_settings.transcription_defaults(db)


@app.get("/jobs/{job_id}/transcripts")
def get_job_transcripts(job_id: int, db: Session = Depends(get_db)):
    """Read completed, checksum-verified page outputs without loading a partial bundle."""
    job = db.get(models.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    if job.kind != "bundle" or not job.pdf:
        raise HTTPException(status_code=400, detail="This job is not an item transcription.")
    return {"jobId": job_id, "status": job.status, "pages": partial_pages(db, job)}

#an item transcription's pages so far, from its run's folder: each one's id, type, status and what was read off it
def partial_pages(db, job):
    from pathlib import Path
    from backend.pipeline.run import read_manifest, digest
    folder = ROOT / settings()["OUTPUT"] / Path(job.pdf).stem
    manifest = read_manifest(folder)
    pages = []
    for name, saved in (manifest.get("transcripts") or {}).items():
        if not isinstance(saved, dict) or Path(name).name != name:
            continue
        path = folder / "transcribe" / f"{Path(name).stem}.json"
        try:
            if digest(path) != saved.get("result"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pages.append({"id": Path(name).stem, "category": saved.get("request", {}).get("label"), "data": data})
    completed = {page["id"]: page for page in pages}
    identified = {Path(page["file"]).stem: page for page in manifest.get("pages", []) if page.get("file")}
    # Published page images are available before identification completes.
    extracted = {path.stem for path in (folder / "pages").glob("*.png")}
    unknown = {name for (name,) in db.query(models.PageType.name).filter(models.PageType.unknown)}
    result = []
    for page_id in sorted(extracted | identified.keys() | completed.keys()):
        page = completed.get(page_id)
        category = identified.get(page_id, {}).get("label") or (page or {}).get("category") or "unidentified"
        status = ("Transcribed — not grouped" if page else
                  "Not required" if category == "blank" else
                  "Needs identification" if category in {"unidentified", "review", *unknown} else
                  "Awaiting transcription")
        result.append({"id": page_id, "category": category, "status": status,
                       "data": page["data"] if page else None})
    return result


def export_survey(survey_id: str, request: Request, db: Session):
    survey_id = survey_id.strip()
    if not survey_id:
        raise HTTPException(status_code=400, detail="Enter a survey ID.")
    survey = get_survey(survey_id, request, db)
    reviews = get_reviews(survey_id, db)["reviews"]
    pages = []
    for page in survey["pages"]:
        fields = []
        for field in page["fields"]:
            saved = reviews.get(page["id"], {}).get(field["id"])
            reviewed = bool(saved and saved.get("savedAt"))
            fields.append({
                **field,
                "value": saved["value"] if reviewed else field["value"],
                **({"decoded": saved.get("decoded")} if reviewed and "decoded" in field else {}),
                "status": "Reviewed" if reviewed else "ToBeReviewed",
            })
        pages.append({
            "pageId": page["id"],
            "label": page["type"],
            "status": "Reviewed" if fields and all(
                field["status"] == "Reviewed" for field in fields
            ) else "ToBeReviewed",
            "fields": fields,
            "flags": page["flags"],
        })
    return {"surveys": [{
        "surveyId": survey_id,
        "parentId": survey["parentId"],
        "status": "Reviewed" if pages and all(
            page["status"] == "Reviewed" for page in pages
        ) else "ToBeReviewed",
        "pages": pages,
    }]}


@app.get("/export/bundles")
def export_bundles(collection: int | None = None, db: Session = Depends(get_db)):
    from pathlib import PurePosixPath
    bundles = db.query(models.Bundle).order_by(models.Bundle.bundle_id)
    return [{"id": b.bundle_id, "name": PurePosixPath(b.source_pdf.replace("\\", "/")).parent.name or b.bundle_id}
            for b in (bundles if collection is None else bundles.filter_by(collection_id=collection))]


@app.get("/export")
def download_export(request: Request, survey_id: str | None = None, bundle_id: str | None = None,
                    db: Session = Depends(get_db)):
    if (survey_id is None) == (bundle_id is None):
        raise HTTPException(status_code=400, detail="Choose a survey ID or an item.")
    if survey_id is not None:
        return export_survey(survey_id, request, db)
    bundle_id = bundle_id.strip()
    if not bundle_id:
        raise HTTPException(status_code=400, detail="Choose an item.")
    if not db.get(models.Bundle, bundle_id):
        raise HTTPException(status_code=404, detail="Item not found.")
    surveys = []
    #a record holding only records, no pages of its own, has nothing to export; theirs name it as their parent
    parents = db.query(models.Survey.parent_id).filter(models.Survey.parent_id.is_not(None))
    for (sid,) in (db.query(models.Survey.survey_id).filter_by(bundle_id=bundle_id).order_by(models.Survey.survey_id)
                   .filter(or_(models.Survey.survey_id.in_(db.query(models.Page.survey_id)), models.Survey.survey_id.not_in(parents)))):
        surveys.extend(export_survey(sid, request, db)["surveys"])
    # Unassigned pages have no saved survey reviews, but remain in the download.
    unassigned = []
    for page in db.query(models.Page).filter_by(bundle_id=bundle_id, survey_id=None).order_by(models.Page.page_id):
        fields = page_fields(db, page)
        unassigned.append({"pageId": page.page_id, "label": page.category,
                           "status": "ToBeReviewed", "reason": "No survey assignment",
                           "fields": [{**f, "status": "ToBeReviewed"} for f in fields],
                           "flags": page_flags(db, page, fields)})
    return {"bundleId": bundle_id, "surveys": surveys, "unassignedPages": unassigned}

#an item's export in the archive's shape (series > item > page): the series' archive item its number names (None fields if it
#names none), and its pages in the item's own order, each with the number of the record it sits in (in order of first page)
#ponytail: a nested record gets its own number and no link to its parent; add the parent's number if the import needs the tree
def archive_item(collection, bundle, request, db):
    number = PurePosixPath(bundle.source_pdf.replace("\\", "/")).parent.name or bundle.bundle_id
    item = (db.query(models.ArchiveItem).filter_by(node=int(number), collection_id=collection.collection_id).first()
            if number.isascii() and number.isdigit() and len(number) < 19 else None)
    export = download_export(request, bundle_id=bundle.bundle_id, db=db)
    def page_number(page):
        return int(page["pageId"].rsplit("_", 1)[1])  #the number scans.page_scan fetches it by
    first = {s["surveyId"]: min(map(page_number, s["pages"])) for s in export["surveys"] if s["pages"]}
    records = {survey: n for n, survey in enumerate(sorted(first, key=first.get), 1)}
    pages = []
    for survey, page in ([(s["surveyId"], p) for s in export["surveys"] for p in s["pages"]]
                         + [(None, p) for p in export["unassignedPages"]]):
        decoded = {f["id"]: f["decoded"] for f in page["fields"] if f.get("decoded") is not None}
        pages.append({"page": page_number(page), "pageType": page["label"], "record": records.get(survey),
                      "reviewed": page["status"] == "Reviewed", "fields": {f["id"]: f["value"] for f in page["fields"]},
                      **({"decoded": decoded} if decoded else {})})
    return {"series": {"name": collection.name, "identifier": collection.archive_identifier, "node": collection.archive_series,
                       "title": collection.archive_title},
            "item": {"number": number, "identifier": item and item.identifier, "node": item and item.node,
                     "title": item and item.title},
            "pages": sorted(pages, key=lambda page: page["page"])}

#the series and the bundles loaded into it, or the 404 that says why there is nothing to export
def series_bundles(collection_id, db):
    collection = db.get(models.Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="No such series.")
    bundles = db.query(models.Bundle).filter_by(collection_id=collection_id).order_by(models.Bundle.bundle_id).all()
    if not bundles:
        raise HTTPException(status_code=404, detail="Nothing in this series is transcribed yet.")
    return collection, bundles

#a transcribed series as a zip of <series identifier>/<item identifier>.json, one file per item, items in number order, and the zip's
#file name; step() is called after each item is done
def series_zip(collection, bundles, request, db, step=lambda: None):
    items = []
    for bundle in bundles:
        items.append(archive_item(collection, bundle, request, db))
        step()
    def by_number(item):  #numbers numerically, then names that aren't numbers
        number = item["item"]["number"]
        return (0, int(number), "") if number.isascii() and number.isdigit() else (1, 0, number)
    items.sort(key=by_number)
    folder = collection.archive_identifier or re.sub(r"[^A-Za-z0-9_-]", "_", collection.name)
    #ponytail: built in memory; two bundles in one item folder share a file name, and the later replaces the earlier
    files = {f"{folder}/{i['item']['identifier'] or i['item']['number']}.json": json.dumps(i, indent=2, ensure_ascii=False)
             for i in items}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue(), f"{folder}.zip"

def zip_response(data, filename):
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.get("/collections/{collection_id}/export")
def export_series(collection_id: int, request: Request, db: Session = Depends(get_db)):
    collection, bundles = series_bundles(collection_id, db)
    return zip_response(*series_zip(collection, bundles, request, db))

#a series' zips being prepared, by id: {"collection", "done", "total"}, then "zip" (the bytes and file name) or "error" once finished
#ponytail: kept in this process's memory, so lost on restart and never expired if never collected; move it to the jobs table
#if exports need to outlive the API or the dialog
series_exports = {}

def build_series_export(build, collection_id, request, bind):
    with Session(bind=bind) as db:  #its own session: the request's closes with the request, and one session is for one thread
        try:
            collection, bundles = series_bundles(collection_id, db)
            def step():
                build["done"] += 1
            build["zip"] = series_zip(collection, bundles, request, db, step)
        except Exception as error:
            build["error"] = str(error)

#starts preparing a series' zip, which GET .../export/<id> reports on and then hands over
@app.post("/collections/{collection_id}/export", status_code=202)
def start_series_export(collection_id: int, request: Request, db: Session = Depends(get_db)):
    total = len(series_bundles(collection_id, db)[1])
    build_id = uuid.uuid4().hex
    build = series_exports[build_id] = {"collection": collection_id, "done": 0, "total": total}
    threading.Thread(target=build_series_export, args=(build, collection_id, request, db.get_bind()), daemon=True).start()
    return {"id": build_id, "total": total}

#how far a zip has got, or the zip (or why it failed) once it is done, after which it is forgotten
@app.get("/collections/{collection_id}/export/{build_id}")
def series_export_progress(collection_id: int, build_id: str):
    build = series_exports.get(build_id)
    if build is None or build["collection"] != collection_id:
        raise HTTPException(status_code=404, detail="No such export.")
    if "error" in build:
        series_exports.pop(build_id, None)
        raise HTTPException(status_code=500, detail=f"The export failed: {build['error']}")
    if "zip" in build:
        series_exports.pop(build_id, None)
        return zip_response(*build["zip"])
    return {"done": build["done"], "total": build["total"]}


class MovePageRequest(BaseModel):
    surveyId: str
    sourceSurveyId: str
    reviewerId: int
    revision: int
    reason: str = ""

@app.get("/page-actions/{page_id:path}")
def page_action_context(page_id: str, db: Session = Depends(get_db)):
    page = db.get(models.Page, page_id)
    if page is None:
        raise HTTPException(404, "Page not found.")
    surveys = db.query(models.Survey).filter(models.Survey.bundle_id == page.bundle_id).order_by(models.Survey.survey_id).all()
    job = db.query(models.Job).filter(models.Job.page_id == page_id, models.Job.kind == "page").order_by(models.Job.job_id.desc()).first()
    types = db.query(models.PageType).filter_by(collection_id=db.get(models.Bundle, page.bundle_id).collection_id)         .order_by(models.PageType.built_in.desc(), models.PageType.name)
    return {"bundleId": page.bundle_id, "surveyId": page.survey_id, "category": page.category,
            "pageTypes": [{"name": t.name, "label": t.label} for t in types], #what it can be changed to: its collection's types
            "needsTranscription": page.needs_transcription, "revision": page.revision_no or 0, "hasReviews": bool(db.query(models.Edit).filter_by(page_id=page_id).first()),
            "job": job_json(job) if job else None,
            "surveys": [{"id": s.survey_id, "pages": [{"id": p.page_id, "type": p.category} for p in
                         db.query(models.Page).filter_by(survey_id=s.survey_id).order_by(models.Page.page_id)]} for s in surveys]}

@app.put("/page-moves/{page_id:path}")
def move_page(page_id: str, payload: MovePageRequest, db: Session = Depends(get_db)):
    write_lock(db)
    page = db.get(models.Page, page_id)
    target = db.get(models.Survey, payload.surveyId)
    if page is None or target is None:
        raise HTTPException(404, "Page or destination record not found.")
    if not db.get(models.Reviewer, payload.reviewerId):
        raise HTTPException(400, "Select a valid reviewer.")
    if target.bundle_id != page.bundle_id:
        raise HTTPException(400, "Pages can only move within the same item.")
    if target.survey_id == page.survey_id:
        raise HTTPException(400, f"Choose a different {page_record_name(db, page)}.")
    if page.survey_id != payload.sourceSurveyId or (page.revision_no or 0) != payload.revision:
        raise HTTPException(409, "This page changed. Refresh before moving it.")
    if db.query(models.Job).filter(models.Job.page_id == page_id, models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(409, "Wait for this page's transcription to finish before moving it.")
    db.add(models.PageMove(page_id=page_id, from_survey=page.survey_id, to_survey=target.survey_id,
                           reviewer_id=payload.reviewerId, reason=payload.reason.strip()))
    left = [p for (p,) in db.query(models.Page.page_id).filter(models.Page.survey_id == page.survey_id, models.Page.page_id != page_id)]
    page.survey_id = target.survey_id
    if page.checked_revision == (page.revision_no or 0):
        page.checked_revision = (page.revision_no or 0) + 1
    page.revision_no = (page.revision_no or 0) + 1
    db.flush()
    checks.check_pages(db.connection(), [page_id, *left[:1]])  #its new record, and the one it left (a page of it brings the rest)
    db.commit()
    return {"surveyId": page.survey_id, "pageId": page_id}


class PageClassificationRequest(BaseModel):
    pageType: str
    reviewerId: int
    revision: int

class PageTranscriptionRequest(BaseModel):
    reviewerId: int
    revision: int
    model: str
    provider: str
    effort: str

def actionable_page(db, page_id, reviewer_id, revision):
    write_lock(db)
    page = db.get(models.Page, page_id)
    if page is None:
        raise HTTPException(404, "Page not found.")
    if not db.get(models.Reviewer, reviewer_id):
        raise HTTPException(400, "Select a valid reviewer.")
    if (page.revision_no or 0) != revision:
        raise HTTPException(409, "This page changed. Refresh and try again.")
    if db.query(models.Job).filter(models.Job.page_id == page_id, models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(409, "This page already has a queued or running transcription.")
    return page

@app.put("/page-classification/{page_id:path}")
def classify_page(page_id: str, payload: PageClassificationRequest, db: Session = Depends(get_db)):
    page = actionable_page(db, page_id, payload.reviewerId, payload.revision)
    new_type = db.get(models.PageType, payload.pageType)
    if not new_type or new_type.collection_id != db.get(models.Bundle, page.bundle_id).collection_id:
        raise HTTPException(400, f"No page type called {payload.pageType} in this page's series.")
    if payload.pageType == page.category:
        raise HTTPException(400, "The page is already that type.")
    from backend.db.page_history import snapshot
    snapshot(db, page_id, payload.reviewerId, "change_type")
    page.category = payload.pageType
    # An Unknown type's pages wait, unread, for a reviewer to pick their type.
    page.needs_transcription = not new_type.unknown
    page.revision_no = (page.revision_no or 0) + 1
    page.checked_revision = None
    db.flush()
    checks.check_pages(db.connection(), [page_id])  #its old type's rule flags go; its new type's rules apply to what it holds
    db.commit()
    return {
        "pageType": page.category,
        "needsTranscription": page.needs_transcription,
    }


@app.post("/page-transcription/{page_id:path}")
def transcribe_page(page_id: str, payload: PageTranscriptionRequest, db: Session = Depends(get_db)):
    page = actionable_page(db, page_id, payload.reviewerId, payload.revision)
    if page.category not in instructions.newest(db):
        raise HTTPException(400, f"No transcription template is configured for {page.category}. Choose a page type with a template first.")
    if not payload.model.strip() or len(payload.model) > 200 or any(c.isspace() for c in payload.model) or payload.model.startswith("-") or "+" in payload.model:
        raise HTTPException(400, "Enter a valid model name.")
    if payload.provider not in ALL_PROVIDERS or not payload.effort or len(payload.effort) > 40 or any(c.isspace() for c in payload.effort) or payload.effort.startswith("-"):
        raise HTTPException(400, "Enter a valid provider and effort.")
    job = models.Job(kind="page", page_id=page_id, page_type=page.category, reviewer_id=payload.reviewerId,
                     base_revision=page.revision_no or 0, transcription_model=payload.model,
                     transcription_provider=payload.provider, transcription_effort=payload.effort)
    db.add(job)
    db.commit()
    return {"job": job_json(job)}


@app.get("/page-history/{page_id:path}")
def get_page_history(page_id: str, db: Session = Depends(get_db)):
    """Read-only timeline. Snapshots describe content BEFORE the recorded action."""
    page = db.get(models.Page, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")
    names = dict(db.query(models.Reviewer.reviewer_id, models.Reviewer.name))
    events = []
    def event(kind, identity, time, reviewer, title, details, snapshot=None, changes=None):
        events.append(dict(id=f"{kind}-{identity}", time=time.replace(tzinfo=timezone.utc).isoformat() if time else None,
                           reviewer=names.get(reviewer, "Unknown reviewer"), title=title, details=details, snapshot=snapshot, changes=changes or []))
    for version in db.query(models.PageVersion).filter_by(page_id=page_id):
        content = json.loads(version.snapshot)
        previous = next(iter(content.get("pages", [])), {})
        event("version", version.version_id, version.time, version.reviewer_id,
              "Page type changed" if version.action == "change_type" else "Page retranscribed",
              f"Previous page type: {previous.get('category', 'Unknown')}. Previous revision: {previous.get('revision_no', 'Unknown')}.", content)
    for move in db.query(models.PageMove).filter_by(page_id=page_id):
        event("move", move.move_id, move.time, move.reviewer_id, f"Moved to another {page_record_name(db, page)}",
              f"{move.from_survey or 'Unassigned'} → {move.to_survey}" + (f". Reason: {move.reason}" if move.reason else ""))
    previous_values = {}
    for edit in db.query(models.Edit).filter_by(page_id=page_id).order_by(models.Edit.edit_id):
        field, original = edited_field(db, edit)
        previous = previous_values.get(field, original)
        previous_values[field] = edit.edit_text
        event("edit", edit.edit_id, edit.time, edit.reviewer_id, "Field review saved",
              f"{field}: {previous or '—'} → {edit.edit_text or '—'}",
              changes=[{"field": field, "previous": previous, "saved": edit.edit_text}])
    events.sort(key=lambda item: (item["time"] or "", item["id"]), reverse=True)
    return {"pageId": page_id, "revision": page.revision_no, "events": events}


#--A PRESTCRIBE FILE--# everything this copy of PrestCribe has (series, their setup, transcriptions, reviews, people), to open in
#another; the scans aren't in it: the other gets them from the archive as it needs them, or they're imported again
#what a setup-only PrestCribe file leaves out: every page and what was read off it, the records and items read, tasks, and this
#computer's own choices (its transcription model, page sorting and sorting models)
NOT_SETUP = ("edits", "flags", "annotations", "resident_fields", "residents", "other_children", "fields", "page_moves",
             "page_versions", "pages", "surveys", "bundles", "jobs", "sorting_models", "app_settings")

@app.get("/state")
def save_state(content: Literal["everything", "setup"] = "everything", db: Session = Depends(get_db)):
    import shutil, tempfile
    from starlette.background import BackgroundTask
    folder = tempfile.mkdtemp()
    copy = Path(folder) / "state.db"
    with sqlite3.connect(copy) as out:
        db.connection().connection.driver_connection.backup(out)
        if content == "setup":  #the series and how they're read, to start reading again from scratch
            out.execute("PRAGMA foreign_keys = OFF")
            for table in NOT_SETUP:
                out.execute(f'DELETE FROM "{table}"')
            out.commit()
            out.execute("VACUUM")
    out.close()
    name = f"PrestCribe {'setup ' if content == 'setup' else ''}{datetime.now():%Y-%m-%d}.prestcribe"
    return FileResponse(copy, filename=name, media_type="application/octet-stream",
                        background=BackgroundTask(shutil.rmtree, folder, ignore_errors=True))

#opens a PrestCribe file (GET /state) in place of everything here, once nothing is being read; an older file is brought up to
#date and one from a newer PrestCribe refused before anything here changes, and what was here is kept as
#backend/db/prestcribe-backup-<when>.db
@app.post("/state")
async def open_state(request: Request, db: Session = Depends(get_db)):
    import tempfile
    from alembic.script import ScriptDirectory
    if db.query(models.Job).filter(models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(status_code=409, detail="Wait for the tasks waiting or running to finish (Tasks, top right), then open it.")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "state.db"
        path.write_bytes(await request.body())
        found = sqlite3.connect(path)
        try:
            tables = {name for (name,) in found.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        except sqlite3.DatabaseError:
            tables = set()
        if not {"alembic_version", "collections", "page_types", "pages"} <= tables:
            found.close()
            raise HTTPException(status_code=400, detail="That isn't a PrestCribe file.")
        version = found.execute("SELECT version_num FROM alembic_version").fetchone()
        if version and version[0] not in {s.revision for s in ScriptDirectory.from_config(database.alembic_config()).walk_revisions()}:
            found.close()
            raise HTTPException(status_code=409, detail="That file was saved by a newer PrestCribe. Update this one first (Settings, then About), then open it.")
        live = db.connection().connection.driver_connection
        if "app_settings" in tables and not found.execute("SELECT 1 FROM app_settings LIMIT 1").fetchone():  #a setup-only file: this computer's own choices stay
            found.executemany("INSERT INTO app_settings (key, value) VALUES (?, ?)", live.execute("SELECT key, value FROM app_settings").fetchall())
            found.commit()
        found.close()
        database.migrate(f"sqlite:///{path.as_posix()}")
        with sqlite3.connect(ROOT / "backend" / "db" / f"prestcribe-backup-{datetime.now():%Y%m%d-%H%M%S}.db") as kept:
            live.backup(kept)
        kept.close()
        found = sqlite3.connect(path)
        found.backup(live)
        found.close()
    return {"opened": True}


#--PAGE SORTING--# how pages are sorted into page types: on this computer (PyTorch, where installed) or by the reading model
class Sorter(BaseModel):
    provider: str
    model: str
    effort: str

#each field left out stays as it is; sorter null: the transcription choice sorts again
class PageSortingRequest(BaseModel):
    method: Literal["local", "model"] | None = None
    unsure: Literal["review", "model"] | None = None
    sorter: Sorter | None = None
    sameAsTranscription: bool = False

_checked, _checking = {}, threading.Lock()  #a passed check of page sorting on this computer, kept while the API runs; one at a time

#how pages are sorted: the method, what a page the model here isn't sure of does, the reading model that sorts (null: the
#transcription choice), whether PyTorch is here, and a passed check of it, if one has run
@app.get("/page-sorting")
def get_page_sorting(db: Session = Depends(get_db)):
    return {**app_settings.sorting_settings(db), "localAvailable": app_settings.local_sorting_available(), "checked": _checked or None}

@app.put("/page-sorting")
def put_page_sorting(payload: PageSortingRequest, db: Session = Depends(get_db)):
    if payload.method == "local" and not app_settings.local_sorting_available():
        raise HTTPException(status_code=400, detail="PyTorch isn't installed on this computer, so pages can't be sorted here.")
    if payload.sorter:
        check_transcription(payload.sorter.provider, payload.sorter.model, payload.sorter.effort)
    write_lock(db)
    if payload.method:
        app_settings.save_page_sorting(db, payload.method)
    app_settings.save_sorting_settings(db, unsure=payload.unsure,
                                       sorter=None if payload.sameAsTranscription else payload.sorter.model_dump() if payload.sorter else False)
    return get_page_sorting(db)


#--API KEYS--# for transcribing through an AI company's API (backend/pipeline/transcribe/providers.py): kept on this computer,
#never in the database, and never sent back; each provider says whether it has one, and where to get one
class ApiKey(BaseModel):
    key: str = ""  #"": forget the saved one

@app.get("/api-keys")
def get_api_keys():
    saved = providers.saved_keys()
    return [{"provider": name, "label": p["label"], "keysUrl": p["keys"], "needsKey": p["env"] is not None,
             "saved": name in saved, "fromEnvironment": name not in saved and bool(p["env"] and os.environ.get(p["env"]))}
            for name, p in providers.PROVIDERS.items()]

@app.put("/api-keys/{provider}")
def put_api_key(provider: str, payload: ApiKey):
    if provider not in providers.PROVIDERS or providers.PROVIDERS[provider]["env"] is None:
        raise HTTPException(status_code=404, detail="No provider with a key called that.")
    value = payload.key.strip()
    if value and (len(value) > 500 or any(c.isspace() for c in value)):
        raise HTTPException(status_code=400, detail="That doesn't look like a key.")
    providers.save_key(provider, value)
    return get_api_keys()


#whether a failure, or what caused it, is a connection or download failing (requests and huggingface_hub errors are matched by name)
def no_internet(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        names = {c.__name__ for c in type(error).__mro__}
        if isinstance(error, (URLError, ConnectionError, socket.gaierror, socket.timeout)) or names & {"ConnectionError", "Timeout", "LocalEntryNotFoundError", "OfflineModeIsEnabled"}:
            return True
        error = error.__cause__ or error.__context__
    return False

#checks page sorting on this computer works, by sorting a blank test page with it (loading PyTorch and the sorting model, which
#is downloaded the first time); what went wrong in words if it doesn't
@app.post("/page-sorting/check")
def check_page_sorting():
    import platform, tempfile, time
    if not app_settings.local_sorting_available():
        intel_mac = sys.platform == "darwin" and platform.machine() != "arm64"
        return {"ok": False, "detail": "PyTorch isn't available for Intel Macs: sort pages by the reading model." if intel_mac
                else "PyTorch isn't installed on this computer: install it from Settings, then Page sorting."}
    from PIL import Image
    from backend.pipeline.identify.identify import identify_pages
    with _checking:  #a check asked for while one runs waits for it, and gets its pass
        if _checked:
            return dict(_checked)
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory() as folder:
                page = Path(folder) / "check.png"
                Image.new("RGB", (850, 1100), "white").save(page)
                identify_pages([page])
        except Exception as error:
            if no_internet(error):  #the sorting model's first download
                return {"ok": False, "detail": f"The page sorting model couldn't be loaded; it's downloaded the first time, so check the internet ({error})"[:400]}
            return {"ok": False, "detail": f"Page sorting on this computer failed: {type(error).__name__}: {error}"[:400]}
        _checked.update(ok=True, seconds=round(time.monotonic() - started, 1))
        return dict(_checked)


#--UPDATES--# an installed copy (install.ps1 or install.sh; its release wrote VERSION) can see the latest release and update to it
RELEASES = "https://github.com/bennos280/IT-Project-Unimelb-Archive-Team-4/releases"
LATEST = "https://api.github.com/repos/bennos280/IT-Project-Unimelb-Archive-Team-4/releases/latest"

def installed_version():
    version = ROOT / "VERSION"
    return version.read_text(encoding="utf-8").strip() if version.is_file() else None

#the computer PrestCribe runs on, for a problem report: its system, Python, and whether pages can be sorted on it
def system_info():
    import platform
    name = f"macOS {platform.mac_ver()[0]}" if sys.platform == "darwin" else f"{platform.system()} {platform.release()}"
    return {"os": f"{name} ({platform.machine()})", "python": platform.python_version(),
            "pytorch": app_settings.local_sorting_available()}

#this copy's version (None: not installed from a release, e.g. a git checkout), the latest release's, whether
#to update, when this was checked, and the computer it runs on
@app.get("/version")
def get_version():
    import urllib.request
    current, latest, error = installed_version(), None, None
    try:
        request = urllib.request.Request(LATEST, headers={"Accept": "application/vnd.github+json", "User-Agent": "PrestCribe"})
        with urllib.request.urlopen(request, timeout=10) as reply:
            latest = json.loads(reply.read().decode("utf-8"))["tag_name"]
    except Exception:
        error = "Couldn't reach GitHub to check for updates."
    return {"current": current, "latest": latest, "releases": RELEASES, "error": error,
            "updatable": bool(current and latest and latest != current),
            "checkedAt": datetime.now(timezone.utc).isoformat(), "system": system_info()}

#updates an installed copy: the installer is run again in its own window, for this folder, once this copy has stopped (it
#starts PrestCribe again when it's done); the database, scans and results are kept
@app.post("/update", status_code=202)
def update(db: Session = Depends(get_db)):
    import subprocess, urllib.request
    if not installed_version():
        raise HTTPException(status_code=400, detail="This copy wasn't installed from a release: update it with git pull.")
    if db.query(models.Job).filter(models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(status_code=409, detail="Wait for the tasks to finish before updating.")
    installer = f"{RELEASES}/latest/download/install.{'ps1' if sys.platform == 'win32' else 'sh'}"
    try:
        with urllib.request.urlopen(urllib.request.Request(installer, headers={"User-Agent": "PrestCribe"}), timeout=10):
            pass
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Couldn't download the installer: {error}"[:300])
    if sys.platform == "win32":
        folder = re.sub("['‘’‚‛]", lambda quote: quote[0] * 2, str(ROOT))  #PowerShell's single quotes, curly ones too
        script = (f"try {{ Start-Sleep 5; & ([scriptblock]::Create((irm '{installer}'))) -Folder '{folder}' }} "
                  f"catch {{ Write-Host ('The update failed: ' + $_); Read-Host 'Press Enter to close this window' }}")
        subprocess.Popen(["powershell", "-ExecutionPolicy", "ByPass", "-NoProfile", "-Command", script],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        script = f'sleep 5; f=$(mktemp) && curl -LsSf "{installer}" -o "$f" && PRESTCRIBE_HOME={shlex.quote(str(ROOT))} sh "$f"; rm -f "$f"'
        subprocess.Popen(["sh", "-c", script], start_new_session=True)
    threading.Timer(1, os._exit, [0]).start()  #this copy stops, so its files can be replaced; the worker stops with it
    return {"updating": True}
