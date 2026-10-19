"""A series' items are listed from the archive and added to its list (one by one once the archive confirms each is this
series', or the whole list at once, trusting it), and run into that series with its own page types."""
import json

import pytest

from backend import scans, worker
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


def test_adding_a_series_whole_list_is_queued_and_the_worker_adds_each_downloadable_item_no_series_lists(client, db, diaries,
                                                                                                           monkeypatch):
    monkeypatch.setattr(worker, "PAUSE", 0)
    db.add(models.ArchiveItem(node=637675, collection_id=1, identifier="UMA-IT-000147343", title="Listed"))
    db.commit()
    queued = client.post("/collections/2/items/all", json={"search": " diary "})
    assert (queued.status_code, queued.json()["kind"], queued.json()["search"]) == (202, "items", "diary")
    again = client.post("/collections/2/items/all", json={})
    assert (again.status_code, again.json()["detail"]) == (409, "This series is already adding items.")
    assert worker.work_once(db)
    db.expire_all()
    job = db.get(models.Job, queued.json()["id"])
    assert (job.status, job.done_pages, job.total_pages) == ("done", 6, 30)  # both pages of 3 gone through, of the 30 listed
    assert db.query(models.ArchiveItem).filter_by(collection_id=2).count() == 0  # listed, no scans, Reading Room only
    browses = [r for r in diaries.requests if r.startswith("/nodes/browse?")]
    assert len(browses) == 2 and all("keywords=diary" in r for r in browses)
    diaries.add_listing(524173, [(637679, "Diary 1887", "UMA-IT-000147347", True), (637680, "Diary 1888", "UMA-IT-000147348", True)])
    client.post("/collections/2/items/all", json={})
    assert worker.work_once(db)
    db.expire_all()
    assert {(i.node, i.title, i.pdf) for i in db.query(models.ArchiveItem).filter_by(collection_id=2)} == {
        (637679, "Diary 1887", "637679/637679.pdf"), (637680, "Diary 1888", "637680/637680.pdf")}


def test_a_list_too_long_for_the_archive_to_show_is_added_a_box_at_a_time(client, db, archive, monkeypatch):
    monkeypatch.setattr(worker, "PAUSE", 0)
    db.add(models.Collection(collection_id=3, name="Cards", archive_series=71317, archive_identifier="UMA-SRE-20160049",
                             archive_items=60772))
    db.commit()
    archive.add_series(71317, "[UMA-SRE-20160049] Cards", "Identifier: UMA-SRE-20160049", "60,772", units=2)
    archive.add_listing(71317, [(1, "Not read", "UMA-ITE-1", True)], pages=417, count=10000)  # all the archive shows of it
    archive.add_listing("units:71317", [(177811, "2016.0049 Unit 0001", "", False), (177812, "2016.0049 Unit 0002", "", False)])
    archive.add_unit(177811, 1)
    archive.add_unit(177812, 2)
    archive.add_listing("unit:177811", [(368478, "Anderson, Mr William S, 4328", "UMA-ITE-2016004900808", True)])
    archive.add_listing("unit:177812", [(428369, "Taylor, W R, A12524", "UMA-ITE-2", True, "Access restrictions apply"),
                                        (380835, "Davis, V", "UMA-ITE-3", True)])
    client.post("/collections/3/items/all", json={})
    assert worker.work_once(db)
    db.expire_all()
    assert {i.node for i in db.query(models.ArchiveItem).filter_by(collection_id=3)} == {368478, 380835}
    job = db.query(models.Job).one()
    assert (job.status, job.done_pages, job.total_pages) == ("done", 3, 60772)
    assert len([r for r in archive.requests if r.startswith("/nodes/browse?bid=71317&")]) == 1  # not its 417 pages


def test_adding_a_list_from_an_archive_that_cant_be_reached_fails_the_task_with_the_reason(client, db, monkeypatch):
    monkeypatch.setattr(worker, "PAUSE", 0)
    db.add(models.Collection(collection_id=2, name="Diaries", archive_series=524173, archive_identifier="UMA-SR-000001769"))
    db.commit()
    client.post("/collections/2/items/all", json={})
    assert worker.work_once(db)  # the tests never reach the internet
    db.expire_all()
    job = db.query(models.Job).one()
    assert job.status == "failed" and "the tests don't reach the archive" in job.error


def test_tasks_say_what_each_job_is_how_far_it_has_got_and_where_to_see_it(client, db, diaries):
    db.add_all([models.ArchiveItem(node=216412, collection_id=1, identifier="UMA-ITE-1973000200001", title="Box Hill 00"),
                models.Job(kind="train", status="done"),
                models.Job(kind="bundle", pdf="data/216412/423444_x.pdf", status="failed", error="the archive broke off"),
                models.Job(kind="items", collection_id=2, search="diary", status="running", done_pages=24, total_pages=30)])
    db.commit()
    tasks = client.get("/jobs").json()
    assert [(t["label"], t["status"], t["done"], t["total"], t["unit"], t["href"], t["error"]) for t in tasks] == [
        ('Adding items to Diaries matching "diary"', "running", 24, 30, "items", "/?collection=2", None),
        ("Transcribing Box Hill 00", "failed", 0, 0, "pages", "/?collection=1&bundle=216412", "the archive broke off"),
        ("Training page sorting", "done", 0, 0, "pages", None, None)]
    assert [(t["collectionId"], t["series"]) for t in tasks] == [(2, "Diaries"), (1, "Wilfred Prest Survey"), (None, None)]


def test_a_run_saves_the_series_it_is_loaded_into(tmp_path):
    from backend.pipeline import run as pipeline
    pipeline.Run(tmp_path / "b.pdf", tmp_path / "out", collection=2).save()
    assert json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))["collection"] == 2


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
