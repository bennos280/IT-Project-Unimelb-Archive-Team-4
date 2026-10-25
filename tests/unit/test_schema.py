"""The rules in backend/db/models.py are enforced by the db: links between tables and the CHECK rules."""
import pytest
from sqlalchemy.exc import IntegrityError

from backend.db import loader, models
from tests.unit.test_backend_api import add_in_order


def refused(db, row):
    db.add(row)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_row_must_belong_to_something_that_exists(db):
    refused(db, models.Survey(survey_id="s", bundle_id="no such bundle"))
    refused(db, models.Field(page_id="p", list_name="residents", item_no=1, field_title="age"))  # no such page
    refused(db, models.Flag(page_id="p", field_title="address", kind="uncertain", reason="?"))  # no such field


def test_a_job_status_is_waiting_running_done_or_failed(db):
    refused(db, models.Job(pdf="a.pdf", status="banana"))


def test_a_page_has_one_of_the_page_types(db):
    add_in_order(db)
    refused(db, models.Page(page_id="p", import_path="p.png", bundle_id="6789", category="banana"))


def test_a_flag_is_an_inconsistency_gibberish_or_uncertain(db):
    add_in_order(db, models.Page(page_id="p", import_path="p.png", bundle_id="6789", category="main"),
                 models.Field(page_id="p", field_title="address"))
    refused(db, models.Flag(page_id="p", field_title="address", kind="banana", reason="?"))


def test_an_edit_fixes_exactly_one_thing(db):
    refused(db, models.Edit(page_id="p", edit_text="x"))  # nothing
    add_in_order(db, models.Page(page_id="p", import_path="p.png", bundle_id="6789", category="main"),
                 models.Field(page_id="p", field_title="address"),
                 models.Field(page_id="p", list_name="other_children.died", item_no=0, field_title=""),
                 models.Annotation(page_id="p", annotation_no=0))
    refused(db, models.Edit(page_id="p", edit_text="x", field_title="address", annotation_no=0))  # two
    refused(db, models.Edit(page_id="p", edit_text="x", list_name="other_children.died", annotation_no=0))  # an annotation in a list
    refused(db, models.Edit(page_id="p", edit_text="x", list_name="residents", item_no=0, field_title="age"))  # no such value


def test_reading_a_page_again_drops_the_edits_and_flags_on_its_values(db):
    add_in_order(db, models.Page(page_id="p", import_path="p.png", bundle_id="6789", category="main"),
                 models.Field(page_id="p", field_title="address"),
                 models.Field(page_id="p", list_name="residents", item_no=0, field_title="age"),
                 models.Field(page_id="p", list_name="other_children.died", item_no=0, field_title=""),
                 models.Edit(page_id="p", edit_text="x", field_title="address"),
                 models.Edit(page_id="p", edit_text="44", list_name="residents", item_no=0, field_title="age"),
                 models.Edit(page_id="p", edit_text="girl 3", list_name="other_children.died", item_no=0, field_title=""),
                 models.Flag(page_id="p", list_name="residents", item_no=0, field_title="age", kind="check", reason="?"))
    db.commit()
    loader.clear_content("p", db.connection())
    db.commit()
    assert (db.query(models.Field).count(), db.query(models.Edit).count(), db.query(models.Flag).count()) == (0, 0, 0)
