"""A series' items are listed from the archive and added to its list (one by one once the archive confirms each is this
series', or the whole list at once, trusting it), and run into that series with its own page types."""
import json

import pytest

from backend import scans
from backend.api import main
from backend.db import app_settings, models
from backend.db.loader import stored_path

SERIES = "[UMA-SR-000001769] Strathfieldsaye Estate Diaries"


@pytest.fixture
def diaries(db, archive):
    """Series 2, the Strathfieldsaye diaries, on a fake archive: two listed items (one with no scans) and the items' pages."""
    db.add(models.Collection(collection_id=2, name="Diaries", archive_series=524173, archive_identifier="UMA-SR-000001769",
                             archive_title="Strathfieldsaye Estate Diaries"))
    db.commit()
    archive.add_series(524173, SERIES, "Identifier: UMA-SR-000001769", 18)
    archive.add_listing(524173, [(637675, "Diary 1878-1883", "UMA-IT-000147343", True),
                                 (637676, "Diary 1884 & 1885", "UMA-IT-000147344", False),
                                 (637678, "Diary 1886", "UMA-IT-000147346", True, "Access restrictions apply")], pages=2, count=30)
    archive.add_item(637675, "Diary 1878-1883", "UMA-IT-000147343", SERIES, [("1369539", "000-147-343-00001.pdf")])
    archive.add_item(637677, "Diary 1923", "UMA-IT-000147345", SERIES, [("1397319", "a.pdf"), ("999999", "a.pdf")])
    archive.add_item(637676, "Diary 1884 & 1885", "UMA-IT-000147344", SERIES, [])
    archive.add_item(216412, "Box Hill 00", "UMA-ITE-1973000200001", "[UMA-SR-000000842] Social Survey forms", [("423444", "x.pdf")])
    return archive


def test_a_series_items_are_listed_from_the_archive_saying_which_have_scans_and_which_are_listed_already(client, db, diaries):
    db.add(models.ArchiveItem(node=637675, collection_id=2, identifier="UMA-IT-000147343", title="Diary 1878-1883"))
    db.commit()
    listing = client.get("/collections/2/archive-items", params={"page": 2, "search": " diary "}).json()
    assert listing == {"items": [
        {"node": 637675, "title": "Diary 1878-1883", "identifier": "UMA-IT-000147343", "scanned": True, "added": True},
        {"node": 637676, "title": "Diary 1884 & 1885", "identifier": "UMA-IT-000147344", "scanned": False, "added": False},
        {"node": 637678, "title": "Diary 1886", "identifier": "UMA-IT-000147346", "scanned": False, "added": False}],  # Reading Room
        "page": 2, "pages": 2, "total": 30}
    [browse] = [r for r in diaries.requests if r.startswith("/nodes/browse?")]
    assert "bid=524173" in browse and "page=2" in browse and "keywords=diary" in browse and "order=asc" in browse


def test_listing_needs_a_series_linked_to_an_archive_that_answers(client, db):
    db.add(models.Collection(collection_id=2, name="Ships"))
    db.commit()
    assert client.get("/collections/2/archive-items").json()["detail"] == "This series isn't linked to the archive."
    db.get(models.Collection, 2).archive_series = 7
    db.commit()
    reply = client.get("/collections/2/archive-items")  # the tests never reach the internet
    assert reply.status_code == 502 and reply.json()["detail"].startswith("Couldn't reach the archive")


def test_chosen_items_are_added_once_the_archive_shows_them_in_this_series(client, db, diaries):
    db.add(models.ArchiveItem(node=111, collection_id=1, identifier="UMA-ITE-1", title="Listed"))
    db.commit()
    reply = client.post("/collections/2/items", json={"nodes": [637675, 637677, 216412, 111, 999, 637675]}).json()
    assert reply["added"] == [{"node": 637675, "title": "Diary 1878-1883"}, {"node": 637677, "title": "Diary 1923"}]
    assert reply["refused"] == [{"node": 216412, "reason": "It belongs to another series on the archive."},
                                {"node": 111, "reason": "A series lists it already."},
                                {"node": 999, "reason": "The archive has no item with that number."}]
    assert not [r for r in diaries.requests if r.startswith("/nodes/download")]  # its PDF is looked up when it is run
    db.expire_all()
    assert {i.node: i.pdf for i in db.query(models.ArchiveItem).filter_by(collection_id=2)} == {
        637675: "637675/637675.pdf", 637677: "637677/637677.pdf"}
    assert client.post("/collections/2/items", json={"nodes": []}).status_code == 400
    assert client.post("/collections/2/items", json={"nodes": list(range(26))}).status_code == 400


def test_an_added_item_is_listed_and_run_under_its_series_only(client, db, diaries, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "settings", lambda: {"DATA": str(tmp_path)})
    app_settings.save_transcription_defaults(db, "claude", "sonnet", "high")
    client.post("/collections/2/items", json={"nodes": [637675]})
    [listed] = client.get("/bundles?collection=2").json()
    assert (listed["name"], listed["loaded"], listed["archive"]) == (
        "637675", False, {"identifier": "UMA-IT-000147343", "title": "Diary 1878-1883"})
    assert listed["pdf"] == stored_path(tmp_path / "637675" / "637675.pdf")
    assert client.get("/bundles").json() == []
    assert client.post("/jobs", json={"pdf": listed["pdf"]}).status_code == 202
    assert [client.get(f"/collections/{n}").json()["running"] for n in (2, 1)] == [1, 0]


def test_the_whole_list_is_added_at_once_but_for_items_it_cant_download_or_a_series_lists(client, db, diaries):
    db.add(models.ArchiveItem(node=637675, collection_id=1, identifier="UMA-IT-000147343", title="Listed"))
    db.commit()
    assert client.post("/collections/2/items/all", json={"search": " diary "}).json() == {"added": 0, "skipped": 3}
    browses = [r for r in diaries.requests if r.startswith("/nodes/browse?")]
    assert len(browses) == 2 and all("keywords=diary" in r for r in browses)  # both of its pages
    assert not [r for r in diaries.requests if r.startswith("/nodes/download")]
    diaries.add_listing(524173, [(637679, "Diary 1887", "UMA-IT-000147347", True), (637680, "Diary 1888", "UMA-IT-000147348", True)],
                        pages=2)  # the fake sends the same page twice
    assert client.post("/collections/2/items/all", json={}).json() == {"added": 2, "skipped": 0}
    db.expire_all()
    assert {(i.node, i.title, i.pdf) for i in db.query(models.ArchiveItem).filter_by(collection_id=2)} == {
        (637679, "Diary 1887", "637679/637679.pdf"), (637680, "Diary 1888", "637680/637680.pdf")}


def test_a_series_linked_without_its_identifier_checks_items_against_the_archives(client, db, diaries):
    db.get(models.Collection, 2).archive_identifier = None
    db.commit()
    reply = client.post("/collections/2/items", json={"nodes": [637675, 216412]}).json()
    assert ([i["node"] for i in reply["added"]], [i["node"] for i in reply["refused"]]) == ([637675], [216412])
    diaries.add_series(524173, SERIES, "Access Status: Open for public access", 18)  # the archive shows no identifier
    refused = client.post("/collections/2/items", json={"nodes": [637677]})
    assert (refused.status_code, refused.json()["detail"]) == (
        400, "The archive shows no identifier for this series to check items against.")


def test_an_item_number_out_of_range_is_refused(client, db, diaries):
    for bad in ([0], [-5], [2**63]):
        reply = client.post("/collections/2/items", json={"nodes": bad})
        assert (reply.status_code, reply.json()["detail"]) == (400, "An item's number is a whole number from 1.")


def test_adding_a_list_from_an_archive_that_cant_be_reached_says_so(client, db):
    db.add(models.Collection(collection_id=2, name="Diaries", archive_series=524173, archive_identifier="UMA-SR-000001769"))
    db.commit()
    reply = client.post("/collections/2/items/all", json={})  # the tests never reach the internet
    assert reply.status_code == 502 and reply.json()["detail"].startswith("Couldn't reach the archive")


def test_a_run_saves_the_series_it_is_loaded_into(tmp_path):
    from backend.pipeline import run as pipeline
    pipeline.Run(tmp_path / "b.pdf", tmp_path / "out", collection=2).save()
    assert json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))["collection"] == 2


def test_a_list_of_over_a_thousand_items_is_left_for_a_search_to_narrow(client, db, diaries):
    diaries.add_listing(524173, [(637679, "Diary 1887", "UMA-IT-000147347", True)], pages=42, count=29326)
    refused = client.post("/collections/2/items/all", json={})
    assert (refused.status_code, refused.json()["detail"]) == (
        400, "There are 29,326 items in this list, more than 1,000 to add at once. Search to narrow it down.")
    assert len([r for r in diaries.requests if r.startswith("/nodes/browse?")]) == 1


def test_an_added_items_pdf_is_its_newest_original_looked_up_when_it_is_downloaded(diaries, tmp_path):
    diaries.files.update({"999999": b"%PDF old", "1397319": b"%PDF new"})
    scans.fetch_pdf(tmp_path / "637677" / "637677.pdf")
    assert (tmp_path / "637677" / "637677.pdf").read_bytes() == b"%PDF new"
    with pytest.raises(OSError, match="the archive has no PDF of item 637676"):
        scans.fetch_pdf(tmp_path / "637676" / "637676.pdf")


def test_a_page_takes_only_a_page_type_of_its_own_series(client, db):
    db.add_all([models.Reviewer(reviewer_id=1, name="Ben"), models.Collection(collection_id=2, name="Letters")])
    db.flush()
    db.add_all([models.PageType(name="docket", label="Docket", collection_id=2),
                models.Bundle(bundle_id="b", source_pdf="b.pdf")])
    db.flush()
    db.add(models.Page(page_id="b_00001", bundle_id="b", category="main", import_path="x.png"))
    db.commit()
    refused = client.put("/pages/b_00001/type", json={"pageType": "docket", "reviewerId": 1})
    assert (refused.status_code, refused.json()["detail"]) == (400, "No page type called docket in this page's series.")


def test_sorting_gives_only_the_series_own_page_types_and_sends_the_rest_to_review(tmp_path, monkeypatch):
    from backend.pipeline import run as pipeline
    from backend.pipeline.identify import identify
    for n in (1, 2):
        (tmp_path / f"b_{n:05d}.png").write_bytes(b"")
    monkeypatch.setattr(identify, "identify_pages", lambda images, model: [
        {"label": "main", "confidence": 1.0, "distance": 0.0}, {"label": "docket", "confidence": 1.0, "distance": 0.0}])
    run = pipeline.Run(tmp_path, tmp_path / "out", page_types={"docket"})
    pipeline.step_identify(run)
    assert [p["label"] for p in run.pages] == ["review", "docket"]
    assert [r["file"] for r in run.review] == ["b_00001.png"]


def test_an_upload_cant_take_the_number_of_an_item_added_from_the_archive(client, db, tmp_path, monkeypatch):
    from backend.api import uploads
    monkeypatch.setattr(uploads, "settings", lambda: {"DATA": str(tmp_path)})
    db.add(models.ArchiveItem(node=637675, collection_id=1, identifier="UMA-IT-1", title="A", pdf="637675/637675.pdf"))
    db.commit()
    refused = client.post("/bundles/upload", params={"bundle": "637675", "filename": "mine.pdf"}, content=b"%PDF")
    assert (refused.status_code, refused.json()["detail"]) == (
        409, "Item number 637675 belongs to an archive PDF. Choose a different item number.")
    refused = client.post("/bundles/upload", params={"bundle": "1", "filename": "637675.pdf"}, content=b"%PDF")
    assert (refused.status_code, refused.json()["detail"]) == (
        409, "This PDF belongs to archive item 637675. Use that item number.")
