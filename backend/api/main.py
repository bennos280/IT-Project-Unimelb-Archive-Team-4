from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel
from functools import cache
import json
import re
import sqlite3
import threading
from backend.db import app_settings, database, grouping, instructions, loader, models
from backend.db.loader import CODED_DICT, stored_path
from backend import scans
from backend.api.sections import groupings_main, groupings_coded
from datetime import datetime, timezone
from backend.common import ROOT, find_images, settings
from backend.pipeline.transcribe import areas

from backend.api.uploads import upload_bundle
from backend.api import connections, transcription_options

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(connections.router)
app.include_router(transcription_options.router)

#takes the db's write lock now, so another save can't land between a check and the write it guards (freed at commit)
def write_lock(db):
    db.connection().exec_driver_sql("UPDATE pages SET page_id = page_id WHERE 0")

get_db = database.get_db #the db session dependency, defined there so connections.py can use it too

@app.post("/bundles/upload", status_code=201)
async def import_bundle(request: Request, bundle: str, filename: str, db: Session = Depends(get_db)):
    return await upload_bundle(request, bundle, filename, db)


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
        flags.append({"id": "other-page", "fieldId": "text", "kind": "uncertain", "reason": OTHER_PAGE})
    return flags

#a survey's pages in scan order, with fields, flags and scan URL
@app.get("/survey/{survey_id}")
def get_survey(survey_id: str, request: Request, db: Session = Depends(get_db)):
    survey = db.get(models.Survey, survey_id)
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

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
    collection = db.get(models.Collection, db.get(models.Bundle, survey.bundle_id).collection_id)
    return {"id":survey_id, "bundleId":survey.bundle_id, "collectionId":collection.collection_id, "title":collection.name, "pages":pages_list}

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

def version_json(v, names):
    return {"id": v.version_id, "kind": v.kind, "body": v.body, "reviewerId": v.reviewer_id, "reviewer": names.get(v.reviewer_id),
            "note": v.note, "createdAt": v.created_at.replace(tzinfo=timezone.utc).isoformat() if v.created_at else ""}

#the newest prompt, and the newest template of each page type
@app.get("/instructions")
def get_instructions(db: Session = Depends(get_db)):
    names = dict(db.query(models.Reviewer.reviewer_id, models.Reviewer.name))
    return {kind: version_json(v, names) for kind, v in instructions.newest(db).items()}

#every version of the prompt or of one template, newest first
@app.get("/instructions/{kind}")
def get_instruction_versions(kind: str, db: Session = Depends(get_db)):
    versions = (db.query(models.InstructionVersion).filter(models.InstructionVersion.kind == kind)
                .order_by(models.InstructionVersion.version_id.desc()).all())
    if not versions:
        raise HTTPException(status_code=404, detail=f"No prompt or template called {kind}.")
    names = dict(db.query(models.Reviewer.reviewer_id, models.Reviewer.name))
    return [version_json(v, names) for v in versions]

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
    if kind in current and payload.body.replace("\r\n", "\n") == current[kind].body.replace("\r\n", "\n"):
        raise HTTPException(status_code=400, detail="Nothing changed.")
    if found := instructions.problems(kind, payload.body, {k: v.body for k, v in current.items()}, grouping.required_fields(db)):
        raise HTTPException(status_code=400, detail=found)
    version = models.InstructionVersion(kind=kind, body=payload.body, sha256=instructions.sha256(payload.body),
                                        reviewer_id=reviewer.reviewer_id, note=payload.note)
    db.add(version)
    db.commit()
    return version_json(version, {reviewer.reviewer_id: reviewer.name})


#--PAGE TYPES--# (the four built in, and any added here; a page type's pages are read with its template)
class PageTypeRequest(BaseModel):
    reviewerId: int
    collectionId: int = 1
    label: str | None = None #what people see; the name if not given
    name: str | None = None #its id; made from the label if not given

class PageTypeSettings(BaseModel):
    label: str | None = None
    startsRecord: bool | None = None
    matchedByKey: bool | None = None

class CollectionSettings(BaseModel):
    name: str | None = None
    archiveSeries: str | None = None #its series' address on the archive, or the number at its end
    recordKey: str | None = None #None or "": surveys by page order only

class NewCollection(BaseModel):
    name: str
    archiveSeries: str

class PageTypeChange(BaseModel):
    pageType: str
    reviewerId: int
    model: str | None = None
    provider: str | None = None
    effort: str | None = None

RESERVED = {instructions.PROMPT, "blank", "review"} #the prompt's kind, and what page sorting answers for no page type

def page_type_json(t, templates):
    return {"name": t.name, "label": t.label, "builtIn": t.built_in, "unknown": t.unknown, "startsRecord": t.starts_record,
            "matchedByKey": t.matched_by_key, "templateVersion": templates[t.name].version_id if t.name in templates else None}

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
        raise HTTPException(status_code=400, detail="No such collection.")
    try:
        db.add(models.PageType(name=name, label=label, reviewer_id=payload.reviewerId, collection_id=payload.collectionId))
        db.commit()
    except IntegrityError: #the label is taken in the collection
        db.rollback()
        raise HTTPException(status_code=409, detail=f"There is already a page type labelled {label}.")
    return page_type_json(db.get(models.PageType, name), {})

#changes a page type's label or how it groups. A type starts a survey or joins one by number, not both; an Unknown type, never
#read, does neither; and grouping needs the collection's number field in the template of a type that does
@app.patch("/page-types/{name}")
def update_page_type(name: str, payload: PageTypeSettings, db: Session = Depends(get_db)):
    write_lock(db)
    t = db.get(models.PageType, name)
    if not t:
        raise HTTPException(status_code=404, detail=f"No page type called {name}.")
    label = t.label if payload.label is None else payload.label.strip()
    starts = t.starts_record if payload.startsRecord is None else payload.startsRecord
    matched = t.matched_by_key if payload.matchedByKey is None else payload.matchedByKey
    template = instructions.newest(db).get(name)
    key = db.get(models.Collection, t.collection_id).record_key
    problem = ("A page type's label can't be empty." if not label else
               "A page type starts a survey or joins one by number, not both." if starts and matched else
               "Unknown pages aren't read, so they can't start or join a survey." if t.unknown and (starts or matched) else
               f"Add the survey number field '{key}' to its template first."
               if key and (starts or matched) and template and key not in json.loads(template.body) else None)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    t.label, t.starts_record, t.matched_by_key = label, starts, matched
    try:
        db.commit()
    except IntegrityError: #the label is taken in the collection
        db.rollback()
        raise HTTPException(status_code=409, detail=f"There is already a page type labelled {label}.")
    return page_type_json(t, instructions.newest(db))

def collection_json(c, db=None):
    counts = {} if db is None else {
        "bundles": db.query(models.Bundle).filter_by(collection_id=c.collection_id).count(),
        "pages": db.query(models.Page).join(models.Bundle).filter(models.Bundle.collection_id == c.collection_id).count()}
    return {"id": c.collection_id, "name": c.name, "recordKey": c.record_key, "archiveSeries": c.archive_series, **counts}

#a series' node id on archives.library.unimelb.edu.au, from its address (.../nodes/view/499420) or the number itself; None: neither
def series_node(text):
    found = re.fullmatch(r"\s*(?:https?://archives\.library\.unimelb\.edu\.au/nodes/view/)?([1-9]\d{0,8})/?\s*", text or "")
    return int(found.group(1)) if found else None

SERIES_HELP = "Paste the series' address from archives.library.unimelb.edu.au (.../nodes/view/<number>), or just its number."

#every collection, with how many bundles and pages it has
@app.get("/collections")
def get_collections(db: Session = Depends(get_db)):
    return [collection_json(c, db) for c in db.query(models.Collection).order_by(models.Collection.collection_id)]

#a new collection, linked to its series on the archive, starts with its Unknown page type
@app.post("/collections", status_code=201)
def create_collection(payload: NewCollection, db: Session = Depends(get_db)):
    name, node = payload.name.strip(), series_node(payload.archiveSeries)
    if not name:
        raise HTTPException(status_code=400, detail="A collection needs a name.")
    if node is None:
        raise HTTPException(status_code=400, detail=SERIES_HELP)
    write_lock(db)
    collection = models.Collection(name=name, archive_series=node)
    db.add(collection)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"There is already a collection called {name}.")
    db.add(models.PageType(name=new_name(db, "Unknown"), label="Unknown", unknown=True, built_in=True, collection_id=collection.collection_id))
    db.commit()
    return collection_json(collection, db)

@app.get("/collections/{collection_id}")
def get_collection(collection_id: int, db: Session = Depends(get_db)):
    c = db.get(models.Collection, collection_id)
    if not c:
        raise HTTPException(status_code=404, detail="No such collection.")
    return collection_json(c, db)

#renames a collection, relinks its series, or sets the field holding a survey's number, which the templates of the types that
#start or join a survey must have; a field left out of the request stays as it is
@app.patch("/collections/{collection_id}")
def update_collection(collection_id: int, payload: CollectionSettings, db: Session = Depends(get_db)):
    write_lock(db)
    c = db.get(models.Collection, collection_id)
    if not c:
        raise HTTPException(status_code=404, detail="No such collection.")
    given = payload.model_fields_set
    if "name" in given:
        if not (payload.name or "").strip():
            raise HTTPException(status_code=400, detail="A collection needs a name.")
        c.name = payload.name.strip()
    if "archiveSeries" in given:
        if series_node(payload.archiveSeries) is None:
            raise HTTPException(status_code=400, detail=SERIES_HELP)
        c.archive_series = series_node(payload.archiveSeries)
    if "recordKey" in given:
        key = (payload.recordKey or "").strip() or None
        if key and not instructions.KEY.fullmatch(key):
            raise HTTPException(status_code=400, detail="A field name is lower-case letters, digits and _, starting with a letter.")
        templates = instructions.newest(db)
        missing = sorted(t.label for t in db.query(models.PageType).filter_by(collection_id=collection_id)
                         if key and (t.starts_record or t.matched_by_key) and t.name in templates and key not in json.loads(templates[t.name].body))
        if missing:
            raise HTTPException(status_code=400, detail=f"These page types' templates don't have '{key}': {', '.join(missing)}.")
        c.record_key = key
    name = c.name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"There is already a collection called {name}.")
    return collection_json(c, db)

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

#reads a page again as another page type, replacing what was read off it: queued for the worker, or for other done now (an
#empty page to type into). A page with saved reviews keeps its type, as reading it again would lose them.
@app.put("/pages/{page_id:path}/type")
def change_page_type(page_id: str, payload: PageTypeChange, db: Session = Depends(get_db)):
    write_lock(db)
    page = db.get(models.Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    new_type = db.get(models.PageType, payload.pageType)
    if not new_type:
        raise HTTPException(status_code=400, detail=f"No page type called {payload.pageType}.")
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
    if provider not in ("claude", "codex") or not effort or len(effort) > 40 or any(c.isspace() for c in effort) or effort.startswith("-"):
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
    if provider not in ("claude", "codex"):
        raise HTTPException(status_code=400, detail="Choose Claude or Codex.")
    if not effort or len(effort) > 40 or any(c.isspace() for c in effort) or effort.startswith("-"):
        raise HTTPException(status_code=400, detail="Enter a valid effort level.")

class StartJobRequest(BaseModel):
    model: str | None = None
    provider: str | None = None
    effort: str | None = None
    pdf: str #as listed by GET /bundles

#every survey PDF under DATA (the data folder), each DATA/<bundle number>/ folder of page images, and each of the archive's
#bundles whose PDF isn't there, as DATA/<bundle number>/<its PDF> (running it downloads the PDF)
def pdfs():
    data = ROOT / settings()["DATA"]
    here = list(data.rglob("*.pdf")) + [p for p in (data.iterdir() if data.is_dir() else ())
                                        if p.is_dir() and p.name.isdigit() and find_images(p)]
    names = {p.name for p in here}
    return sorted(here + [p for p in (data / pdf for pdf in scans.ARCHIVE_PDFS) if p.name not in names])

def job_json(job):
    return {"id": job.job_id, "kind": job.kind, "pdf": job.pdf, "pageId": job.page_id, "pageType": job.page_type,
            "status": job.status, "step": job.step,
            "donePages": job.done_pages, "totalPages": job.total_pages, "error": job.error,
            "updatedAt": job.updated_at.replace(tzinfo=timezone.utc).isoformat() if job.updated_at else ""}

#every runnable PDF, with its loaded survey ids and latest job; name is the bundle number (the PDF's folder)
@app.get("/bundles")
def get_bundles(collection: int = 1, db: Session = Depends(get_db)):
    loaded = {bundle_id for (bundle_id,) in db.query(models.Bundle.bundle_id).filter_by(collection_id=collection)}
    elsewhere = {bundle_id for (bundle_id,) in db.query(models.Bundle.bundle_id).filter(models.Bundle.collection_id != collection)}
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
        if p.stem in elsewhere or (p.stem not in loaded and collection != 1):  #ponytail: a PDF not loaded yet is collection 1's
            continue
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
    from pathlib import Path
    from backend.pipeline.run import read_manifest, digest
    job = db.get(models.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    if job.kind != "bundle" or not job.pdf:
        raise HTTPException(status_code=400, detail="This job is not a bundle transcription.")
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
    return {"jobId": job_id, "status": job.status, "pages": result}


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
        raise HTTPException(status_code=400, detail="Choose a survey ID or a bundle.")
    if survey_id is not None:
        return export_survey(survey_id, request, db)
    bundle_id = bundle_id.strip()
    if not bundle_id:
        raise HTTPException(status_code=400, detail="Choose a bundle.")
    if not db.get(models.Bundle, bundle_id):
        raise HTTPException(status_code=404, detail="Bundle not found.")
    surveys = []
    for (sid,) in db.query(models.Survey.survey_id).filter_by(bundle_id=bundle_id).order_by(models.Survey.survey_id):
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
        raise HTTPException(404, "Page or destination survey not found.")
    if not db.get(models.Reviewer, payload.reviewerId):
        raise HTTPException(400, "Select a valid reviewer.")
    if target.bundle_id != page.bundle_id:
        raise HTTPException(400, "Pages can only move within the same bundle.")
    if target.survey_id == page.survey_id:
        raise HTTPException(400, "Choose a different survey.")
    if page.survey_id != payload.sourceSurveyId or (page.revision_no or 0) != payload.revision:
        raise HTTPException(409, "This page changed. Refresh before moving it.")
    if db.query(models.Job).filter(models.Job.page_id == page_id, models.Job.status.in_(("waiting", "running"))).first():
        raise HTTPException(409, "Wait for this page's transcription to finish before moving it.")
    db.add(models.PageMove(page_id=page_id, from_survey=page.survey_id, to_survey=target.survey_id,
                           reviewer_id=payload.reviewerId, reason=payload.reason.strip()))
    page.survey_id = target.survey_id
    if page.checked_revision == (page.revision_no or 0):
        page.checked_revision = (page.revision_no or 0) + 1
    page.revision_no = (page.revision_no or 0) + 1
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
        raise HTTPException(400, f"No page type called {payload.pageType} in this page's collection.")
    if payload.pageType == page.category:
        raise HTTPException(400, "The page is already that type.")
    from backend.db.page_history import snapshot
    snapshot(db, page_id, payload.reviewerId, "change_type")
    page.category = payload.pageType
    # An Unknown type's pages wait, unread, for a reviewer to pick their type.
    page.needs_transcription = not new_type.unknown
    page.revision_no = (page.revision_no or 0) + 1
    page.checked_revision = None
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
    if payload.provider not in ("claude", "codex") or not payload.effort or len(payload.effort) > 40 or any(c.isspace() for c in payload.effort) or payload.effort.startswith("-"):
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
        event("move", move.move_id, move.time, move.reviewer_id, "Moved to another survey",
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
