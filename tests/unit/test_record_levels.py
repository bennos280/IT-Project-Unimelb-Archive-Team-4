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
    assert (grouping.rule(db, series)["levels"], len(grouping.rule(db, 1)["levels"])) == ([], 1)


def test_a_level_is_named_in_lower_case_and_says_which_page_types_start_or_join_one(client, db):
    setup(db)
    saved = put(client, 1, {"name": "  Household  Card ", "starts": ["main", "main"], "matched": ["coded"], "key": " number_of_dwelling "}).json()
    assert (saved["levels"], saved["recordName"]) == (
        [{"name": "household card", "starts": ["main"], "matched": ["coded"], "key": "number_of_dwelling"}], "household card")
    assert grouping.rule(db, 1)["levels"][0]["name"] == grouping.record_name(db, 1) == "household card"
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
    assert client.get("/collections/1").json()["levels"][0]["name"] == "household card"  # nothing refused was saved
    assert put(client, 9, {"name": "survey"}).status_code == 404


def test_the_number_field_must_stay_in_the_templates_of_the_page_types_that_group_by_it(client, db):
    setup(db)
    assert grouping.required_fields(db) == {"main": {"number_of_dwelling"}, "coded": {"number_of_dwelling"}}
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
    assert grouping.rule(db, series)["levels"] == [{"name": "letter", "starts": [first], "matched": [], "key": None}]
    assert client.get("/survey/L1").json()["recordName"] == "letter"
    assert put(client, series).json()["levels"] == []  # none again: each item one record
    assert grouping.rule(db, series)["levels"] == [] and not grouping.grouped(db, series)


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


def test_levels_nest_top_first_and_a_page_type_can_need_a_number_field_for_each_level_it_groups(client, db):
    setup(db)
    saved = put(client, 1, {"name": "box", "starts": ["main"]}, {"name": "survey", "starts": ["main"], "matched": ["coded"], "key": "number_of_dwelling"},
                {"name": "card", "starts": ["coded"], "key": "number_of_dwelling"}).json()
    assert ([level["name"] for level in saved["levels"]], saved["recordName"], saved["grouped"]) == (["box", "survey", "card"], "card", True)
    assert grouping.required_fields(db) == {"main": {"number_of_dwelling"}, "coded": {"number_of_dwelling"}}
    assert put(client, 1, {"name": "survey"}, {"name": "Survey"}).json()["detail"] == "There is already a level called survey."
    assert put(client, 1, {"name": "folder"}, {"name": "survey", "starts": ["main"], "key": "street"}).json()["detail"] == (
        "These page types' templates don't have 'street': Main page.")
    assert [level["name"] for level in client.get("/collections/1").json()["levels"]] == ["box", "survey", "card"]


def test_a_record_inside_another_says_so_is_named_by_its_level_and_its_export_keeps_it(client, db):
    setup(db)
    assert put(client, 1, {"name": "folder"}, {"name": "letter"}).status_code == 200
    add(db, models.Bundle(bundle_id="b", source_pdf="b.pdf"), models.Survey(survey_id="f", bundle_id="b"),
        models.Survey(survey_id="f-1", bundle_id="b", parent_id="f"), models.Survey(survey_id="g", bundle_id="b"),
        models.Survey(survey_id="g-1", bundle_id="b", parent_id="g"),
        models.Page(page_id="b_3", survey_id="g-1", bundle_id="b", category="notes", import_path="z.png"),
        models.Page(page_id="b_1", survey_id="f", bundle_id="b", category="notes", import_path="x.png"),
        models.Page(page_id="b_2", survey_id="f-1", bundle_id="b", category="main", import_path="y.png"),
        models.Field(page_id="b_2", field_title="address", text_raw="5 Peel St"))
    assert [(client.get(f"/survey/{s}").json()[k]) for s in ("f", "f-1") for k in ("parentId", "recordName")] == [None, "folder", "f", "letter"]
    # g holds only a record, no pages of its own: nothing to export, and g-1 names it
    assert {s["surveyId"]: s["parentId"] for s in client.get("/export?bundle_id=b").json()["surveys"]} == {"f": None, "f-1": "f", "g-1": "g"}
    db.delete(db.get(models.Survey, "f"))
    db.commit()
    assert db.query(models.Survey).filter_by(survey_id="f-1").count() == 0  # a record goes with the one it sits in


def test_levels_tried_on_an_item_read_show_its_records_by_the_numbers_reviewers_saved_and_save_nothing(client, db):
    setup(db)
    pages = [(1, "notes", None), (2, "main", "3"), (3, "coded", "3"), (4, "main", "7"), (5, "coded", "9")]
    add(db, models.Bundle(bundle_id="b", source_pdf="b.pdf"),
        *[models.Page(page_id=f"b_{n}", bundle_id="b", category=t, import_path="x.png") for n, t, _ in pages],
        *[models.Field(page_id=f"b_{n}", field_title="number_of_dwelling", text_raw=v) for n, _, v in pages if v],
        models.Edit(page_id="b_5", field_title="number_of_dwelling", edit_text="7", reviewer_id=1))  # 9 read, 7 saved
    survey = {"name": "survey", "starts": ["main"], "matched": ["coded"], "key": "number_of_dwelling"}
    tried = client.post("/collections/1/levels/preview", json={"levels": [survey], "item": "b"}).json()
    assert tried == {"records": [{"id": "b-3", "parent": None, "pages": ["b_2", "b_3"]}, {"id": "b-7", "parent": None, "pages": ["b_4", "b_5"]}],
                     "loose": ["b_1"], "problems": ["1 page(s) before the first Main page belong to no survey"]}
    nested = client.post("/collections/1/levels/preview", json={"levels": [{"name": "box", "starts": ["notes"]}, survey], "item": "b"}).json()
    assert [(r["id"], r["parent"]) for r in nested["records"]] == [("b_1", None), ("b_1-3", "b_1"), ("b_1-7", "b_1")]
    assert db.query(models.Survey).count() == 0 and len(client.get("/collections/1").json()["levels"]) == 1  # nothing saved
    db.get(models.Page, "b_5").needs_transcription = True  # to be read again as another type: its old number doesn't count
    db.commit()
    assert client.post("/collections/1/levels/preview", json={"levels": [survey], "item": "b"}).json()["problems"] == [
        "survey b-7: its pages don't agree on 'number of dwelling'", "1 page(s) before the first Main page belong to no survey"]
    assert client.post("/collections/1/levels/preview", json={"levels": [survey], "item": "nowhere"}).status_code == 404
    assert client.post("/collections/1/levels/preview", json={"levels": [{"name": "survey #1"}], "item": "b"}).json()["detail"] == (
        "A level's name is a word or two, like survey or letter.")
