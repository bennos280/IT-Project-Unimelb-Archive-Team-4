"""Collections (/collections): the list with counts, a new one linked to its series on the archive and starting with its own
Unknown page type, a rename, the archive preview (/archive-series), and each collection's own bundles, page types and surveys."""
from backend.db import models
from tests.unit.test_backend_api import add_in_order

PREST = "[UMA-SR-000000842] University of Melbourne Social Survey forms"
DESCRIPTION = ("Identifier: UMA-SR-000000842 | Access Status: Open for public access | Creator: Prest, Wilfred | Date: 1941-1943 | "
               "Read the full record details for Series: University of Melbourne Social Survey forms")


def test_a_new_collection_needs_a_name_and_its_archive_series_and_starts_with_an_unknown_type(client):
    assert client.post("/collections", json={"name": "Ships", "archiveSeries": "UMA-SR-000000842"}).status_code == 400
    assert client.post("/collections", json={"name": " ", "archiveSeries": "5"}).status_code == 400
    created = client.post("/collections", json={"name": "Shipping manifests",
                                                "archiveSeries": "https://archives.library.unimelb.edu.au/nodes/view/123456"}).json()
    assert {k: created[k] for k in ("name", "archiveSeries", "recordKey", "bundles", "pages")} == {
        "name": "Shipping manifests", "archiveSeries": 123456, "recordKey": None, "bundles": 0, "pages": 0}
    assert client.post("/collections", json={"name": "Shipping manifests", "archiveSeries": "7"}).status_code == 409
    assert [(t["name"], t["label"], t["unknown"]) for t in client.get(f"/page-types?collection={created['id']}").json()] == [
        ("unknown", "Unknown", True)]
    assert [c["name"] for c in client.get("/collections").json()] == ["Wilfred Prest Survey", "Shipping manifests"]


def test_a_rename_leaves_the_other_settings_as_they_were(client):
    renamed = client.patch("/collections/1", json={"name": "Prest survey"}).json()
    assert (renamed["name"], renamed["recordKey"], renamed["archiveSeries"]) == ("Prest survey", "number_of_dwelling", 499420)
    assert client.patch("/collections/1", json={"archiveSeries": "nowhere"}).status_code == 400
    assert client.patch("/collections/1", json={"name": ""}).status_code == 400


def test_the_archive_preview_reads_the_series_page(client, archive):
    archive.add_series(499420, PREST, DESCRIPTION, 45)
    assert client.get("/archive-series/499420").json() == {
        "id": 499420, "title": PREST, "identifier": "UMA-SR-000000842", "date": "1941-1943", "access": "Open for public access",
        "items": 45, "url": "https://archives.library.unimelb.edu.au/nodes/view/499420"}
    assert client.get("/archive-series/1").status_code == 404


def test_the_archive_preview_says_when_the_archive_cant_be_reached(client):
    reply = client.get("/archive-series/499420")  # the tests never reach the internet
    assert reply.status_code == 502 and reply.json()["detail"].startswith("Couldn't reach the archive")


def test_each_collection_has_its_own_bundles_page_types_and_surveys(client, db):
    db.add(models.Collection(collection_id=2, name="Ships", archive_series=7))
    db.flush()
    add_in_order(db, models.Reviewer(reviewer_id=1, name="Ben"), models.Bundle(bundle_id="ship1", source_pdf="ship1.pdf", collection_id=2),
                 models.PageType(name="manifest", label="Manifest", collection_id=2),
                 models.Survey(survey_id="s2", bundle_id="ship1"),
                 models.Page(page_id="ship1_00001", survey_id="s2", bundle_id="ship1", category="manifest", import_path="x.png"))
    db.commit()
    assert [b["id"] for b in client.get("/progress?collection=2").json()] == ["ship1"]
    assert [b["id"] for b in client.get("/progress?collection=1").json()] == ["6789"]
    assert [t["name"] for t in client.get("/page-types?collection=2").json()] == ["manifest"]
    assert {c["name"]: (c["bundles"], c["pages"]) for c in client.get("/collections").json()} == {"Wilfred Prest Survey": (1, 0), "Ships": (1, 1)}
    survey = client.get("/survey/s2").json()
    assert (survey["collectionId"], survey["title"]) == (2, "Ships")
    assert client.post("/page-types", json={"label": "Cargo list", "reviewerId": 1, "collectionId": 2}).status_code == 201
    assert [t["name"] for t in client.get("/page-types?collection=2").json()] == ["cargo_list", "manifest"]
    assert "cargo_list" not in [t["name"] for t in client.get("/page-types?collection=1").json()]


def test_bad_names_series_and_collections_are_refused_with_the_reason(client, db):
    client.post("/collections", json={"name": "Ships", "archiveSeries": "7"})
    taken = client.patch("/collections/2", json={"name": "Wilfred Prest Survey"})
    assert (taken.status_code, taken.json()["detail"]) == (409, "There is already a series called Wilfred Prest Survey.")
    for series in ("9999999999999999999999", "0", "-5"):
        assert client.post("/collections", json={"name": "Big", "archiveSeries": series}).status_code == 400, series
    db.add(models.Reviewer(reviewer_id=1, name="Ben"))
    db.commit()
    missing = client.post("/page-types", json={"label": "Cargo", "reviewerId": 1, "collectionId": 99})
    assert (missing.status_code, missing.json()["detail"]) == (400, "No such series.")
    assert client.get("/page-types?collection=0").json() == []  # a filter, not "every collection"


def test_export_lists_only_the_collections_bundles(client, db):
    db.add(models.Collection(collection_id=2, name="Ships", archive_series=7))
    db.flush()
    add_in_order(db, models.Bundle(bundle_id="ship1", source_pdf="ship1.pdf", collection_id=2))
    db.commit()
    assert [b["id"] for b in client.get("/export/bundles?collection=2").json()] == ["ship1"]
    assert [b["id"] for b in client.get("/export/bundles?collection=1").json()] == ["6789"]
    assert len(client.get("/export/bundles").json()) == 2


def test_the_list_counts_review_progress_and_how_far_each_collection_is_set_up(client, db):
    from datetime import datetime
    add_in_order(db, models.Reviewer(reviewer_id=1, name="Ben"), models.Survey(survey_id="s", bundle_id="6789"),
                 models.Page(page_id="p1", survey_id="s", bundle_id="6789", category="main", import_path="1.png"),
                 models.Field(page_id="p1", field_title="address", text_raw="5 Peel St."),
                 models.Page(page_id="p2", survey_id="s", bundle_id="6789", category="notes", import_path="2.png"),
                 models.Field(page_id="p2", field_title="text", text_raw="notes"),
                 models.Page(page_id="p3", bundle_id="6789", category="other", import_path="3.png"),  # in no survey
                 models.Edit(page_id="p1", field_title="address", edit_text="5 Peel St.", reviewer_id=1, time=datetime.now()),
                 models.InstructionVersion(kind="main", body="{}", sha256="m"),
                 models.Job(pdf="data/216498/216498.pdf", status="failed"), models.Job(pdf="data/216498/216498.pdf", status="done"),
                 models.Job(pdf="data/216499/216499.pdf", status="failed"), models.Job(pdf="data/216500/216500.pdf", status="running"))
    db.commit()
    client.post("/collections", json={"name": "Ships", "archiveSeries": "7", "archiveIdentifier": "UMA-SR-000000007",
                                      "archiveTitle": "  Shipping manifests  ", "archiveItems": 12})
    listed = {c["name"]: c for c in client.get("/collections").json()}
    keys = ("bundles", "running", "failed", "pages", "reviewable", "reviewed", "unknownPages", "flagged", "pageTypes", "templates",
            "archiveIdentifier", "archiveTitle", "archiveItems")
    # 216498's newest job is done, so only 216499 counts as failed; the Unknown page is waiting for a type, and flagged for it
    assert {k: listed["Wilfred Prest Survey"][k] for k in keys} == {
        "bundles": 1, "running": 1, "failed": 1, "pages": 3, "reviewable": 2, "reviewed": 1, "unknownPages": 1, "flagged": 1,
        "pageTypes": 3, "templates": 1, "archiveIdentifier": "UMA-SR-000000842",
        "archiveTitle": "University of Melbourne Social Survey forms", "archiveItems": 45}
    assert {k: listed["Ships"][k] for k in keys} == {
        "bundles": 0, "running": 0, "failed": 0, "pages": 0, "reviewable": 0, "reviewed": 0, "unknownPages": 0, "flagged": 0,
        "pageTypes": 0, "templates": 0,  # its Unknown type doesn't count
        "archiveIdentifier": "UMA-SR-000000007", "archiveTitle": "Shipping manifests", "archiveItems": 12}
