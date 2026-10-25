"""Read-only review progress, including pages without a survey assignment."""
from collections import defaultdict
from pathlib import PurePosixPath
from backend.db import field_ids, models


def review_progress(db):
    fields, flagged, reviewed = (defaultdict(set) for _ in range(3))
    def field(page, key, value):
        fields[page].add(key)
        if "[?]" in (value or ""):
            flagged[page].add(key)
    for p, list_name, no, key, value in db.query(models.Field.page_id, models.Field.list_name, models.Field.item_no,
                                                 models.Field.field_title, models.Field.text_raw):
        field(p, field_ids.field_id(list_name, no, key), value)
    for p, no, value in db.query(models.Annotation.page_id, models.Annotation.annotation_no, models.Annotation.text_raw):
        field(p, field_ids.annotation_id(no), value)
    for p, list_name, no, key in db.query(models.Flag.page_id, models.Flag.list_name, models.Flag.item_no, models.Flag.field_title):
        flagged[p].add(field_ids.field_id(list_name, no, key))
    for e in db.query(models.Edit).filter(models.Edit.time.is_not(None)):
        reviewed[e.page_id].add(field_ids.field_id(e.list_name, e.item_no, e.field_title) if e.field_title is not None
                                else field_ids.annotation_id(e.annotation_no))
    bundles = {}
    for b in db.query(models.Bundle).order_by(models.Bundle.bundle_id):
        parent = PurePosixPath(b.source_pdf.replace("\\", "/")).parent.name
        bundles[b.bundle_id] = {"id": b.bundle_id, "name": parent if parent.isdigit() else b.bundle_id, "collectionId": b.collection_id,
                                "pages": []}
    labels = dict(db.query(models.PageType.name, models.PageType.label))
    unknown = {name for (name,) in db.query(models.PageType.name).filter(models.PageType.unknown)}
    for p in db.query(models.Page).order_by(models.Page.page_id):
        if p.category in unknown:
            flagged[p.page_id].add("text")
        pages = bundles[p.bundle_id]["pages"]
        status = (
            "Awaiting transcription" if p.needs_transcription or not fields[p.page_id] else
            "Not in a survey" if p.survey_id is None else
            "Reviewed" if fields[p.page_id] <= reviewed[p.page_id] else
            "Ready to review"
        )
        pages.append({"id": p.page_id, "label": f"Pg {len(pages) + 1}",
                      "category": labels[p.category],
                      "status": status, "model": p.model, "flagCount": len(flagged[p.page_id] - reviewed[p.page_id]),
                      "surveyId": p.survey_id, "reviewPageId": p.page_id})
    return list(bundles.values())
