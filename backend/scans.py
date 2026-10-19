"""Page scans not on this computer, from the University of Melbourne Archives' website: for the API when a page's scan
isn't here, and for the pipeline when a bundle's PDF isn't."""
import html
import logging
import re
import shutil
import tempfile
import time
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from pathlib import Path
from urllib.request import HTTPCookieProcessor, build_opener

from backend.common import ROOT, settings

ARCHIVE = "https://archives.library.unimelb.edu.au"
AGENT = "prest-survey-pipeline (University of Melbourne COMP30022 Team 4, 2026 Semester 2)"  #the archive refuses curl's default name
#each bundle's PDF on the archive, as <bundle number>/<file id>_<file name>
ARCHIVE_PDFS = (Path(__file__).parent / "archive_pdfs.txt").read_text(encoding="utf-8").split()
ARCHIVE_ERRORS = (OSError, HTTPException)  #the archive can't be reached, or broke off
log = logging.getLogger("scans")
RETRY = 300  #seconds before asking the archive again for a bundle's pages after it couldn't send one
failed = {}  #bundle number -> when the archive last couldn't send one of its pages


#a session that has opened a bundle's download page, which lets it download the bundle's files; page number -> file id
def archive_bundle(bundle):
    if not bundle.isdigit():
        raise OSError(f"{bundle} isn't an archive item number")
    session = build_opener(HTTPCookieProcessor())
    session.addheaders = [("User-Agent", AGENT)]
    with session.open(f"{ARCHIVE}/nodes/download/{bundle}", timeout=30) as response:
        page = response.read().decode("utf-8", "replace")
    return session, {int(no): file_id for file_id, no in re.findall(r'value="/assets/downloadwiz/(\d+)">[^<]*\.(\d+)</option>', page)}


#one of the archive's files, saved to path whole or not at all
def archive_download(session, file_id, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as folder:
        part = Path(folder) / "part"  #not *.pdf, so a stopped download is never listed as a bundle
        with session.open(f"{ARCHIVE}/assets/downloadwiz/{file_id}", timeout=30) as response, open(part, "wb") as file:
            if response.headers.get_content_type() == "text/html":
                raise OSError(f"the archive sent a web page instead of file {file_id}")
            shutil.copyfileobj(response, file)
            size = response.headers.get("Content-Length")
            if size and file.tell() != int(size):
                raise OSError(f"the archive broke off file {file_id} at {file.tell():,} of {int(size):,} bytes")
        part.replace(path)


#a bundle's original PDF from the archive, saved as pdf: <bundle number>/<file id>_<file name>.pdf, or <number>/<number>.pdf
#for an item added from a series' list, whose newest original is looked up first
def fetch_pdf(pdf):
    number = pdf.parent.name
    file_id = pdf.name.split("_", 1)[0] if "_" in pdf.name else archive_original(number)
    if not file_id:
        raise OSError(f"the archive has no PDF of item {number}")
    session, _ = archive_bundle(number)
    archive_download(session, file_id, pdf)


#a page's full scan from the archive, kept in OUTPUT/scans; None while the archive can't send it or hasn't the page
def archive_scan(bundle, page_no):
    jpeg = ROOT / settings()["OUTPUT"] / "scans" / bundle / f"{page_no:04d}.jpg"
    if not jpeg.is_file() and time.monotonic() - failed.get(bundle, -RETRY) >= RETRY:
        try:
            session, pages = archive_bundle(bundle)
            if page_no in pages:
                archive_download(session, pages[page_no], jpeg)
        except ARCHIVE_ERRORS as error:
            failed[bundle] = time.monotonic()
            log.warning("the archive couldn't send bundle %s page %s (%s: %s); asking again in %s s",
                        bundle, page_no, type(error).__name__, error, RETRY)
    return jpeg if jpeg.is_file() else None


def opener():
    session = build_opener()
    session.addheaders = [("User-Agent", AGENT)]
    return session


#a node's page on the archive (/nodes/view/<node>); None if it has none
def node_page(node):
    try:
        with opener().open(f"{ARCHIVE}/nodes/view/{node}", timeout=30) as response:
            return response.read(2_000_000).decode("utf-8", "replace")  #a series page is well under this
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


#a node page's og:title and the "Key: value" parts of its og:description; the archive escapes both twice (Registrar&amp;#039;s)
def page_record(page):
    def meta(name):
        found = re.search(rf'<meta property="og:{name}" content="([^"]*)"', page)
        return html.unescape(html.unescape(found.group(1))) if found else ""
    return meta("title"), dict(part.split(": ", 1) for part in meta("description").split(" | ") if ": " in part)


#a series' page on the archive: its title (without the "[identifier] " the archive starts it with), catalogue identifier, dates,
#access status and number of items; None if the archive has no such page
def archive_series(node):
    page = node_page(node)
    if page is None:
        return None
    title, details = page_record(page)
    identifier = details.get("Identifier", "")
    items = re.search(r"Items in this series \(([\d,]+)\)", page)
    return {"id": node, "title": re.sub(r"^\[[^\]]*\]\s*", "", title), "identifier": identifier,
            "date": details.get("Date", ""), "access": details.get("Access Status", ""),
            "items": int(items.group(1).replace(",", "")) if items else None, "url": f"{ARCHIVE}/nodes/view/{node}"}


#an item's page on the archive: its title, identifier and series ("[UMA-SR-...] <title>"); None if the archive has no such page
def archive_item(node):
    page = node_page(node)
    if page is None:
        return None
    title, details = page_record(page)
    return {"title": title, "identifier": details.get("Identifier", ""), "series": details.get("Series", "")}


#the address of a list on the archive, from the link a node's page names it by: a series' "Items in this series" or "Units in
#this series" (its boxes), a unit's "Items in this unit"; None if it has none
def listing_link(node, of="Items in this series"):
    view = node_page(node)
    link = view and re.search(rf'href="([^"]*/nodes/browse\?[^"]*)"[^>]*>{of}', view)
    return urljoin(ARCHIVE, html.unescape(link.group(1))) if link else None


#a page of a series' list (listing_link), 24 items in the order they were catalogued: node, title, identifier and whether it
#can be downloaded (it has scans, and isn't for the Reading Room only), with the number of pages and of items (the archive
#lists 10,000 at most); search: words in the items' records
def archive_listing(link, page=1, search=""):
    if not link:
        return {"items": [], "page": 1, "pages": 1, "total": 0}
    query = urlencode({"order": "asc", "orderby": "node_id", "page": page, **({"keywords": search} if search else {})})
    with opener().open(f"{link}&{query}", timeout=30) as response:
        listing = response.read(5_000_000).decode("utf-8", "replace")
    def text(markup):  #a search's matches are wrapped in highlighting spans
        return html.unescape(re.sub(r"<[^>]+>", "", markup)).strip()
    def field(block, label):  #a listed item's "<label>: <value>", up to its next field
        found = re.search(rf"{label}: </span>(.*?)(?=<span class=\"metadata\">|</div>|\n|$)", block, re.S)
        return text(found.group(1)) if found else ""
    items = []
    for block in listing.split('<div class="list_item">')[1:]:
        node = re.search(r'name="multiSelect\[\]" value="(\d+)"', block)
        title = re.search(r"<h4>(.*?)</h4>", block, re.S)
        if node:
            items.append({"node": int(node.group(1)), "title": text(title.group(1)) if title else "",
                          "identifier": field(block, "Identifier"),
                          "scanned": "/assets/nodeimg/" in block and "restrict" not in field(block, "Access Status").lower()})
    counts = re.search(r'pageCount: "(\d+)",\s*count: "(\d+)"', listing)
    return {"items": items, "page": page, "pages": max(int(counts.group(1)), 1) if counts else 1,
            "total": int(counts.group(2)) if counts else len(items)}


#the file id of an item's original PDF on the archive, the newest when it has two; None if it has none
def archive_original(node):
    with opener().open(f"{ARCHIVE}/nodes/download/{node}", timeout=30) as response:
        page = response.read().decode("utf-8", "replace")
    found = re.findall(r'/assets/downloadwiz/(\d+)"[^>]*class="downsize"><img[^>]*/><br />[^<]+?\.pdf<', page)
    return max(found, key=int) if found else None


#a page's scan: the picture this computer's pipeline made, else the archive's; None if neither
def page_scan(import_path, source_pdf, page_id):
    scan = ROOT / import_path
    if scan.is_file():
        return scan
    bundle = Path(source_pdf).parent.name  #the archive's bundle number
    page_no = int(page_id.rsplit("_", 1)[1])
    return archive_scan(bundle, page_no)

