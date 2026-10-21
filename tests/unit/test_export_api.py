import io
import json
import zipfile

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

# Add rows one at a time, each flushed, so the rows that point at it can follow.
def add_rows(db, *rows):
    for row in rows:
        db.add(row)
        db.flush()
    db.commit()

# A page of a bundle with its fields (title -> what was read) and the meaning the loader stored for coded ones.
def scanned(bundle, number, survey, category, fields, decoded={}):
    page_id = f"{bundle}_{number}"
    return [models.Page(page_id=page_id, survey_id=survey, bundle_id=bundle, category=category, import_path=f"{page_id}.png"),
            *[models.Field(page_id=page_id, field_title=title, text_raw=raw, decoded_value=decoded.get(title)) for title, raw in fields.items()]]

FOLDER = "UMA-SR-000000842"
BRIGHTON = f"{FOLDER}/UMA-ITE-1973000200001.json"

# Create series 1's items: archive items 90 and 500001, a folder (777) named like another series' archive item, and one whose name is
# not a number. 500001 has two records (S-2 and S-10, which sort the other way as text), a page in no record, a coded page, and
# saved reviews: page 1 fully, and the coded page's washouse.
def setup_series(client, db):
    add_rows(db, models.Collection(collection_id=2, name="Other series"), models.Reviewer(reviewer_id=1, name="Reviewer"),
             models.ArchiveItem(node=90, collection_id=1, identifier="UMA-ITE-1973000000090", title="Ninety Street"),
             models.ArchiveItem(node=500001, collection_id=1, identifier="UMA-ITE-1973000200001", title="Brighton forms"),
             models.ArchiveItem(node=777, collection_id=2, identifier="UMA-ITE-1973000000777", title="Elsewhere"),
             *[models.Bundle(bundle_id=name, source_pdf=f"data/{name}/{name}.pdf", collection_id=1) for name in ("90", "777", "500001", "upload-7")],
             models.Survey(survey_id="A-1", bundle_id="90"), models.Survey(survey_id="U-1", bundle_id="upload-7"),
             models.Survey(survey_id="S-2", bundle_id="500001"), models.Survey(survey_id="S-10", bundle_id="500001"),
             *scanned("90", 1, "A-1", "main", {"address": "1 Low St."}),
             *scanned("upload-7", 1, "U-1", "main", {"address": "3 High St."}),
             *scanned("500001", 1, "S-2", "main", {"address": "5 Peel St.", "bath.location": "Outside"}),
             *scanned("500001", 2, "S-2", "notes", {"text": "Visited twice"}),
             *scanned("500001", 3, None, "main", {"address": "2 Hope Rd – Fitzroy"}),
             *scanned("500001", 9, "S-2", "coded", {"washouse": "1", "bathroom": "1", "remarks": "see form"},
                      {"washouse": "In separate laundry", "bathroom": "Bath in laundry"}),
             *scanned("500001", 10, "S-10", "main", {"address": "9 Kent St."}),
             *scanned("500001", 11, "S-10", "notes", {"text": "Zoë's note"}))
    for page, reviews in [("500001_1", {"address": "7 Peel St.", "bath.location": "Inside"}), ("500001_9", {"washouse": "2"})]:
        edits = {field: {"value": value, "reviewerId": 1} for field, value in reviews.items()}
        assert client.post("/reviews/S-2", json={"reviews": {page: edits}, "revisions": {page: 1}}).status_code == 200

# A series export's files by name, each parsed, in the zip's order.
def files_of(response):
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return {name: json.loads(archive.read(name)) for name in archive.namelist()}

# Check a series export is a zip named for the series, holding a file per item in item-number order (numbers numerically), each named by
# its archive identifier or else its item number, with the series and item as the archive has them (none for an item of another series).
def test_series_export_names_and_orders_the_items(client, db):
    setup_series(client, db)
    response = client.get("/collections/1/export")
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == f'attachment; filename="{FOLDER}.zip"'
    files = files_of(response)
    assert [name.removeprefix(f"{FOLDER}/") for name in files] == ["UMA-ITE-1973000000090.json", "777.json", "UMA-ITE-1973000200001.json", "upload-7.json"]
    series = {"name": "Wilfred Prest Survey", "identifier": FOLDER, "node": 499420, "title": "University of Melbourne Social Survey forms"}
    assert [(f["series"], f["item"]) for f in files.values()] == [
        (series, {"number": "90", "identifier": "UMA-ITE-1973000000090", "node": 90, "title": "Ninety Street"}),
        (series, {"number": "777", "identifier": None, "node": None, "title": None}),
        (series, {"number": "500001", "identifier": "UMA-ITE-1973000200001", "node": 500001, "title": "Brighton forms"}),
        (series, {"number": "upload-7", "identifier": None, "node": None, "title": None})]
    assert files[f"{FOLDER}/777.json"]["pages"] == []  # loaded, but nothing in it
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        raw = archive.read(BRIGHTON).decode("utf-8")
    assert raw.startswith('{\n  "series": {\n    "name"')  # indented by 2
    assert "2 Hope Rd – Fitzroy" in raw and "Zoë's note" in raw  # not escaped

# Check pages are in page-number order, not id order, with the number the archive fetches each by; records are numbered from 1 in order
# of their first page, not their ids (S-10 is the second though it sorts first as text); a page in no record has null; every item numbers its own.
def test_series_export_numbers_pages_and_records(client, db):
    setup_series(client, db)
    files = files_of(client.get("/collections/1/export"))
    assert [(p["page"], p["pageType"], p["record"]) for p in files[BRIGHTON]["pages"]] == [
        (1, "main", 1), (2, "notes", 1), (3, "main", None), (9, "coded", 1), (10, "main", 2), (11, "notes", 2)]
    for name in ("UMA-ITE-1973000000090", "upload-7"):
        assert [(p["page"], p["record"]) for p in files[f"{FOLDER}/{name}.json"]["pages"]] == [(1, 1)]

# Check the reviewed value replaces what the model read, "reviewed" is true only for a page whose every field is, and "decoded" appears
# only for fields with a meaning (a reviewed code with its own meaning), never on a page without any.
def test_series_export_reviewed_values_and_decoded(client, db):
    setup_series(client, db)
    assert files_of(client.get("/collections/1/export"))[BRIGHTON]["pages"] == [
        {"page": 1, "pageType": "main", "record": 1, "reviewed": True, "fields": {"address": "7 Peel St.", "bath.location": "Inside"}},
        {"page": 2, "pageType": "notes", "record": 1, "reviewed": False, "fields": {"text": "Visited twice"}},
        {"page": 3, "pageType": "main", "record": None, "reviewed": False, "fields": {"address": "2 Hope Rd – Fitzroy"}},
        {"page": 9, "pageType": "coded", "record": 1, "reviewed": False,
         "fields": {"washouse": "2", "bathroom": "1", "remarks": "see form"},
         "decoded": {"washouse": "In kitchen", "bathroom": "Bath in laundry"}},
        {"page": 10, "pageType": "main", "record": 2, "reviewed": False, "fields": {"address": "9 Kent St."}},
        {"page": 11, "pageType": "notes", "record": 2, "reviewed": False, "fields": {"text": "Zoë's note"}}]

# Check a series with no archive identifier is exported under its name with every other character made an underscore, and has null series fields.
def test_series_export_folder_without_identifier(client, db):
    add_rows(db, models.Collection(collection_id=2, name="Brighton: forms/1 é"),
             models.Bundle(bundle_id="a", source_pdf="data/a/a.pdf", collection_id=2))
    response = client.get("/collections/2/export")
    assert response.headers["content-disposition"] == 'attachment; filename="Brighton__forms_1__.zip"'
    files = files_of(response)
    assert list(files) == ["Brighton__forms_1__/a.json"]
    assert files["Brighton__forms_1__/a.json"]["series"] == {"name": "Brighton: forms/1 é", "identifier": None, "node": None, "title": None}

# Check an unknown series, and one whose items aren't transcribed yet (even with another series' loaded), return 404 with the reason.
def test_series_export_refuses_unknown_or_untranscribed(client, db):
    response = client.get("/collections/99/export")
    assert (response.status_code, response.json()) == (404, {"detail": "No such series."})
    add_rows(db, models.ArchiveItem(node=90, collection_id=1, identifier="UMA-ITE-1973000000090", title="Ninety Street"),
             models.Collection(collection_id=2, name="Other series"),
             models.Bundle(bundle_id="a", source_pdf="data/a/a.pdf", collection_id=2))
    response = client.get("/collections/1/export")
    assert (response.status_code, response.json()) == (404, {"detail": "Nothing in this series is transcribed yet."})
