"""backend/scans.py reads the archive's real download page (saved from the website), and no test reaches the internet."""
import logging
import urllib.request
from pathlib import Path

import pytest

from backend import scans

PAGE = Path(__file__).parent / "archive" / "download_216412.html"  # Box Hill 00's download page, as the archive sent it


def test_the_archives_real_download_page_gives_every_page_its_file(archive):
    archive.pages["216412"] = PAGE.read_text(encoding="utf-8")
    _, pages = scans.archive_bundle("216412")
    assert list(pages) == list(range(1, 228))  # all 227 pages, in order
    assert (pages[1], pages[2], pages[227]) == ("423448", "423450", "425881")


ARCHIVE_PAGES = Path(__file__).parent / "archive"  # pages as the archive sent them, saved 19 Oct 2026


def saved(name):
    return (ARCHIVE_PAGES / name).read_text(encoding="utf-8")


def test_a_series_real_list_of_items_is_read_with_which_can_be_downloaded(archive):
    archive.views["524173"] = saved("view_524173.html")  # the Strathfieldsaye Estate Diaries
    archive.listings["524173"] = saved("browse_524173.html")
    link = scans.listing_link(524173)
    assert link.startswith("https://archives.library.unimelb.edu.au/nodes/browse?filter=") and link.endswith("&bid=524173")
    listing = scans.archive_listing(link)
    assert (listing["pages"], listing["total"], len(listing["items"])) == (1, 18, 18)
    assert listing["items"][0] == {"node": 637664, "title": "Strathfieldsaye Estate Diary 1904-1909",
                                   "identifier": "UMA-IT-000147332", "scanned": True}
    assert [i["node"] for i in listing["items"] if not i["scanned"]] == [637676]  # nothing to download


def test_a_real_search_result_keeps_the_fields_its_matches_are_highlighted_in(archive):
    archive.listings["524173"] = saved("browse_524173_search.html")  # keywords=000147343
    [item] = scans.archive_listing("https://archives.library.unimelb.edu.au/nodes/browse?filter=x&bid=524173", 1, "000147343")["items"]
    assert (item["node"], item["identifier"], item["scanned"]) == (637675, "UMA-IT-000147343", True)


def test_a_real_reading_room_card_is_listed_as_not_downloadable(archive):
    archive.listings["71317"] = saved("browse_71317_search.html")  # keywords=A12524
    items = scans.archive_listing("https://archives.library.unimelb.edu.au/nodes/browse?filter=x&bid=71317", 1, "A12524")["items"]
    assert {i["node"]: i["scanned"] for i in items}[428369] is False


def test_a_real_items_page_names_its_series_and_its_download_page_its_original_pdf(archive):
    archive.views["368478"] = saved("view_368478.html")
    archive.pages["637675"] = saved("download_637675.html")
    assert scans.archive_item(368478) == {"title": "Anderson, Mr William S, 4328", "identifier": "UMA-ITE-2016004900808",
                                          "series": "[UMA-SRE-20160049] Missing, Wounded and Prisoner Of War Cards"}
    assert scans.archive_original(637675) == "1369539"


def test_no_test_reaches_the_internet():
    with pytest.raises(OSError, match="the tests don't use the internet"):
        urllib.request.urlopen("https://archives.library.unimelb.edu.au/", timeout=5)


def test_a_scan_the_archive_cant_send_is_logged_with_the_reason(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(scans, "settings", lambda: {"OUTPUT": str(tmp_path)})
    with caplog.at_level(logging.WARNING, logger="scans"):
        assert scans.archive_scan("216412", 1) is None  # the tests' archive can't be reached
    assert [r.getMessage() for r in caplog.records] == [
        "the archive couldn't send bundle 216412 page 1 (URLError: <urlopen error the tests don't reach the archive>); asking again in 300 s"]
