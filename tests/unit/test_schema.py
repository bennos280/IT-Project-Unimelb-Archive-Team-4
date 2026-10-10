"""The rules in backend/db/models.py are enforced by the db: links between tables and the CHECK rules."""
import pytest
from sqlalchemy.exc import IntegrityError

from backend.db import models
from tests.unit.test_backend_api import add_in_order


def refused(db, row):
    db.add(row)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_row_must_belong_to_something_that_exists(db):
    refused(db, models.Survey(survey_id="s", bundle_id="no such bundle"))
    refused(db, models.ResidentField(page_id="p", resident_no=1, resident_field_title="age"))  # no such resident
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
                 models.OtherChild(page_id="p", residence="died", child_no=0))
    refused(db, models.Edit(page_id="p", edit_text="x", field_title="address", child_residence="died", child_no=0))  # two
    refused(db, models.Edit(page_id="p", edit_text="x", resident_field_title="age"))  # a resident's field, but whose
    refused(db, models.Edit(page_id="p", edit_text="x", child_no=0))  # a child, but on which list
