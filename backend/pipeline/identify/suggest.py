"""Page types suggested for a series from some of an item's pages: the pages drawn on one numbered contact sheet, and the
reading model asked once what kinds of page it shows (the Suggest page types button in a series' Setup)."""
import math
import random
import re
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from backend.pipeline.transcribe.transcribe import ask

TILE = 400  # pixels wide per page on the sheet: enough to tell a form from a letter, small enough for one image
TALLEST = TILE * 3 // 2  # a longer page is shrunk to this height
MOST = 30
TEMPLATE = {"page_types": [{
    "name": "a short name for this kind of page, like Membership form, Letter or Blank back",
    "description": "one line on what this kind of page is and how to tell it from the others",
    "tiles": "the numbers of the tiles that are this kind of page, like 1, 4, 9",
}]}


def pick(total, count, how="spread", first=None, last=None, seed=None):
    """Which of an item's pages (numbered from 1) to look at: count of them, spread evenly, at random, or spread over the
    range first..last; all of them when there are no more than count."""
    low, high = (max(1, first or 1), min(total, last or total)) if how == "range" else (1, total)
    pages = list(range(low, high + 1))
    count = max(1, min(count, MOST))
    if len(pages) <= count:
        return pages
    if how == "random":
        return sorted(random.Random(seed).sample(pages, count))
    step = len(pages) / count
    return [pages[int(i * step)] for i in range(count)]


def contact_sheet(pdf, pages, out):
    """pages of pdf side by side, each with its tile number (1, 2, ...) in its corner, saved to out as a JPEG."""
    import pymupdf
    tiles = []
    with pymupdf.open(pdf) as doc:
        for n in pages:
            page = doc[n - 1]
            zoom = TILE / page.rect.width
            drawn = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            tile = Image.frombytes("RGB", (drawn.width, drawn.height), drawn.samples)
            tile.thumbnail((TILE, TALLEST))
            tiles.append(tile)
    gap, columns = 16, math.ceil(math.sqrt(len(tiles)))
    rows = [tiles[i:i + columns] for i in range(0, len(tiles), columns)]
    heights = [max(t.height for t in row) for row in rows]  # each row as tall as its tallest page
    sheet = Image.new("RGB", (columns * (TILE + gap) + gap, sum(heights) + gap * (len(rows) + 1)), "#888888")
    draw, font = ImageDraw.Draw(sheet), ImageFont.load_default(size=40)
    y = gap
    for r, row in enumerate(rows):
        for c, tile in enumerate(row):
            x = gap + c * (TILE + gap)
            sheet.paste(tile, (x, y))
            draw.rectangle((x, y, x + 64, y + 52), fill="black")
            draw.text((x + 10, y + 4), str(r * columns + c + 1), fill="white", font=font)
        y += heights[r] + gap
    sheet.save(out, "JPEG", quality=85)


def prompt_for(count, known, hint):
    return (f"These are {count} pages of one item from an archive, each on a numbered tile. Say what distinct kinds of page "
            "they show, so that every page can be sorted into one kind: forms, letters, covers, blank backs and so on. Give "
            "each kind once, with the tiles that are that kind; every tile belongs to one kind. Use as few kinds as tell the "
            "pages apart." + (f" The series already has these page types; use the same name for a page that is one of them: "
                              f"{', '.join(known)}." if known else "") + (f"\n\nFrom the person asking: {hint}" if hint else ""))


def suggest(pdf, pages, choice, known=(), hint=""):
    """[{"label", "description", "pages"}]: the kinds of page the reading model sees in pages of pdf, each with the page
    numbers it said are that kind. choice: {"provider", "model", "effort"}; a failed request raises (SystemExit)."""
    with tempfile.TemporaryDirectory() as folder:
        sheet = Path(folder) / "pages.jpg"
        contact_sheet(pdf, pages, sheet)
        answer = ask(sheet, prompt_for(len(pages), list(known), hint.strip()), TEMPLATE, fresh=True, **choice)  #asked again, not a saved answer
    found = []
    for kind in answer.get("page_types") or []:
        label = " ".join(str(kind.get("name") or "").split())[:60]
        tiles = {int(t) for t in re.findall(r"\d+", str(kind.get("tiles") or "")) if 1 <= int(t) <= len(pages)}
        if label and label.lower() not in {f["label"].lower() for f in found}:
            found.append({"label": label, "description": " ".join(str(kind.get("description") or "").split())[:300],
                          "pages": [pages[t - 1] for t in sorted(tiles)]})
    return found
