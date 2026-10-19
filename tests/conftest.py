"""Shared by every test: nothing on the internet is reached, only this computer itself. The archive lists no bundles and
can't be reached, unless a test uses the `archive` fixture, a stand-in that serves the files the test gives it."""
import html
import io
import socket
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPCookieProcessor
from urllib.response import addinfourl

import pytest

from backend import scans
from backend.db import database
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
        self.pages, self.files, self.requests, self.cut_short, self.views, self.listings = {}, {}, [], set(), {}, {}

    def add_series(self, node, title, description, items, units=None):
        """A series' view page (/nodes/view/<node>), with the og: tags and the item count the real one has, and when given the
        count of its units (boxes); its lists are add_listing(node) and add_listing(f"units:{node}")."""
        self.views[str(node)] = (f'<meta property="og:title" content="{title}" />'
                                 f'<meta property="og:description" content="{description}" />'
                                 f'<a href="/nodes/browse?bid={node}">Items in this series ({items})</a>'
                                 + (f'<a href="/nodes/browse?filter=units&bid={node}">Units in this series ({units})</a>' if units else ""))

    def add_unit(self, node, items):
        """A unit's (box's) view page, linking to its list of items, add_listing(f"unit:{node}")."""
        self.views[str(node)] = f'<a href="/nodes/browse?filter=unit&bid={node}">Items in this unit ({items})</a>'

    def add_listing(self, series, items, pages=1, count=None):
        """A series' items page (/nodes/browse?...&bid=<series>) as the real one marks them up: (node, title, identifier,
        whether it has scans, and optionally its access status); the series' view page (add_series) links to it."""
        self.listings[str(series)] = "".join(
            f'<div class="list_item"><input type="checkbox" name="multiSelect[]" value="{node}" />'
            f'<img src="{f"/assets/nodeimg/{node}/a.jpg" if scanned else "/theme/uma/img/placeholder.png"}" />'
            f'<h4>{html.escape(title)}</h4>\n<span class="metadata"><span class="titlelabel">Identifier: </span>{identifier}</span>\n'
            f'<span class="metadata"><span class="titlelabel">Access Status: </span>{access[0] if access else "Open for public access"}'
            '</span>\n</div>'
            for node, title, identifier, scanned, *access in items
        ) + f'<script>var bntBlock = {{pageCount: "{pages}", count: "{len(items) if count is None else count}"}};</script>'

    def add_item(self, node, title, identifier, series, originals):
        """An item's view page (og: tags naming its series) and download page offering its original PDFs ((file id, name))."""
        self.views[str(node)] = (f'<meta property="og:title" content="{html.escape(title)}" />'
                                 f'<meta property="og:description" content="Identifier: {identifier} | Series: {series} | '
                                 f'Access Status: Open for public access" />')
        self.pages[str(node)] = "".join(f'<a href="https://archives.library.unimelb.edu.au/assets/downloadwiz/{file_id}" '
                                        f'class="downsize"><img src="/img/file_pdf.png" /><br />{name}<span class="tinytim">'
                                        f'<br />1 MB</span></a>' for file_id, name in originals)

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
                if path.startswith("/nodes/browse?"):  #a list: by its filter and node, else by its node
                    query = parse_qs(urlparse(path).query)
                    listing = archive.listings.get(f"{query.get('filter', [''])[0]}:{query['bid'][0]}", archive.listings.get(query["bid"][0], ""))
                    return response(listing.encode(), "text/html")
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
