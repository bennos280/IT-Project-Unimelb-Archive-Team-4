"""Rewrites the "fields" lists of areas.json (printed labels per area) from the review screen's field boxes: python -m backend.pipeline.transcribe.area_fields"""
import json
import re
from pathlib import Path

from . import area_rules, areas

ROOT = Path(__file__).resolve().parents[3]
LOCATIONS = ROOT / "frontend" / "src" / "review-screen" / "fieldLocations.ts"
DATA_DICT = ROOT / "backend" / "db" / "data_dict.json"
AREAS_JSON = Path(__file__).with_name("areas.json")
PAGES = {"main": "1", "coded": "3"}
BOX = re.compile(r'(?:"([^"]+)"|(\w+)):\s*\{\s*x:\s*([\d.]+),\s*y:\s*([\d.]+),\s*width:\s*([\d.]+),\s*height:\s*([\d.]+)')
#boxes whose centre is in no area, or in a neighbour: the area they belong to
OVERRIDES = {("main", "signature_of_investigator"): "top_right_corner",  #the top-right header block, centre just under it
             ("coded", "length_of_residence"): "right_column"}  #a right column field, centre in the corner above it
#printed names the data dictionary does not have
EXTRA = {("main", "number_of_dwelling"): ["Dwelling No."],
         ("main", "archive_reference"): ["Archive Reference"],
         ("main", "industry_of_head_code"): ["Industry code", "Industry of Head code"],
         ("main", "occupation_of_head_code"): ["Occupation code", "Occupation of Head code"],
         ("coded", "washouse"): ["Washhouse"],  #as it is printed on the card
         ("coded", "children_of_head_or_wife_living"): ["Children of H. or Wife", "Children Living", "Living"],
         ("coded", "children_of_head_or_wife_dead"): ["Children Dead", "Dead"],
         ("coded", "children_of_head_or_wife_total"): ["Children Total"]}


def boxes(page_type):
    """{field id: (centre x, centre y)} of a page type in fieldLocations.ts."""
    text = re.sub(r"//.*", "", LOCATIONS.read_text(encoding="utf-8"))
    section = re.search(rf"\n  {page_type}: \{{(.*?)\n  \}},", text, re.S).group(1)
    return {a or b: (float(x) + float(w) / 2, float(y) + float(h) / 2) for a, b, x, y, w, h in BOX.findall(section)}


def area_of(page_type, field_id, centre):
    if (page_type, field_id) in OVERRIDES: return OVERRIDES[page_type, field_id]
    x, y = centre
    return next(name for name in areas.names(page_type)
                if (b := areas.box(page_type, name)) and b["x"] <= x < b["x"] + b["width"] and b["y"] <= y < b["y"] + b["height"])


def printed(page_type, field_id):
    """The field's printed label, as the data dictionary has it (the id in words if it has none)."""
    fields = json.loads(DATA_DICT.read_text(encoding="utf-8"))["pages"][PAGES[page_type]]["fields"]
    key = re.sub(r"\.\d+", "", field_id)  #residents.0.age is residents.age
    return fields.get(key, {}).get("label_text") or key.replace("_", " ").replace(".", " ")


def variants(label):
    """The label, then shorter ways it is written: without the brackets, without "Approx.", without the "Kitchen:" part."""
    plain = re.sub(r"\s*\([^)]*\)", "", label).strip()
    short = re.sub(r"^Approx\. ", "", plain)
    return [label, plain, short, *([short.split(": ", 1)[1]] if ": " in short else [])]


def generate():
    result = {}
    for page_type in PAGES:
        by_field = {}
        for field_id, centre in boxes(page_type).items():
            key = re.sub(r"\.\d+", "", field_id)
            by_field.setdefault(key, (area_of(page_type, field_id, centre), [printed(page_type, field_id), *EXTRA.get((page_type, key), [])]))
        owners = {}  #normalised label -> the areas that use it
        for area, labels in by_field.values():
            for label in labels:
                for variant in variants(label):
                    owners.setdefault(area_rules.norm(variant), set()).add(area)
        assert all(owners[area_rules.norm(labels[0])] == {area} for area, labels in by_field.values()), "a printed label in two areas"
        result[page_type] = {name: [] for name in areas.names(page_type)}
        for area, labels in by_field.values():
            for label in labels:
                for variant in variants(label):
                    words = area_rules.norm(variant)
                    keep = variant == label or (len(words.split()) > 1 and owners[words] == {area})
                    if keep and words not in {area_rules.norm(v) for v in result[page_type][area]}:
                        result[page_type][area].append(variant)
    return result


def write(result):
    lines = []
    for page_type in PAGES:
        rows = []
        for name in areas.names(page_type):
            box = {key: areas.AREAS[page_type][name][key] for key in ("label", "x", "y", "width", "height")}
            head = ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in box.items())
            rows.append(f'  "{name}": {{{head},\n   "fields": {json.dumps(result[page_type][name], ensure_ascii=False)}}}')
        lines.append(f' "{page_type}": {{\n' + ",\n".join(rows) + "\n }")
    AREAS_JSON.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write(generate())
