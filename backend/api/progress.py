"""Read-only review progress, including pages without a survey assignment."""
from collections import defaultdict
from pathlib import PurePosixPath
from backend.db import models


def review_progress(db):
    fields, flagged, reviewed = (defaultdict(set) for _ in range(3))
    def field(page, key, value):
        fields[page].add(key)
        if "[?]" in (value or ""):
            flagged[page].add(key)
    for p, key, value in db.query(models.Field.page_id, models.Field.field_title, models.Field.text_raw):
        field(p, key, value)
    for p, no, key, value in db.query(models.ResidentField.page_id, models.ResidentField.resident_no,
                                     models.ResidentField.resident_field_title, models.ResidentField.text_raw):
        field(p, f"residents.{no}.{key}", value)
    for p, residence, no, value in db.query(models.OtherChild.page_id, models.OtherChild.residence,
                                           models.OtherChild.child_no, models.OtherChild.text_raw):
        field(p, f"other_children.{residence}.{no}", value)
    for p, no, value in db.query(models.Annotation.page_id, models.Annotation.annotation_no, models.Annotation.text_raw):
        field(p, f"annotations.{no}", value)
    for p, key in db.query(models.Flag.page_id, models.Flag.field_title):
        flagged[p].add(key)
    for e in db.query(models.Edit).filter(models.Edit.time.is_not(None)):
        if e.field_title is not None:
            key = e.field_title
        elif e.resident_no is not None:
            key = f"residents.{e.resident_no}.{e.resident_field_title}"
        elif e.child_no is not None:
            key = f"other_children.{e.child_residence}.{e.child_no}"
        else:
            key = f"annotations.{e.annotation_no}"
        reviewed[e.page_id].add(key)
    bundles = {}
    for b in db.query(models.Bundle).order_by(models.Bundle.bundle_id):
        parent = PurePosixPath(b.source_pdf.replace("\\", "/")).parent.name
        bundles[b.bundle_id] = {"id": b.bundle_id, "name": parent if parent.isdigit() else b.bundle_id, "pages": []}
    for p in db.query(models.Page).order_by(models.Page.page_id):
        if p.category == "other":
            flagged[p.page_id].add("text")
        pages = bundles[p.bundle_id]["pages"]
        status = ("Awaiting transcription" if not fields[p.page_id] else
                  "Reviewed" if fields[p.page_id] <= reviewed[p.page_id] else "Ready to review")
        pages.append({"id": p.page_id, "label": f"Pg {len(pages) + 1}",
                      "category": {"main": "Main page", "notes": "Notes", "coded": "Coded", "other": "Notes"}.get(p.category, p.category),
                      "status": status, "model": p.model, "flagCount": len(flagged[p.page_id] - reviewed[p.page_id]),
                      "surveyId": p.survey_id, "reviewPageId": p.page_id})
    return list(bundles.values())
