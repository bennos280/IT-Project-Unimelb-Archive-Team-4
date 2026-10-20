import pytest
from backend.db import models

# Create one bundle, survey, page, reviewer, and two fields for the export tests.
def setup_survey(db):
    rows = [models.Bundle(bundle_id="bundle", source_pdf="data/123/bundle.pdf", collection_id=1),
            models.Survey(survey_id="survey", bundle_id="bundle"),
            models.Page(page_id="p", survey_id="survey", bundle_id="bundle", category="main", import_path="scan.png"),
            models.Field(page_id="p", field_title="address", text_raw="Model"),
            models.Field(page_id="p", field_title="blank", text_raw=None),
            models.Reviewer(reviewer_id=1, name="Reviewer")]
    for row in rows:
        db.add(row)
        db.flush()
    db.commit()

# Check the latest saved correction, including blank and special values, preserves the source image and review status.
@pytest.mark.parametrize("value", ["Correction", "", "/", "[?]", None])
def test_export_latest_saved_value_and_source(client, db, value):
    setup_survey(db)
    for revision, text in [(1, "Old"), (2, value)]:
        assert client.post("/reviews/survey", json={"reviews": {"p": {"address": {"value": text, "reviewerId": 1}}}, "revisions": {"p": revision}}).status_code == 200
    result = client.get("/export?survey_id=survey").json()["surveys"][0]
    assert result["status"] == "ToBeReviewed"
    page = result["pages"][0]
    fields = {f["id"]: f for f in page["fields"]}
    assert fields["address"]["value"] == value
    assert fields["address"]["status"] == "Reviewed"
    assert fields["blank"]["value"] is None

 # Check bundle export includes every survey, empty surveys, and unassigned pages, and lists the bundle number with its ID.
def test_bundle_includes_all_surveys_and_unassigned_pages(client, db):
    setup_survey(db)
    db.add(models.Survey(survey_id="empty", bundle_id="bundle"))
    db.add(models.Page(page_id="loose", bundle_id="bundle", category="other", import_path="loose.png"))
    db.commit()
    result = client.get("/export?bundle_id=bundle").json()
    assert {s["surveyId"] for s in result["surveys"]} == {"survey", "empty"}
    assert next(s for s in result["surveys"] if s["surveyId"] == "empty")["status"] == "ToBeReviewed"
    assert result["unassignedPages"][0]["pageId"] == "loose"
    assert client.get("/export/bundles").json() == [{"id": "bundle", "name": "123"}]

# Check missing, blank, or conflicting selections return 400 and unknown survey or bundle IDs return 404.
def test_export_rejects_invalid_selection(client):
    for query in ["", "?survey_id=", "?bundle_id=", "?survey_id=x&bundle_id=y"]:
        assert client.get("/export" + query).status_code == 400
    for query in ["?survey_id=unknown", "?bundle_id=unknown"]:
        assert client.get("/export" + query).status_code == 404

    # Check IDs are trimmed and isolate the requested bundle even when another bundle has the same display number.
def test_bundle_export_uses_id_and_excludes_other_bundles(client, db):
    setup_survey(db)
    db.add(models.Bundle(bundle_id="other-bundle", source_pdf="data/123/other.pdf", collection_id=1))
    db.flush()
    db.add(models.Survey(survey_id="other-survey", bundle_id="other-bundle"))
    db.add(models.Page(page_id="other-page", bundle_id="other-bundle", category="other", import_path="other.png"))
    db.commit()
    response = client.get("/export", params={"bundle_id": " bundle "})
    assert response.status_code == 200
    result = response.json()
    assert result["bundleId"] == "bundle"
    assert [survey["surveyId"] for survey in result["surveys"]] == ["survey"]
    assert result["unassignedPages"] == []
    assert client.get("/export", params={"bundle_id": "123"}).status_code == 404

    # Check the survey response supplies the database bundle ID used by the review screen’s Current bundle option.
def test_review_survey_identifies_current_bundle(client, db):
    setup_survey(db)
    response = client.get("/survey/survey")
    assert response.status_code == 200
    assert response.json()["bundleId"] == "bundle"
