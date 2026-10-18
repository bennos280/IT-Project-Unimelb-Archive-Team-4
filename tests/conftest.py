"""Shared by every test: nothing on the internet is reached, only this computer itself. The archive lists no bundles and
can't be reached, unless a test uses the `archive` fixture, a stand-in that serves the files the test gives it. Every
consistency check is switched on (checks.json only decides which ones the app shows)."""
import io
import socket
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor
from urllib.response import addinfourl

import pytest

from backend import scans
from backend.db import database
from backend.pipeline.validate import run_validation, validator


@pytest.fixture(autouse=True)
def every_check(monkeypatch):
    monkeypatch.setattr(run_validation, "load_checks", lambda path=None: dict.fromkeys(validator.CHECKS, True))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def unreachable(*args, **kwargs):
        raise URLError("the tests don't reach the archive")

    def this_computer_only(host, *args, **kwargs):
        if host not in (None, "localhost", "127.0.0.1", "::1"):
            raise socket.gaierror(f"the tests don't use the internet (looked up {host})")
        return lookup(host, *args, **kwargs)

    lookup = socket.getaddrinfo
    monkeypatch.setattr(scans, "build_opener", unreachable)
    monkeypatch.setattr(socket, "getaddrinfo", this_computer_only)
    monkeypatch.setattr(scans, "ARCHIVE_PDFS", [])
    monkeypatch.setattr(scans, "failed", {})


@pytest.fixture(autouse=True)
def no_real_db(monkeypatch):
    def refused(*args, **kwargs):
        raise RuntimeError("the tests don't open the real database: give the test a db (cli_db) or an explicit choice")

    monkeypatch.setattr(database, "SessionLocal", refused)


class FakeArchive:
    """Bundles' download pages and files by id. Like the archive, it answers only a session that gives a user agent, and
    sends a file only to one that keeps cookies and has opened a download page. A file id in cut_short breaks off halfway."""

    def __init__(self):
        self.pages, self.files, self.requests, self.cut_short, self.views = {}, {}, [], set(), {}

    def add_series(self, node, title, description, items):
        """A series' view page (/nodes/view/<node>), with the og: tags and the item count the real one has."""
        self.views[str(node)] = (f'<meta property="og:title" content="{title}" />'
                                 f'<meta property="og:description" content="{description}" />'
                                 f'<a href="/nodes/browse?bid={node}">Items in this series ({items})</a>')

    def add(self, bundle, pages, pdf=None):
        """A bundle's download page listing its pages ({page number: (file id, bytes)}) and its PDF ((file id, bytes))."""
        self.pages[bundle] = "".join(f'<option value="/assets/downloadwiz/{file_id}">x.pdf.{no:05d}</option>'
                                     for no, (file_id, _) in pages.items())
        self.files.update({file_id: data for file_id, data in [*pages.values(), *([pdf] if pdf else [])]})

    def __call__(self, *handlers):
        archive, opened = self, []
        cookies = any(isinstance(handler, HTTPCookieProcessor) for handler in handlers)

        class Session:
            addheaders = []

            def open(self, url, timeout):
                path = url.removeprefix(scans.ARCHIVE)
                archive.requests.append(path)
                kind, _, key = path.rpartition("/")
                if not any(name == "User-Agent" for name, _ in self.addheaders):
                    raise HTTPError(url, 403, "Forbidden", Message(), None)
                if kind == "/nodes/view" and key in archive.views:
                    return response(archive.views[key].encode(), "text/html")
                if kind == "/nodes/download" and key in archive.pages:
                    opened.append(key)
                    return response(archive.pages[key].encode(), "text/html")
                if kind == "/assets/downloadwiz" and cookies and opened and key in archive.files:
                    body = archive.files[key]
                    return response(body[:len(body) // 2] if key in archive.cut_short else body, "application/octet-stream", len(body))
                raise HTTPError(url, 404, "Not Found", Message(), None)

        return Session()


def response(body, content_type, size=None):
    headers = Message()
    headers["Content-Type"] = content_type
    headers["Content-Length"] = str(len(body) if size is None else size)
    return addinfourl(io.BytesIO(body), headers, "", 200)


@pytest.fixture
def archive(monkeypatch):
    fake = FakeArchive()
    monkeypatch.setattr(scans, "build_opener", fake)
    return fake
