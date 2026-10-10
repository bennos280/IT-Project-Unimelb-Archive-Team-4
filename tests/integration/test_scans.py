"""backend/scans.py reads the archive's real download page (saved from the website), and no test reaches the internet."""
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


def test_no_test_reaches_the_internet():
    with pytest.raises(OSError, match="the tests don't use the internet"):
        urllib.request.urlopen("https://archives.library.unimelb.edu.au/", timeout=5)
