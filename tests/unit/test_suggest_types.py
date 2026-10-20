"""Suggest page types: some of an item's pages are drawn on one numbered contact sheet and the reading model is asked once what
kinds of page it shows (backend/pipeline/identify/suggest.py, and POST /collections/<id>/page-types/suggest on it)."""
import math
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from backend.api import main
from backend.db import app_settings, models
from backend.pipeline.identify import suggest

APP = {"provider": "codex", "model": "gpt-test", "effort": "medium"}
GAP = 16  # between tiles on the sheet


def make_pdf(path, pages=6, shapes=(), dark=()):
    """A real PDF of pages pages (200 x 300 points unless shapes gives each one's), those numbered in dark painted black."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as doc:
        for n in range(1, pages + 1):
            width, height = shapes[n - 1] if shapes else (200, 300)
            page = doc.new_page(width=width, height=height)
            page.insert_text((20, 50), f"page {n}")
            if n in dark:
                page.draw_rect(page.rect, fill=(0, 0, 0))
        doc.save(str(path))
    return path


def answering(monkeypatch, answer):
    """The reading model, answering answer; what it was asked is added to the list returned (the sheet is read while it is there)."""
    asked = []
    def ask(image, prompt, template, **choice):
        with Image.open(image) as sheet:
            asked.append({"image": Path(image), "format": sheet.format, "size": sheet.size, "prompt": prompt, "template": template,
                          "choice": choice})
        return answer
    monkeypatch.setattr(suggest, "ask", ask)
    return asked


def dark(pixel):
    return max(pixel) < 60


def light(pixel):
    return min(pixel) > 200


def grey(pixel):  # the sheet's background, #888888
    return all(abs(c - 0x88) < 12 for c in pixel)


def tile_corner(i, columns, height):
    return GAP + (i % columns) * (suggest.TILE + GAP), GAP + (i // columns) * (height + GAP)


# which pages
def test_pages_are_spread_evenly_starting_with_the_first():
    assert suggest.pick(100, 4) == [1, 26, 51, 76]
    assert suggest.pick(10, 3, "spread") == [1, 4, 7]
    assert suggest.pick(7, 3) == [1, 3, 5]  # whole steps down from 2.33 pages


def test_random_pages_are_in_order_without_repeats_and_the_same_for_the_same_seed():
    pages = suggest.pick(100, 5, "random", seed=1)
    assert pages == suggest.pick(100, 5, "random", seed=1) and pages != suggest.pick(100, 5, "random", seed=2)
    assert pages == sorted(set(pages)) and len(pages) == 5 and 1 <= pages[0] and pages[-1] <= 100
    assert pages != suggest.pick(100, 5)  # not the spread ones


def test_a_range_is_clamped_to_the_item_and_the_pages_are_spread_over_what_is_left_of_it():
    assert suggest.pick(50, 4, "range", 11, 30) == [11, 16, 21, 26]
    assert suggest.pick(20, 3, "range", 15, 999) == [15, 17, 19]  # the item ends at 20
    assert suggest.pick(20, 4, "range", None, 8) == [1, 3, 5, 7]
    assert suggest.pick(20, 4, "range") == suggest.pick(20, 4)  # no ends: the whole item
    assert suggest.pick(20, 4, "range", 18, 20) == [18, 19, 20]  # no more than count: all of them
    assert suggest.pick(10, 3, "spread", 5, 6) == [1, 4, 7]  # the ends mean something only to a range


def test_an_item_with_no_more_pages_than_asked_for_gives_all_of_them():
    assert suggest.pick(5, 16) == [1, 2, 3, 4, 5]
    assert suggest.pick(16, 16) == list(range(1, 17))
    assert suggest.pick(5, 16, "random", seed=1) == [1, 2, 3, 4, 5]
    assert suggest.pick(1, 16) == [1]


def test_no_more_than_30_pages_are_picked_and_at_least_one():
    spread = suggest.pick(100, 50)
    assert len(spread) == suggest.MOST == 30 and spread == sorted(set(spread)) and spread[0] == 1
    assert len(suggest.pick(100, 50, "random", seed=2)) == 30
    assert suggest.pick(30, 50) == list(range(1, 31))
    assert len(suggest.pick(45, 99)) == 30 and suggest.pick(45, 99)[-1] <= 45
    assert suggest.pick(10, 0) == [1]


# the contact sheet
def test_a_contact_sheet_is_one_jpeg_with_a_numbered_tile_for_each_page_in_the_order_given(tmp_path):
    pdf, out = make_pdf(tmp_path / "a.pdf", pages=6, dark={3}), tmp_path / "sheet.jpg"
    suggest.contact_sheet(pdf, [3, 1, 2, 4, 5], out)
    assert out.read_bytes()[:2] == b"\xff\xd8"
    with Image.open(out) as image:
        assert image.format == "JPEG"
        sheet = image.convert("RGB")
    tall, columns = suggest.TILE * 3 // 2, math.ceil(math.sqrt(5))  # a 200 x 300 point page drawn 400 wide is 600 high
    assert sheet.size == (columns * (suggest.TILE + GAP) + GAP, 2 * (tall + GAP) + GAP)
    for i in range(5):
        x, y = tile_corner(i, columns, tall)
        assert dark(sheet.getpixel((x + 3, y + 3)))  # the number's box
        assert max(high for low, high in sheet.crop((x, y, x + 64, y + 52)).getextrema()) > 200  # and the number in it
    x, y = tile_corner(0, columns, tall)
    assert dark(sheet.getpixel((x + 300, y + 300)))  # tile 1 is page 3, the black one
    x, y = tile_corner(1, columns, tall)
    assert light(sheet.getpixel((x + 300, y + 300)))  # tile 2 is page 1
    x, y = tile_corner(5, columns, tall)
    assert grey(sheet.getpixel((x + 200, y + 300))) and grey(sheet.getpixel((x + 3, y + 3)))  # the sixth place is empty
    assert grey(sheet.getpixel((2, 2)))


def test_pages_of_different_shapes_are_each_drawn_as_wide_as_a_tile_in_a_row_as_high_as_the_tallest(tmp_path):
    pdf, out = make_pdf(tmp_path / "a.pdf", pages=2, shapes=[(200, 300), (300, 200)]), tmp_path / "sheet.jpg"
    suggest.contact_sheet(pdf, [1, 2], out)
    with Image.open(out) as image:
        sheet = image.convert("RGB")
    tall = suggest.TILE * 3 // 2
    assert sheet.size == (2 * (suggest.TILE + GAP) + GAP, tall + 2 * GAP)
    x, y = tile_corner(1, 2, tall)
    assert light(sheet.getpixel((x + 200, y + 100))) and light(sheet.getpixel((x + suggest.TILE - 10, y + 150)))  # the landscape page
    assert grey(sheet.getpixel((x + 200, y + 500)))  # and nothing under it


def test_a_very_tall_page_is_shrunk_to_fit_and_each_row_is_as_tall_as_its_own_tallest_tile(tmp_path):
    shapes = [(200, 3000), (400, 300), (400, 300), (400, 300)]  # 400 x 6000 drawn: far taller than a tile may be
    pdf, out = make_pdf(tmp_path / "a.pdf", pages=4, shapes=shapes), tmp_path / "sheet.jpg"
    suggest.contact_sheet(pdf, [1, 2, 3, 4], out)
    with Image.open(out) as image:
        sheet = image.convert("RGB")
    tall, short = suggest.TALLEST, 300  # the first row holds the shrunk page, the second only 400 x 300 ones
    assert sheet.size == (2 * (suggest.TILE + GAP) + GAP, tall + short + 3 * GAP)
    x, y = GAP, GAP
    assert light(sheet.getpixel((x + 20, y + tall // 2))) and light(sheet.getpixel((x + 20, y + tall - 5)))  # its whole height is there
    assert grey(sheet.getpixel((x + 100, y + tall // 2)))  # shrunk to 40 wide, not stretched to the tile
    x, y = GAP, GAP + tall + GAP
    assert dark(sheet.getpixel((x + 3, y + 3))) and light(sheet.getpixel((x + 300, y + 150)))  # the second row starts under the first
    assert grey(sheet.getpixel((x + 300, y + short + 5)))  # and is only as tall as its own tiles


def test_a_contact_sheet_of_one_page_is_that_page_and_its_number(tmp_path):
    out = tmp_path / "sheet.jpg"
    suggest.contact_sheet(make_pdf(tmp_path / "a.pdf", pages=3), [3], out)
    with Image.open(out) as sheet:
        assert sheet.size == (suggest.TILE + 2 * GAP, suggest.TILE * 3 // 2 + 2 * GAP)


# asking the reading model
def test_the_model_is_asked_once_about_a_sheet_of_the_pages_and_its_tiles_are_taken_for_their_page_numbers(tmp_path, monkeypatch):
    pdf = make_pdf(tmp_path / "a.pdf", pages=9)
    asked = answering(monkeypatch, {"page_types": [
        {"name": "Membership form", "description": "A printed form with boxes", "tiles": "tiles 3 and 1"},
        {"name": "Letter", "description": "Typed, one paragraph", "tiles": "Tile 2, 4."},
        {"name": "Blank back", "description": "Nothing on it", "tiles": [5]}]})
    found = suggest.suggest(pdf, [2, 4, 6, 8, 9], APP)
    assert found == [{"label": "Membership form", "description": "A printed form with boxes", "pages": [2, 6]},  # in page order
                     {"label": "Letter", "description": "Typed, one paragraph", "pages": [4, 8]},
                     {"label": "Blank back", "description": "Nothing on it", "pages": [9]}]
    assert len(asked) == 1
    only = asked[0]
    assert (only["format"], only["choice"], only["template"]) == ("JPEG", APP, suggest.TEMPLATE)
    assert only["size"][0] == 3 * (suggest.TILE + GAP) + GAP  # five tiles, three across
    assert not only["image"].exists()  # the sheet isn't kept


def test_tiles_that_are_not_on_the_sheet_are_ignored_and_a_kind_with_none_left_has_no_pages(tmp_path, monkeypatch):
    answering(monkeypatch, {"page_types": [{"name": "Form", "tiles": "1, 2, 3, 4, 0, 99"}, {"name": "Cover", "tiles": "7"},
                                           {"name": "Letter", "tiles": "none of them"}, {"name": "Note", "tiles": None}, {"name": "Map"}]})
    found = suggest.suggest(make_pdf(tmp_path / "a.pdf"), [5, 6], APP)
    assert [(f["label"], f["pages"]) for f in found] == [("Form", [5, 6]), ("Cover", []), ("Letter", []), ("Note", []), ("Map", [])]
    assert all(f["description"] == "" for f in found)


def test_a_kind_named_again_or_with_no_name_is_dropped_and_names_and_descriptions_are_tidied(tmp_path, monkeypatch):
    answering(monkeypatch, {"page_types": [
        {"name": "  Letter\n from  home ", "description": " A  typed\nletter ", "tiles": "1"},
        {"name": "letter FROM home", "description": "again", "tiles": "2"},  # the same, as first said
        {"name": "", "tiles": "3"}, {"name": "   ", "tiles": "3"}, {"name": None, "tiles": "3"}, {"description": "unnamed", "tiles": "3"},
        {"name": "x" * 100, "description": "d" * 400, "tiles": "3"}]})
    found = suggest.suggest(make_pdf(tmp_path / "a.pdf"), [1, 2, 3], APP)
    assert found == [{"label": "Letter from home", "description": "A typed letter", "pages": [1]},
                     {"label": "x" * 60, "description": "d" * 300, "pages": [3]}]


@pytest.mark.parametrize("answer", [{}, {"page_types": None}, {"page_types": []}, {"other": [{"name": "Letter"}]}])
def test_an_answer_with_no_kinds_gives_none(tmp_path, monkeypatch, answer):
    answering(monkeypatch, answer)
    assert suggest.suggest(make_pdf(tmp_path / "a.pdf"), [1, 2], APP) == []


def test_the_prompt_counts_the_pages_and_names_the_page_types_the_series_has_and_what_the_person_said(tmp_path, monkeypatch):
    asked = answering(monkeypatch, {"page_types": []})
    pdf = make_pdf(tmp_path / "a.pdf")
    suggest.suggest(pdf, [1, 2, 3], APP, known=["Main page", "Letter"], hint="  The backs are mostly blank.\n")
    prompt = asked[0]["prompt"]
    assert prompt.startswith("These are 3 pages of one item")
    assert "already has these page types" in prompt and "Main page, Letter." in prompt
    assert prompt.endswith("\n\nFrom the person asking: The backs are mostly blank.")  # as typed, trimmed
    suggest.suggest(pdf, [1, 2], APP, known=(), hint="   ")
    assert asked[1]["prompt"].startswith("These are 2 pages") and "already has" not in asked[1]["prompt"] and "From the person" not in asked[1]["prompt"]


def test_a_request_the_model_cant_answer_is_not_caught_here(tmp_path, monkeypatch):
    def ask(image, prompt, template, **choice):
        raise SystemExit("rate limited")
    monkeypatch.setattr(suggest, "ask", ask)
    with pytest.raises(SystemExit, match="rate limited"):
        suggest.suggest(make_pdf(tmp_path / "a.pdf"), [1], APP)


# the endpoint
@pytest.fixture
def item(db, tmp_path, monkeypatch):
    """Item 5 of the first series, with an 8-page PDF where the API looks for it; item 6 of series 2, which has a page type of its
    own; and item 7 of the first series with no PDF known."""
    monkeypatch.setattr(main, "settings", lambda: {"DATA": str(tmp_path)})
    db.add(models.Collection(collection_id=2, name="Diaries", archive_series=524173, archive_identifier="UMA-SR-000001769"))
    db.flush()
    db.add_all([models.ArchiveItem(node=5, collection_id=1, identifier="UMA-IT-000000005", title="Five", pdf="5/5.pdf"),
                models.ArchiveItem(node=6, collection_id=2, identifier="UMA-IT-000000006", title="Six", pdf="6/6.pdf"),
                models.ArchiveItem(node=7, collection_id=1, identifier="UMA-IT-000000007", title="Seven", pdf=None),
                models.PageType(name="entry_2", label="Diary entry", collection_id=2)])
    db.commit()
    make_pdf(tmp_path / "5" / "5.pdf", pages=8)
    make_pdf(tmp_path / "6" / "6.pdf", pages=3)


@pytest.fixture
def chosen(db):
    app_settings.save_transcription_defaults(db, **APP)


ANSWER = {"page_types": [{"name": "Membership form", "description": "A printed form", "tiles": "1, 2"},
                         {"name": "Letter", "description": "Typed letter", "tiles": "3 and 4"}]}


def test_suggesting_asks_the_chosen_model_once_about_the_picked_pages_and_adds_nothing(client, db, item, chosen, monkeypatch):
    asked = answering(monkeypatch, ANSWER)
    before = client.get("/page-types", params={"collection": 1}).json()
    rows = db.query(models.PageType).count()
    reply = client.post("/collections/1/page-types/suggest", json={"item": "5", "count": 4, "hint": "The backs are blank."})
    assert reply.status_code == 200
    assert reply.json() == {"pages": [1, 3, 5, 7], "types": [
        {"label": "Membership form", "description": "A printed form", "pages": [1, 3]},
        {"label": "Letter", "description": "Typed letter", "pages": [5, 7]}]}
    assert len(asked) == 1
    prompt = asked[0]["prompt"]
    assert (asked[0]["choice"], asked[0]["format"], asked[0]["template"]) == (APP, "JPEG", suggest.TEMPLATE)
    assert asked[0]["size"][0] == 2 * (suggest.TILE + GAP) + GAP  # four tiles, two across
    assert prompt.startswith("These are 4 pages") and prompt.endswith("From the person asking: The backs are blank.")
    assert all(label in prompt for label in ("Main page", "Notes page", "Coded page"))  # the series' own
    assert "Unknown" not in prompt and "Diary entry" not in prompt
    assert client.get("/page-types", params={"collection": 1}).json() == before and db.query(models.PageType).count() == rows


def test_the_pages_can_be_picked_at_random_or_from_a_range_and_are_16_unless_asked_otherwise(client, item, chosen, monkeypatch):
    answering(monkeypatch, {"page_types": []})
    suggest_pages = lambda **body: client.post("/collections/1/page-types/suggest", json={"item": "5", **body}).json()["pages"]
    assert suggest_pages() == list(range(1, 9))  # 16 asked for, 8 there
    assert suggest_pages(count=3, pick="range", first=3, last=8) == [3, 5, 7]
    assert suggest_pages(count=3, pick="range", first=6, last=99) == [6, 7, 8]
    assert suggest_pages(count=3, pick="range", first=8, last=8) == [8]  # the last page alone is a range
    random_pages = suggest_pages(count=3, pick="random")
    assert len(random_pages) == 3 and random_pages == sorted(set(random_pages)) and set(random_pages) <= set(range(1, 9))


@pytest.mark.parametrize("fields", [{"first": 9}, {"first": 20, "last": 30}, {"first": 5, "last": 3}])  # past the end; before the start
def test_a_range_with_no_pages_in_it_is_400_and_the_model_isnt_asked(client, item, chosen, monkeypatch, fields):
    asked = answering(monkeypatch, ANSWER)
    reply = client.post("/collections/1/page-types/suggest", json={"item": "5", "pick": "range", **fields})
    assert (reply.status_code, reply.json()["detail"]) == (400, "That item has 8 pages: choose pages within them.")
    assert asked == []


def test_the_400_for_an_empty_range_counts_a_one_page_item_in_the_singular(client, item, chosen, tmp_path, monkeypatch):
    asked = answering(monkeypatch, ANSWER)
    make_pdf(tmp_path / "5" / "5.pdf", pages=1)
    reply = client.post("/collections/1/page-types/suggest", json={"item": "5", "pick": "range", "first": 2})
    assert (reply.status_code, reply.json()["detail"]) == (400, "That item has 1 page: choose pages within them.")
    assert asked == []


def test_suggesting_with_no_transcription_model_chosen_is_refused_before_anything_is_asked(client, item, monkeypatch):
    asked = answering(monkeypatch, ANSWER)
    reply = client.post("/collections/1/page-types/suggest", json={"item": "5"})
    assert (reply.status_code, reply.json()["detail"]) == (409, "Choose a transcription model on the Settings page first.")
    assert asked == []


INVALID = [{"count": 31}, {"count": 0}, {"hint": "x" * 1001}, {"pick": "sideways"}, {"pick": "range", "first": 0}, {"pick": "range", "last": 0},
           {"count": "many"}]


@pytest.mark.parametrize("fields", INVALID)
def test_a_request_the_endpoint_cant_make_sense_of_is_422(client, item, chosen, monkeypatch, fields):
    asked = answering(monkeypatch, ANSWER)
    assert client.post("/collections/1/page-types/suggest", json={"item": "5", **fields}).status_code == 422
    assert asked == []


def test_a_request_with_no_item_is_422_and_the_most_it_allows_is_30_pages_and_a_1000_character_hint(client, item, chosen, monkeypatch):
    answering(monkeypatch, ANSWER)
    assert client.post("/collections/1/page-types/suggest", json={}).status_code == 422
    assert client.post("/collections/1/page-types/suggest", json={"item": "5", "count": 30, "hint": "x" * 1000}).status_code == 200


def test_a_model_that_cant_answer_is_a_502_with_what_it_said(client, item, chosen, monkeypatch):
    def refuses(image, prompt, template, **choice):
        raise SystemExit("rate limited")
    monkeypatch.setattr(suggest, "ask", refuses)
    reply = client.post("/collections/1/page-types/suggest", json={"item": "5"})
    assert (reply.status_code, reply.json()["detail"]) == (502, "Page types couldn't be suggested: rate limited")

    def breaks(image, prompt, template, **choice):
        raise RuntimeError("x" * 500)
    monkeypatch.setattr(suggest, "ask", breaks)
    reply = client.post("/collections/1/page-types/suggest", json={"item": "5"})
    assert reply.status_code == 502 and reply.json()["detail"] == ("Page types couldn't be suggested: " + "x" * 500)[:400]

    def cant_draw(pdf, pages, out):  # not the model: any other failure is the same 502
        raise ValueError("page 3 can't be drawn")
    monkeypatch.setattr(suggest, "contact_sheet", cant_draw)
    reply = client.post("/collections/1/page-types/suggest", json={"item": "5"})
    assert (reply.status_code, reply.json()["detail"]) == (502, "Page types couldn't be suggested: page 3 can't be drawn")


@pytest.mark.parametrize("name", ["999", "abc", "-5", "6", "7", "1234567890"])
def test_an_item_the_series_doesnt_list_or_has_no_pdf_for_is_404_and_the_model_isnt_asked(client, item, chosen, monkeypatch, name):
    asked = answering(monkeypatch, ANSWER)  # 6 is series 2's, 7 has no PDF known
    assert client.post("/collections/1/page-types/suggest", json={"item": name}).status_code == 404
    assert asked == []


def test_an_items_pdf_not_here_yet_is_downloaded_first_and_an_archive_that_cant_send_it_is_a_502(client, item, chosen, tmp_path, monkeypatch):
    asked = answering(monkeypatch, ANSWER)
    (tmp_path / "5" / "5.pdf").unlink()
    got = []
    def fetch_pdf(pdf):
        got.append(pdf)
        make_pdf(pdf, pages=3)
    monkeypatch.setattr(main.scans, "fetch_pdf", fetch_pdf)
    reply = client.post("/collections/1/page-types/suggest", json={"item": "5"})
    assert reply.status_code == 200 and reply.json()["pages"] == [1, 2, 3] and got == [tmp_path / "5" / "5.pdf"]
    client.post("/collections/1/page-types/suggest", json={"item": "5"})
    assert len(got) == 1  # it is here now

    (tmp_path / "5" / "5.pdf").unlink()
    def cant(pdf):
        raise OSError("the archive has no PDF of item 5")
    monkeypatch.setattr(main.scans, "fetch_pdf", cant)
    asked.clear()
    reply = client.post("/collections/1/page-types/suggest", json={"item": "5"})
    assert (reply.status_code, reply.json()["detail"]) == (502, "Couldn't get its scans from the archive (the archive has no PDF of item 5).")
    assert asked == []
