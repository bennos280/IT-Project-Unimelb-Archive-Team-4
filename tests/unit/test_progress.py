"""Test progress UI is calculated from saved fields and reviews, with page model data."""
from datetime import datetime, timezone

from backend.db import models


def seed(db):
    for row in (
        models.Bundle(bundle_id="b", source_pdf="216417/b.pdf", collection_id=1),
        models.Bundle(bundle_id="empty", source_pdf="empty.pdf", collection_id=1),
        models.Survey(survey_id="s", bundle_id="b"),
        models.Page(page_id="p1", bundle_id="b", survey_id="s", category="main", import_path="1.png", model="test-model"),
        models.Page(page_id="p2", bundle_id="b", category="notes", import_path="2.png"),
        models.Field(page_id="p1", field_title="a", text_raw="[?]"),
        models.Field(page_id="p1", field_title="b", text_raw=""),
        models.Flag(page_id="p1", field_title="a", kind="uncertain", reason="Check"),
    ):
        db.add(row)
        db.flush()
    db.commit()


def test_progress_preserves_status_flags_model_and_review_targets(client, db):
    seed(db)
    response = client.get("/progress")
    assert response.status_code == 200
    bundle, empty = response.json()
    assert bundle["name"] == "216417"
    assert empty["pages"] == []
    first, second = bundle["pages"]
    assert (first["status"], first["flagCount"], first["model"]) == ("Ready to review", 1, "test-model")
    assert (first["surveyId"], first["reviewPageId"]) == ("s", "p1")
    assert (second["status"], second["model"], second["surveyId"]) == ("Awaiting transcription", None, None)


def test_only_saved_reviews_reduce_flags_and_all_fields_must_be_reviewed(client, db):
    seed(db)
    edit = models.Edit(page_id="p1", field_title="a", edit_text="readable")
    db.add(edit)
    db.commit()
    def page():
        return client.get("/progress").json()[0]["pages"][0]
    assert page()["flagCount"] == 1
    edit.time = datetime.now(timezone.utc)
    db.commit()
    assert (page()["status"], page()["flagCount"]) == ("Ready to review", 0)
    db.add(models.Edit(page_id="p1", field_title="b", edit_text="", time=datetime.now(timezone.utc)))
    db.commit()
    assert page()["status"] == "Reviewed"


def test_nested_fields_require_reviews_too(client, db):
    seed(db)
    db.get(models.Page, "p2").survey_id = "s"
    db.flush()
    for row in (
        models.Resident(page_id="p2", resident_no=0),
        models.ResidentField(page_id="p2", resident_no=0, resident_field_title="name", text_raw="[?]"),
        models.OtherChild(page_id="p2", residence="died", child_no=0, text_raw="[?]"),
        models.Annotation(page_id="p2", annotation_no=0, text_raw="[?]"),
    ):
        db.add(row)
        db.flush()
    db.commit()
    def page():
        return client.get("/progress").json()[0]["pages"][1]
    assert (page()["status"], page()["flagCount"]) == ("Ready to review", 3)
    for target in (
        {"resident_no": 0, "resident_field_title": "name"},
        {"child_residence": "died", "child_no": 0},
        {"annotation_no": 0},
    ):
        db.add(models.Edit(page_id="p2", edit_text="corrected", time=datetime.now(timezone.utc), **target))
    db.commit()
    assert (page()["status"], page()["flagCount"]) == ("Reviewed", 0)


def test_page_with_fields_but_no_survey_is_not_ready_to_review(client, db):
    """A transcribed page without a survey stays outside review progress."""
    seed(db)
    db.add(models.Field(page_id="p2", field_title="text", text_raw="Transcribed notes"))
    db.commit()
    response = client.get("/progress")
    assert response.status_code == 200
    bundle = next(b for b in response.json() if b["id"] == "b")
    page = next(p for p in bundle["pages"] if p["id"] == "p2")
    assert page["surveyId"] is None
    assert page["status"] == "Not in a survey"


def test_progress_is_reused_until_the_database_changes(client, db, monkeypatch):
    from backend.api import progress
    seed(db)
    calls = []
    original = progress.review_progress
    monkeypatch.setattr(progress, "review_progress", lambda session: calls.append(1) or original(session))
    first = client.get("/progress").json()
    assert client.get("/progress").json() == first
    assert len(calls) == 1
    db.add(models.Edit(page_id="p1", field_title="a", edit_text="readable", time=datetime.now(timezone.utc)))
    db.commit()
    assert client.get("/progress").json()[0]["pages"][0]["flagCount"] == 0
    assert len(calls) == 2
