"""Each series names its records (the Wilfred Prest Survey's are surveys), and in a series where no page type starts a
record each page is a record of its own."""
from backend.db import models


def add(db, *rows):
    for row in rows:  # one at a time: the db checks foreign keys and the models have no relationships to order them
        db.add(row)
        db.flush()
    db.commit()


def letters(client, db):
    """A second series whose records are letters and aren't grouped: one item, one Unknown page of free text."""
    series = client.post("/collections", json={"name": "Letters", "archiveSeries": "7"}).json()["id"]
    client.patch(f"/collections/{series}", json={"recordName": "Letter "})
    unknown = db.query(models.PageType).filter_by(collection_id=series, unknown=True).one().name
    add(db, models.Bundle(bundle_id="L1", source_pdf="L1.pdf", collection_id=series),
        models.Survey(survey_id="L1_00001", bundle_id="L1"),
        models.Page(page_id="L1_00001", survey_id="L1_00001", bundle_id="L1", category=unknown, import_path="x.png"),
        models.Field(page_id="L1_00001", field_title="text", text_raw="Dear Sir"))
    return series, unknown


def test_a_series_names_its_records_in_lower_case_and_an_empty_name_is_record(client):
    assert client.get("/collections/1").json()["recordName"] == "survey"
    assert client.patch("/collections/1", json={"recordName": "  Household  Card "}).json()["recordName"] == "household card"
    assert client.patch("/collections/1", json={"name": "Prest"}).json()["recordName"] == "household card"  # left out: kept
    assert client.patch("/collections/1", json={"recordName": ""}).json()["recordName"] == "record"
    for bad in ("survey #1", "three word name", "a--", "x" * 41):
        refused = client.patch("/collections/1", json={"recordName": bad})
        assert (refused.status_code, refused.json()["detail"]) == (400, "A record name is a word or two, like survey or letter.")
    assert client.patch("/collections/1", json={"recordName": "o'clock card"}).status_code == 200


def test_a_series_is_grouped_while_one_of_its_page_types_starts_a_record(client, db):
    series, _ = letters(client, db)
    assert client.get("/collections/1").json()["grouped"] is True
    assert client.get(f"/collections/{series}").json()["grouped"] is False
    add(db, models.Reviewer(reviewer_id=1, name="Ben"))
    first = client.post("/page-types", json={"label": "First page", "reviewerId": 1, "collectionId": series}).json()["name"]
    assert client.patch(f"/page-types/{first}", json={"startsRecord": True}).status_code == 200
    assert client.get(f"/collections/{series}").json()["grouped"] is True
    assert client.get("/survey/L1_00001").json()["grouped"] is True


def test_an_ungrouped_series_names_its_record_its_own_way(client, db):
    series, unknown = letters(client, db)
    record = client.get("/survey/L1_00001").json()
    assert (record["recordName"], record["grouped"]) == ("letter", False)
    [page] = record["pages"]
    assert [f["group"] for f in page["fields"]] == ["Letter details"]
    assert [f["reason"] for f in page["flags"] if f["id"] == "other-page"] == [
        "The computer couldn't tell what this page is, so it wasn't read. Check what it is, and type anything worth keeping."]
    refused = client.patch(f"/page-types/{unknown}", json={"startsRecord": True})
    assert refused.json()["detail"] == "Unknown pages aren't read, so they can't start or join a letter."
    client.patch(f"/collections/{series}", json={"recordName": "envelope"})
    refused = client.patch(f"/page-types/{unknown}", json={"startsRecord": True})
    assert refused.json()["detail"] == "Unknown pages aren't read, so they can't start or join an envelope."


def test_an_unknown_page_grouped_with_others_is_flagged_as_part_of_their_survey(client, db):
    add(db, models.Bundle(bundle_id="6789", source_pdf="6789.pdf"), models.Survey(survey_id="s", bundle_id="6789"),
        models.Page(page_id="s_1", survey_id="s", bundle_id="6789", category="main", import_path="x.png"),
        models.Page(page_id="s_2", survey_id="s", bundle_id="6789", category="other", import_path="y.png"),
        models.Field(page_id="s_2", field_title="text", text_raw="Moved away"))
    record = client.get("/survey/s").json()
    assert (record["recordName"], record["grouped"]) == ("survey", True)
    page = record["pages"][1]
    assert [f["group"] for f in page["fields"]] == ["Survey details"]
    assert [f["reason"] for f in page["flags"] if f["id"] == "other-page"] == [
        "The computer couldn't tell what this page is, so it wasn't read. It is in this survey because it comes after the "
        "survey's first page in the scan: check it belongs here, and type anything worth keeping."]
