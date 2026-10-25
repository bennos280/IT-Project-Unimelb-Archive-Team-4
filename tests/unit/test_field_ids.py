"""The review screen's ids for values read off a page (backend/db/field_ids.py): the ids the review screen, saved edits and
exports already use come back out of their parts, and each id parses back into them."""
import pytest

from backend.db import field_ids


@pytest.mark.parametrize("parts, field_id", [
    (("", 0, "address"), "address"),
    (("", 0, "rooms.number_of_living_rooms"), "rooms.number_of_living_rooms"),
    (("residents", 0, "age"), "residents.0.age"),
    (("residents", 12, "pre_war_occupation"), "residents.12.pre_war_occupation"),
    (("other_children.died", 0, ""), "other_children.died.0"),
    (("other_children.living_elsewhere", 3, ""), "other_children.living_elsewhere.3"),
])
def test_an_id_is_built_from_its_parts_and_parses_back_into_them(parts, field_id):
    assert field_ids.field_id(*parts) == field_id
    assert field_ids.parse(field_id) == parts
    assert field_ids.annotation_no(field_id) is None


def test_an_annotation_id_is_its_number():
    assert field_ids.annotation_id(4) == "annotations.4"
    assert field_ids.annotation_no("annotations.4") == 4


@pytest.mark.parametrize("field_id", ["annotations.١", "residents.x.age", "residents.١.age", "annotations"])
def test_an_id_without_an_ascii_item_number_is_a_field_outside_a_list(field_id):
    assert field_ids.annotation_no(field_id) is None
    assert field_ids.parse(field_id) == ("", 0, field_id)
