"""A series' levels of record (PUT /collections/{id}/levels): what each is called and what one is made of, in order, which the
pipeline's group step reads (backend/db/grouping.py); a series with none has each item as one record."""
import pytest

from backend import scans
from backend.db import grouping, models
from tests.unit.test_page_type_settings import setup

# The Prest survey's level, as migration 023 makes it: a main form starts one (a second sheet is the same survey), then any
# notes, and its one coded card is matched by dwelling number wherever it was filed
MAIN = {"type": "main", "count": "one_or_more", "how": "starts"}
NOTES = {"type": "notes", "count": "any", "how": "follows"}
CODED = {"type": "coded", "count": "one", "how": "matched"}
SURVEY = {"name": "survey", "parts": [MAIN, NOTES, CODED], "key": "number_of_dwelling"}


def made_of(*types):  # parts that start (the first) or follow, one of each
    return [{"type": t, "count": "one", "how": "starts" if i == 0 else "follows"} for i, t in enumerate(types)]


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
        [{**SURVEY, "starts": ["main"], "matched": ["coded"]}], "survey", True)
    other = client.get(f"/collections/{series}").json()
    assert (other["levels"], other["recordName"], other["grouped"]) == ([], "record", False)
    assert (grouping.rule(db, series)["levels"], len(grouping.rule(db, 1)["levels"])) == ([], 1)
    assert grouping.rule(db, 1)["unknown"] == ["other"]  # its pages aren't flagged as a type a survey isn't made of


def test_a_level_is_named_in_lower_case_and_made_of_its_series_page_types_in_order(client, db):
    setup(db)
    add(db, models.InstructionVersion(kind="main", body='{"number_of_dwelling": null, "address": null, "residents": [{"age": null}]}', sha256="m2"))
    saved = put(client, 1, {**SURVEY, "name": "  Household  Card ", "key": " number_of_dwelling "}).json()
    assert (saved["levels"], saved["recordName"]) == (
        [{**SURVEY, "name": "household card", "starts": ["main"], "matched": ["coded"]}], "household card")
    assert grouping.rule(db, 1)["levels"][0]["name"] == grouping.record_name(db, 1) == "household card"
    for level, problem in [
            ({"name": "survey #1"}, "A level's name is a word or two, like survey or letter."),
            ({"name": "survey", "parts": made_of("nowhere")}, "A level's page types must be this series' own."),
            ({"name": "survey", "parts": made_of("other")}, "Unknown pages aren't read, so a survey can't be made of them."),
            ({"name": "survey", "parts": made_of("main", "main")}, "Each page type is in a survey once."),
            ({"name": "survey", "parts": [NOTES, MAIN]}, "The first page type starts a survey, and only it."),
            ({"name": "survey", "parts": [MAIN, {**NOTES, "how": "starts"}]}, "The first page type starts a survey, and only it."),
            ({"name": "envelope", "parts": [MAIN, CODED]}, "Pages are matched to an envelope by its number field: set one first."),
            ({"name": "survey", "parts": [MAIN], "key": "Bad key"}, "A field name is lower-case letters, digits and _, starting with a letter."),
            ({"name": "survey", "key": "number_of_dwelling"},
             "A survey's number is read from its page types: add one first, or choose no number field."),
            ({**SURVEY, "key": "address"}, "These page types' templates don't have 'address': Coded page."),
            ({"name": "survey", "parts": [MAIN], "key": "residents"}, "These page types' templates don't have 'residents': Main page.")]:
        refused = put(client, 1, level)
        assert (refused.status_code, refused.json()["detail"]) == (400, problem)
    assert client.get("/collections/1").json()["levels"][0]["name"] == "household card"  # nothing refused was saved
    assert put(client, 9, {"name": "survey"}).status_code == 404


def test_the_number_field_must_stay_in_the_templates_of_the_page_types_that_group_by_it(client, db):
    setup(db)
    assert grouping.required_fields(db) == {"main": {"number_of_dwelling"}, "coded": {"number_of_dwelling"}}
    coded = {"body": '{"text": null}', "basedOn": client.get("/instructions/coded").json()[0]["id"], "reviewerId": 1}
    assert client.post("/instructions/coded", json=coded).json()["detail"] == ["coded: needs 'number_of_dwelling'"]
    assert put(client, 1, {"name": "survey", "parts": [MAIN, NOTES]}).status_code == 200  # by page order: no number field
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
    assert put(client, series, {"name": "letter", "parts": made_of(first)}).json()["grouped"] is True
    assert grouping.rule(db, series)["levels"] == [{"name": "letter", "parts": made_of(first), "key": None, "starts": [first], "matched": []}]
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
    saved = put(client, 1, {"name": "box", "parts": made_of("main")}, SURVEY,
                {"name": "card", "parts": made_of("coded"), "key": "number_of_dwelling"}).json()
    assert ([level["name"] for level in saved["levels"]], saved["recordName"], saved["grouped"]) == (["box", "survey", "card"], "card", True)
    assert grouping.required_fields(db) == {"main": {"number_of_dwelling"}, "coded": {"number_of_dwelling"}}
    assert put(client, 1, {"name": "survey"}, {"name": "Survey"}).json()["detail"] == "There is already a level called survey."
    assert put(client, 1, {"name": "folder"}, {"name": "survey", "parts": [MAIN], "key": "street"}).json()["detail"] == (
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
    survey = SURVEY
    tried = client.post("/collections/1/levels/preview", json={"levels": [survey], "item": "b"}).json()
    assert tried == {"records": [{"id": "b-3", "parent": None, "pages": ["b_2", "b_3"]}, {"id": "b-7", "parent": None, "pages": ["b_4", "b_5"]}],
                     "loose": ["b_1"], "pageTypes": {"b_1": "Notes page", "b_2": "Main page", "b_3": "Coded page", "b_4": "Main page", "b_5": "Coded page"},
                     "problems": [{"page": "b_1", "record": None, "reason": "1 page(s) before the first Main page belong to no survey"}]}
    nested = client.post("/collections/1/levels/preview", json={"levels": [{"name": "box", "parts": made_of("notes")}, survey], "item": "b"}).json()
    assert [(r["id"], r["parent"]) for r in nested["records"]] == [("b_1", None), ("b_1-3", "b_1"), ("b_1-7", "b_1")]
    assert nested["problems"] == []  # the box's main forms and coded cards are its surveys'
    assert db.query(models.Survey).count() == 0 and len(client.get("/collections/1").json()["levels"]) == 1  # nothing saved
    db.get(models.Page, "b_5").needs_transcription = True  # to be read again as another type: its old number doesn't count
    db.commit()
    assert client.post("/collections/1/levels/preview", json={"levels": [survey], "item": "b"}).json()["problems"] == [
        {"page": "b_4", "record": "b-7", "reason": "its pages don't agree on 'number of dwelling'"},
        {"page": "b_1", "record": None, "reason": "1 page(s) before the first Main page belong to no survey"}]
    assert client.post("/collections/1/levels/preview", json={"levels": [survey], "item": "nowhere"}).status_code == 404
    assert client.post("/collections/1/levels/preview", json={"levels": [{"name": "survey #1"}], "item": "b"}).json()["detail"] == (
        "A level's name is a word or two, like survey or letter.")


def test_a_page_is_shown_small_from_its_items_pdf_or_its_scan_here_and_never_fetched(client, db, tmp_path, monkeypatch):
    for asked in ("archive_scan", "archive_bundle", "archive_download"):
        monkeypatch.setattr(scans, asked, lambda *args, **kwargs: pytest.fail("the archive was asked"))
    import pymupdf
    pdf = tmp_path / "t.pdf"
    with pymupdf.open() as doc:
        for _ in range(2):
            doc.new_page(width=600, height=800)
        doc.save(pdf)
    add(db, models.Bundle(bundle_id="t", source_pdf=str(pdf)), models.Bundle(bundle_id="u", source_pdf=str(tmp_path / "gone.pdf")),
        *[models.Page(page_id=page, bundle_id=bundle, category="main", import_path=str(tmp_path / f"{page}.png"))
          for page, bundle in (("t_00002", "t"), ("t_00009", "t"), ("u_00001", "u"))])
    shown = client.get("/pages/t_00002/thumbnail")
    assert (shown.status_code, shown.headers["content-type"], shown.content[:2]) == (200, "image/jpeg", bytes([0xFF, 0xD8]))
    from PIL import Image
    import io
    assert Image.open(io.BytesIO(shown.content)).size == (240, 320)  # 240 wide, in proportion
    assert [client.get(f"/pages/{page}/thumbnail").status_code for page in ("t_00009", "u_00001", "nowhere")] == [404] * 3
    # a folder of scans: each page's own, whatever it's called; one not here yet is drawn once it is
    Image.new("L", (300, 400)).save(tmp_path / "front.png")
    add(db, models.Bundle(bundle_id="v", source_pdf=str(tmp_path / "v")),
        *[models.Page(page_id=page, bundle_id="v", category="main", import_path=str(tmp_path / f"{scan}.png"))
          for page, scan in (("v_front", "front"), ("v_00002", "later"))])
    assert [client.get(f"/pages/{page}/thumbnail").status_code for page in ("v_front", "v_00002")] == [200, 404]
    Image.new("RGB", (300, 400)).save(tmp_path / "later.png")
    shown = client.get("/pages/v_00002/thumbnail")
    assert (shown.status_code, Image.open(io.BytesIO(shown.content)).size) == (200, (240, 320))
    # else the scan the archive sent before, kept in OUTPUT/scans/<item>/; a page called by no number has none there
    monkeypatch.setattr(scans, "settings", lambda: {"OUTPUT": str(tmp_path / "out")})
    (tmp_path / "out" / "scans" / tmp_path.name).mkdir(parents=True)
    Image.new("RGB", (300, 400)).save(tmp_path / "out" / "scans" / tmp_path.name / "0003.jpg")
    add(db, *[models.Page(page_id=page, bundle_id="v", category="main", import_path=str(tmp_path / "none.png")) for page in ("v_00003", "v_\u00b2")])
    assert [client.get(f"/pages/{page}/thumbnail").status_code for page in ("v_00003", "v_\u00b2")] == [200, 404]


def test_a_record_with_too_many_or_too_few_of_a_part_or_a_page_type_it_isnt_made_of_is_flagged(client, db):
    setup(db)
    pages = [(1, "main", "3"), (2, "notes", None), (3, "notes", None), (4, "coded", "3"), (5, "coded", "3"), (6, "main", "8"), (7, "letter", None),
             (8, "other", None)]  # an Unknown page: flagged as unread, not as a type the survey isn't made of
    add(db, models.PageType(name="letter", label="Letter page"), models.Bundle(bundle_id="b", source_pdf="b.pdf"),
        *[models.Page(page_id=f"b_{n}", bundle_id="b", category=t, import_path="x.png") for n, t, _ in pages],
        *[models.Field(page_id=f"b_{n}", field_title="number_of_dwelling", text_raw=v) for n, _, v in pages if v])
    level = {**SURVEY, "parts": [MAIN, {**NOTES, "count": "at_most_one"}, CODED]}
    tried = client.post("/collections/1/levels/preview", json={"levels": [level], "item": "b"}).json()
    assert [(r["id"], r["pages"]) for r in tried["records"]] == [("b-3", ["b_1", "b_2", "b_3", "b_4", "b_5"]), ("b-8", ["b_6", "b_7", "b_8"])]
    assert tried["problems"] == [
        {"page": "b_1", "record": "b-3", "reason": "expected at most one Notes page, found 2; expected one Coded page, found 2"},
        {"page": "b_6", "record": "b-8", "reason": "expected one Coded page, found none; Letter page isn't part of a survey"}]
    level = {**SURVEY, "parts": [MAIN, {**NOTES, "count": "one_or_more"}, CODED]}
    assert [p["reason"] for p in client.post("/collections/1/levels/preview", json={"levels": [level], "item": "b"}).json()["problems"]] == [
        "expected one Coded page, found 2",
        "expected at least one Notes page, found none; expected one Coded page, found none; Letter page isn't part of a survey"]


def test_a_level_isnt_flagged_for_the_page_types_of_the_levels_below_and_its_problems_are_its_own(client, db):
    setup(db)
    pages = [(1, "main", "3"), (2, "coded", "3"), (3, "main", "8"), (4, "coded", "8")]
    add(db, models.Bundle(bundle_id="b", source_pdf="b.pdf"),
        *[models.Page(page_id=f"b_{n}", bundle_id="b", category=t, import_path="x.png") for n, t, _ in pages],
        *[models.Field(page_id=f"b_{n}", field_title="number_of_dwelling", text_raw=v) for n, _, v in pages])
    box = {"name": "box", "parts": [{"type": "main", "count": "one", "how": "starts"}, {"type": "notes", "count": "one", "how": "follows"}]}
    tried = client.post("/collections/1/levels/preview", json={"levels": [box, SURVEY], "item": "b"}).json()
    assert [(r["id"], r["parent"]) for r in tried["records"]] == [("b_1", None), ("b_1-3", "b_1"), ("b_3", None), ("b_3-8", "b_3")]
    # each box lacks its notes page, said of the box though its first page is also its survey's; its coded cards are its surveys'
    assert tried["problems"] == [{"page": "b_1", "record": "b_1", "reason": "expected one Notes page, found none"},
                                 {"page": "b_3", "record": "b_3", "reason": "expected one Notes page, found none"}]
