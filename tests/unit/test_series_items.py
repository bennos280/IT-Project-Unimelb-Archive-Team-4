"""A series' dashboard asks the server for a page of its items at a time, searched, filtered and counted there, so a series
of tens of thousands of items stays quick."""
import json

import pytest

from backend.api import main
from backend.db import models
from backend.db.loader import stored_path


@pytest.fixture
def diaries(db, tmp_path, monkeypatch):
    """Series 2 lists items 2, 9, 10 and 100 from the archive: 9 is loaded (a page ready to review, one in no record) and 10 is
    being transcribed (two pages so far)."""
    monkeypatch.setattr(main, "settings", lambda: {"DATA": str(tmp_path), "OUTPUT": str(tmp_path / "output")})
    db.add(models.Collection(collection_id=2, name="Diaries", archive_series=524173, archive_identifier="UMA-SR-000001769"))
    db.flush()
    titles = {2: "Diary two", 9: "Diary nine", 10: "Diary ten", 100: "Diary hundred"}
    db.add_all([models.ArchiveItem(node=n, collection_id=2, identifier=f"UMA-IT-{n:09d}", title=t, pdf=f"{n}/{n}.pdf")
                for n, t in titles.items()] + [models.PageType(name="letter_2", label="Letter", collection_id=2),
                                               models.Bundle(bundle_id="9", source_pdf="9/9.pdf", collection_id=2)])
    db.flush()
    db.add(models.Survey(survey_id="9_00001", bundle_id="9"))
    db.flush()
    db.add_all([models.Page(page_id="9_00001", bundle_id="9", survey_id="9_00001", category="letter_2", import_path="a.png"),
                models.Page(page_id="9_00002", bundle_id="9", category="letter_2", import_path="b.png")])
    db.flush()
    db.add_all([models.Field(page_id=p, field_title="text", text_raw="Dear Sir") for p in ("9_00001", "9_00002")] +
               [models.Job(pdf=stored_path(tmp_path / "10" / "10.pdf"), status="running", kind="bundle")])
    db.commit()
    run = tmp_path / "output" / "10"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"pages": [{"file": "10_00001.png", "label": "review"},
                                                             {"file": "10_00002.png", "label": "blank"}]}))


def names(reply):
    return [item["name"] for item in reply["items"]]


def test_items_come_a_page_at_a_time_in_order_of_their_numbers_with_their_counts_and_the_series(client, diaries):
    first = client.get("/collections/2/items", params={"size": 2}).json()
    assert (names(first), first["page"], first["total"], first["all"]) == (["2", "9"], 0, 4, 4)
    assert first["items"][1]["counts"] == {"total": 2, "reviewable": 1, "unassigned": 1, "reviewed": 0, "ready": 1, "records": 1}
    assert first["items"][1]["archive"] == {"identifier": "UMA-IT-000000009", "title": "Diary nine"}
    assert first["totals"] == {"total": 4, "reviewable": 1, "unassigned": 1, "reviewed": 0, "ready": 1, "records": 1}  # with 10's two so far
    assert first["most"] == {"pages": 2, "records": 1}
    second = client.get("/collections/2/items", params={"size": 2, "page": 1}).json()
    assert (names(second), second["items"][0]["counts"]["total"], second["items"][0]["job"]["status"]) == (["10", "100"], 2, "running")
    assert client.get("/collections/2/items", params={"size": 2, "page": 7}).json()["page"] == 1  # past the end: the last


def test_items_are_found_by_number_title_or_identifier_and_by_status(client, diaries):
    def find(**params):
        return names(client.get("/collections/2/items", params=params).json())
    assert find(search=" NINE ") == ["9"]
    assert find(search="it-000000100") == ["100"]
    assert find(search="10") == ["10", "100"]
    assert find(status="Awaiting transcription") == ["2", "10", "100"]
    assert find(status="Transcription in progress") == ["10"]
    assert find(status="Ready to review") == find(status="Not in a survey") == ["9"]
    assert find(status="Reviewed") == []


def test_an_item_is_given_by_its_number_or_bundle_id_with_its_pages(client, diaries):
    item = client.get("/collections/2/items/9").json()
    assert (item["bundle"], item["loaded"], [p["status"] for p in item["pages"]]) == ("9", True, ["Ready to review", "Not in a survey"])
    assert client.get("/collections/2/items/100").json()["pages"] == []
    assert client.get("/collections/2/items/nowhere").json()["detail"] == "No such item."
    assert client.get("/collections/99/items").json()["detail"] == "No such series."


def test_a_record_names_its_item_as_the_dashboard_does(client, diaries):
    assert client.get("/survey/9_00001").json()["item"] == {
        "name": "9", "archive": {"identifier": "UMA-IT-000000009", "title": "Diary nine"}}


def test_an_item_that_is_one_record_gives_it_so_the_dashboard_opens_it_straight_away(client, db, diaries):
    def nine():
        return next(item for item in client.get("/collections/2/items").json()["items"] if item["name"] == "9")
    assert (nine()["record"], client.get("/survey/9_00001").json()["wholeItem"]) == (None, False)  # a page is in no record
    db.get(models.Page, "9_00002").survey_id = "9_00001"
    db.commit()
    assert (nine()["record"], client.get("/survey/9_00001").json()["wholeItem"]) == ("9_00001", True)
    assert [item["record"] for item in client.get("/collections/2/items").json()["items"] if item["name"] != "9"] == [None] * 3


def test_an_item_gives_its_records_and_a_record_the_ones_it_sits_inside_top_first(client, db, diaries):
    db.add(models.RecordLevel(collection_id=2, position=1, name="volume"))
    db.add(models.RecordLevel(collection_id=2, position=2, name="month"))
    db.add(models.Survey(survey_id="9", bundle_id="9"))
    db.flush()
    db.get(models.Survey, "9_00001").parent_id = "9"
    db.commit()
    assert client.get("/collections/2/items/9").json()["records"] == [{"id": "9", "parent": None}, {"id": "9_00001", "parent": "9"}]
    assert client.get("/survey/9_00001").json()["ancestors"] == []  # 9 holds just 9_00001 and no pages: the item opens past it
    db.get(models.Page, "9_00002").survey_id = "9"
    db.commit()
    assert client.get("/survey/9_00001").json()["ancestors"] == [{"id": "9", "name": "volume", "parent": None}]
    assert client.get("/survey/9_00001").json()["recordName"] == "month"


def test_an_item_found_in_two_places_under_the_data_folder_is_listed_once_and_its_pages_counted_once(client, diaries, tmp_path):
    for folder in (tmp_path / "9", tmp_path / "raw" / "Surveys" / "9"):
        folder.mkdir(parents=True)
        (folder / "9.pdf").write_bytes(b"")
    reply = client.get("/collections/2/items").json()
    assert (names(reply), reply["all"], reply["totals"]["total"]) == (["2", "9", "10", "100"], 4, 4)
    assert reply["items"][1]["pdf"] == stored_path(tmp_path / "9" / "9.pdf")  # the first of its copies in order
    assert sorted(row["bundle"] for row in client.get("/bundles", params={"collection": 2}).json()) == ["10", "100", "2", "9"]


def test_the_items_transcribed_are_all_the_loaded_ones_whatever_page_search_or_status_is_asked_for(client, db, diaries):
    db.add(models.Bundle(bundle_id="2", source_pdf="2/2.pdf", collection_id=2))
    db.commit()

    def asked(**params):
        reply = client.get("/collections/2/items", params=params).json()
        return names(reply), reply["transcribed"], reply["all"]
    assert asked() == (["2", "9", "10", "100"], 2, 4)
    assert asked(size=1, page=2) == (["10"], 2, 4)  # the page shown holds neither loaded item
    assert asked(search="hundred") == (["100"], 2, 4)
    assert asked(status="Awaiting transcription") == (["10", "100"], 2, 4)
