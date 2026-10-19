"""A series' levels of record (PUT /collections/{id}/levels): what each is called and the page types that start or join one,
which the pipeline's group step reads (backend/db/grouping.py); a series with none has each item as one record."""
from backend.db import grouping, models
from tests.unit.test_page_type_settings import setup


def add(db, *rows):
    for row in rows:  # one at a time: the db checks foreign keys and the models have no relationships to order them
        db.add(row)
        db.flush()
    db.commit()


def letters(client, db):
    """A second series with no levels: one item, one Unknown page of free text."""
    series = client.post("/collections", json={"name": "Letters", "archiveSeries": "7"}).json()["id"]
    unknown = db.query(models.PageType).filter_by(collection_id=series, unknown=True).one().name
    add(db, models.Bundle(bundle_id="L1", source_pdf="L1.pdf", collection_id=series),
        models.Survey(survey_id="L1", bundle_id="L1"),
        models.Page(page_id="L1_00001", survey_id="L1", bundle_id="L1", category=unknown, import_path="x.png"),
        models.Field(page_id="L1_00001", field_title="text", text_raw="Dear Sir"))
    return series, unknown


def put(client, series, *levels):
    return client.put(f"/collections/{series}/levels", json={"levels": list(levels)})


def test_prest_has_one_level_its_surveys_and_a_new_series_none(client, db):
    series, _ = letters(client, db)
    prest = client.get("/collections/1").json()
    assert (prest["levels"], prest["recordName"], prest["grouped"]) == (
        [{"name": "survey", "starts": ["main"], "matched": ["coded"], "key": "number_of_dwelling"}], "survey", True)
    other = client.get(f"/collections/{series}").json()
    assert (other["levels"], other["recordName"], other["grouped"]) == ([], "record", False)
    assert grouping.rule(db, series)["one_per_item"] and not grouping.rule(db, 1)["one_per_item"]


def test_a_level_is_named_in_lower_case_and_says_which_page_types_start_or_join_one(client, db):
    setup(db)
    saved = put(client, 1, {"name": "  Household  Card ", "starts": ["main", "main"], "matched": ["coded"], "key": " number_of_dwelling "}).json()
    assert (saved["levels"], saved["recordName"]) == (
        [{"name": "household card", "starts": ["main"], "matched": ["coded"], "key": "number_of_dwelling"}], "household card")
    assert grouping.rule(db, 1)["record"] == "household card"
    for level, problem in [
            ({"name": "survey #1"}, "A level's name is a word or two, like survey or letter."),
            ({"name": "survey", "starts": ["nowhere"]}, "A level's page types must be this series' own."),
            ({"name": "survey", "starts": ["other"]}, "Unknown pages aren't read, so they can't start or join a survey."),
            ({"name": "survey", "starts": ["coded"], "matched": ["coded"], "key": "number_of_dwelling"},
             "A page type starts a survey or joins one by number, not both."),
            ({"name": "envelope", "matched": ["coded"]}, "Pages join an envelope by its number field: set one first."),
            ({"name": "survey", "matched": ["coded"], "key": "number_of_dwelling"},
             "Pages can only join a survey a page type starts: choose one that starts it."),
            ({"name": "survey", "starts": ["main"], "key": "Bad key"}, "A field name is lower-case letters, digits and _, starting with a letter."),
            ({"name": "survey", "starts": ["main"], "matched": ["coded"], "key": "address"},
             "These page types' templates don't have 'address': Coded page.")]:
        refused = put(client, 1, level)
        assert (refused.status_code, refused.json()["detail"]) == (400, problem)
    assert put(client, 1, {"name": "survey"}, {"name": "letter"}).json()["detail"] == "A series has one level for now."
    assert client.get("/collections/1").json()["levels"][0]["name"] == "household card"  # nothing refused was saved
    assert put(client, 9, {"name": "survey"}).status_code == 404


def test_the_number_field_must_stay_in_the_templates_of_the_page_types_that_group_by_it(client, db):
    setup(db)
    assert grouping.required_fields(db) == {"main": "number_of_dwelling", "coded": "number_of_dwelling"}
    coded = {"body": '{"text": null}', "basedOn": client.get("/instructions/coded").json()[0]["id"], "reviewerId": 1}
    assert client.post("/instructions/coded", json=coded).json()["detail"] == ["coded: needs 'number_of_dwelling'"]
    assert put(client, 1, {"name": "survey", "starts": ["main"]}).status_code == 200  # by page order: no number field
    assert grouping.required_fields(db) == {}
    assert client.post("/instructions/coded", json=coded).status_code == 201


def test_with_no_levels_each_item_is_one_record_and_with_one_its_page_types_start_them(client, db):
    series, unknown = letters(client, db)
    record = client.get("/survey/L1").json()
    assert (record["recordName"], record["grouped"]) == ("record", False)
    [page] = record["pages"]
    assert [f["group"] for f in page["fields"]] == ["Record details"]
    assert [f["reason"] for f in page["flags"] if f["id"] == "other-page"] == [
        "The computer couldn't tell what this page is, so it wasn't read. Check what it is, and type anything worth keeping."]
    add(db, models.Reviewer(reviewer_id=1, name="Ben"))
    first = client.post("/page-types", json={"label": "First page", "reviewerId": 1, "collectionId": series}).json()["name"]
    assert put(client, series, {"name": "letter", "starts": [first]}).json()["grouped"] is True
    assert (grouping.rule(db, series)["starts"], grouping.rule(db, series)["record"]) == ({first}, "letter")
    assert client.get("/survey/L1").json()["recordName"] == "letter"
    assert put(client, series).json()["levels"] == []  # none again: each item one record
    assert grouping.rule(db, series)["one_per_item"]


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


def test_an_unknown_page_of_an_item_that_is_one_record_isnt_said_to_follow_its_first_page(client, db):
    series, unknown = letters(client, db)
    add(db, models.Page(page_id="L1_00002", survey_id="L1", bundle_id="L1", category=unknown, import_path="y.png"),
        models.Field(page_id="L1_00002", field_title="text", text_raw="Yours faithfully"))
    pages = client.get("/survey/L1").json()["pages"]
    assert [f["reason"] for p in pages for f in p["flags"] if f["id"] == "other-page"] == [
        "The computer couldn't tell what this page is, so it wasn't read. Check what it is, and type anything worth keeping."] * 2
