import pytest
"""The named areas of a card (backend/pipeline/transcribe/areas.json): the file is sound, the prompt lists exactly its
names, and the API gives an annotation's area and its box."""
import json
import re

from backend.db import models
from backend.pipeline.transcribe import areas
from backend.pipeline.transcribe.transcribe import read_texts, schema_for
from tests.unit.test_backend_api import add_in_order

PAGE_TYPES = ("main", "coded")


def test_every_area_is_a_unique_name_with_a_label_and_a_box_inside_the_card():
    assert set(areas.AREAS) == set(PAGE_TYPES)
    for page_type in PAGE_TYPES:
        names = areas.names(page_type)
        assert names and len(names) == len(set(names)) and all(re.fullmatch(r"[a-z]+(_[a-z]+)*", name) for name in names)
        for name in names:
            box = areas.AREAS[page_type][name]
            assert box["label"].strip() and set(box) == {"label", "x", "y", "width", "height", "fields"}, name
            assert all(isinstance(f, str) and f.strip() for f in box["fields"]) and len(box["fields"]) == len(set(box["fields"])), name
            assert 0 <= box["x"] and 0 <= box["y"] and box["width"] > 0 and box["height"] > 0, name
            assert box["x"] + box["width"] <= 1 and box["y"] + box["height"] <= 1, name


def test_a_page_type_without_areas_has_no_names_or_boxes():
    assert areas.names("notes") == [] and areas.box("notes", "header") is None and areas.box("main", "nowhere") is None
    assert areas.box("main", None) is None


def test_the_prompt_lists_exactly_the_names_for_each_page_type():
    prompt = read_texts()["prompt"].replace("\r\n", "\n")
    for page_type, heading in (("main", "Annotation areas, main form:"), ("coded", "Annotation areas, coded card:")):
        listed = prompt.split(heading, 1)[1].split("\n\n", 1)[0]
        listed = re.sub(r"\([^)]*\)", "", listed)  # the hints in brackets
        assert [name.strip(" .") for name in listed.split(",")] == areas.names(page_type)


def annotated_survey(db, category, *annotations):
    add_in_order(db, models.Survey(survey_id="12345", bundle_id="6789"),
                 models.Page(page_id="p", survey_id="12345", category=category, import_path="p.png", bundle_id="6789"),
                 *[models.Annotation(page_id="p", annotation_no=no, text_raw="*", location="somewhere", area=area)
                   for no, area in enumerate(annotations)])
    db.commit()


def test_an_annotation_with_an_area_comes_with_its_box_and_one_without_has_none(client, db):
    annotated_survey(db, "main", "kitchen_block", None, "top_left_corner")
    with_area, without, other = client.get("/survey/12345").json()["pages"][0]["fields"]
    assert with_area["area"] == "kitchen_block" and with_area["areaLabel"] == "Kitchen"
    # an area is shown 0.03 bigger on every side, kept on the page
    assert with_area["sourceRegion"] == pytest.approx({"x": 0.75, "y": 0.47, "width": 0.25, "height": 0.53})
    assert without["area"] is None and "sourceRegion" not in without and "areaLabel" not in without
    assert other["sourceRegion"] == pytest.approx({"x": 0, "y": 0, "width": 0.28, "height": 0.15})


def test_an_area_the_page_type_does_not_have_gives_no_box(client, db):
    annotated_survey(db, "coded", "kitchen_block")  # a main form's area on a coded card (the page was moved)
    field = client.get("/survey/12345").json()["pages"][0]["fields"][0]
    assert field["area"] == "kitchen_block" and "sourceRegion" not in field


def test_the_transcription_schema_asks_for_an_area_on_every_annotation():
    for page_type in ("main", "coded", "notes"):
        item = schema_for(json.loads(read_texts()[page_type]))["properties"]["annotations"]["items"]
        assert item["required"] == ["raw", "location", "area"] and item["properties"]["area"] == {"type": ["string", "null"]}


def test_an_annotations_own_region_is_its_box_and_an_area_without_one_gives_the_areas_box(client, db):
    add_in_order(db, models.Survey(survey_id="12345", bundle_id="6789"),
                 models.Page(page_id="p", survey_id="12345", category="main", import_path="p.png", bundle_id="6789"),
                 models.Annotation(page_id="p", annotation_no=0, text_raw="*", location="residential pref row", area="residents_table",
                                   region='{"x": 0.04, "y": 0.67, "width": 0.57, "height": 0.028}'),
                 models.Annotation(page_id="p", annotation_no=1, text_raw="*", location="column 2", area="residents_table"))
    db.commit()
    row, whole = client.get("/survey/12345").json()["pages"][0]["fields"]
    # a row or cell is shown 0.015 bigger on every side
    assert row["sourceRegion"] == pytest.approx({"x": 0.025, "y": 0.655, "width": 0.6, "height": 0.058}) and row["areaLabel"] == "Residents table"
    assert whole["sourceRegion"] == pytest.approx({"x": 0.14, "y": 0.26, "width": 0.5, "height": 0.74})
