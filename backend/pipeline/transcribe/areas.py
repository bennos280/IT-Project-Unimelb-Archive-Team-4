"""The named parts of a card (areas.json: boxes as fractions of the page image) that an annotation is placed in."""
import json
from pathlib import Path

AREAS = json.loads((Path(__file__).resolve().parent / "areas.json").read_text(encoding="utf-8"))


#the area names for a page type; none for a type without areas
def names(page_type):
    return list(AREAS.get(page_type, {}))


#an area's box {x, y, width, height}; None if the page type has no such area
def box(page_type, name):
    area = AREAS.get(page_type, {}).get(name)
    return area and {key: area[key] for key in ("x", "y", "width", "height")}


#a box grown on every side and kept on the page, so a mark at its edge still falls inside
def padded(box, pad):
    x0, y0 = max(0, box["x"] - pad), max(0, box["y"] - pad)
    x1, y1 = min(1, box["x"] + box["width"] + pad), min(1, box["y"] + box["height"] + pad)
    return {"x": round(x0, 4), "y": round(y0, 4), "width": round(x1 - x0, 4), "height": round(y1 - y0, 4)}


#the box the review screen highlights for an annotation: its row/cell region (JSON text) grown by 0.015, else its area grown by 0.03
def shown(page_type, name, region):
    if region:
        return padded(json.loads(region), 0.015)
    area = name and box(page_type, name)
    return area and padded(area, 0.03)


def label(page_type, name):
    return AREAS.get(page_type, {}).get(name, {}).get("label")


#an area's printed field labels (areas.json "fields")
def fields(page_type, name):
    return AREAS.get(page_type, {}).get(name, {}).get("fields", [])
