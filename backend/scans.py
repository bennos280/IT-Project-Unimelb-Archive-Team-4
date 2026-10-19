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


#a bundle's original PDF from the archive, saved as pdf: <bundle number>/<file id>_<file name>.pdf
def fetch_pdf(pdf):
    session, _ = archive_bundle(pdf.parent.name)
    archive_download(session, pdf.name.split("_", 1)[0], pdf)


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


#a series' page on the archive (/nodes/view/<node>, which robots.txt allows): its title (without the "[identifier] " the archive
#starts it with), catalogue identifier, dates, access status and number of items; None if the archive has no such page
def archive_series(node):
    session = build_opener()
    session.addheaders = [("User-Agent", AGENT)]
    try:
        with session.open(f"{ARCHIVE}/nodes/view/{node}", timeout=30) as response:
            page = response.read(2_000_000).decode("utf-8", "replace")  #a series page is well under this
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    def meta(name):  #the archive escapes these twice: Registrar&amp;#039;s
        found = re.search(rf'<meta property="og:{name}" content="([^"]*)"', page)
        return html.unescape(html.unescape(found.group(1))) if found else ""
    details = dict(part.split(": ", 1) for part in meta("description").split(" | ") if ": " in part)
    items = re.search(r"Items in this series \(([\d,]+)\)", page)
    return {"id": node, "title": re.sub(r"^\[[^\]]*\]\s*", "", meta("title")), "identifier": details.get("Identifier", ""), "date": details.get("Date", ""),
            "access": details.get("Access Status", ""), "items": int(items.group(1).replace(",", "")) if items else None,
            "url": f"{ARCHIVE}/nodes/view/{node}"}


#a page's scan: the picture this computer's pipeline made, else the archive's; None if neither
def page_scan(import_path, source_pdf, page_id):
    scan = ROOT / import_path
    if scan.is_file():
        return scan
    bundle = Path(source_pdf).parent.name  #the archive's bundle number
    page_no = int(page_id.rsplit("_", 1)[1])
    return archive_scan(bundle, page_no)

