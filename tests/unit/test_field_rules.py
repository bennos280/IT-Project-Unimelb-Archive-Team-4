"""A page type's field rules (backend/db/checks.py): saved with its template version, and a page's values that break them
flagged for review (kind invalid) when its item is loaded or it is read again."""
import json
import sqlite3

import pytest

from backend.db import checks, database, loader, models
from tests.unit.test_instructions import TEXTS, main_with, seeded  # noqa: F401 (seeded is a fixture)
from tests.unit.test_loader import run_folder

STATUS = ["Missing", "Wounded", "POW = Prisoner of war"]


@pytest.mark.parametrize("rule, value, problem", [
    ({"type": "text", "required": True}, " ", "Required, but empty"),
    ({"type": "text", "required": True}, "/", "Required, but empty"),  # crossed out: nothing there
    ({"type": "number", "required": True}, "[?]", None),  # unreadable: flagged as that already
    ({"type": "number"}, None, None),
    ({"type": "number"}, "twelve", "Should be a number"),
    ({"type": "number"}, "1,234.5", None),
    ({"type": "number", "min": 14, "max": 70}, "71", "Should be from 14 to 70"),
    ({"type": "number", "min": 14}, "13", "Should be at least 14"),
    ({"type": "date"}, "12 March 1917", None),
    ({"type": "date"}, "12/3/17", None),
    ({"type": "date"}, "Sept. 1917", None),
    ({"type": "date"}, "31/2/1917", "Should be a date, like 12 March 1917 or 12/3/1917"),
    ({"type": "date"}, "soon", "Should be a date, like 12 March 1917 or 12/3/1917"),
    ({"type": "date", "min": "1914", "max": "4 Aug 1920"}, "March 1913", "Should be from 1914 to 4 Aug 1920"),
    ({"type": "date", "max": "1920"}, "12/3/20", None),  # its century isn't known: no range to check
    ({"type": "date", "max": "4 Aug 1920"}, "August 1920", None),  # as far as it goes, it's in range
    ({"type": "yes_no"}, "Y", None),
    ({"type": "yes_no"}, "maybe", "Should be yes or no"),
    ({"type": "one_of", "values": STATUS}, "wounded", None),
    ({"type": "one_of", "values": STATUS}, "Prisoner of war", None),  # its meaning will do
    ({"type": "one_of", "values": STATUS}, "Killed", "Should be one of: Missing, Wounded, POW"),
    ({"type": "one_of", "values": ["000-996 = Code", "999 = Not known"]}, "042", None),
    ({"type": "one_of", "values": ["000-996 = Code", "999 = Not known"]}, "997", "Should be one of: 000-996, 999"),
    ({"type": "several_of", "values": STATUS}, "Wounded, POW", None),
    ({"type": "several_of", "values": STATUS}, "Wounded; Killed", "“Killed” isn't one of: Missing, Wounded, POW"),
    ({"type": "pattern", "pattern": r"[A-Z]?\d+", "example": "A12524"}, "A-12", "Should look like A12524"),
    ({"type": "pattern", "pattern": r"[A-Z]?\d+"}, "A12524", None),
])
def test_a_value_breaking_its_rule_says_why(rule, value, problem):
    assert checks.value_problem(rule, value) == problem


TEMPLATE = {"name": "Surname, then given names", "status": None, "age": None, "dates": {"reported": None},
            "residents": [{"age": None}]}


@pytest.mark.parametrize("rules, problem", [
    ({"surname": {"type": "text"}}, "'surname' isn't a field of the template"),
    ({"dates": {"type": "date"}}, "'dates' isn't a field of the template"),  # a group, not a field
    ({"residents.age": {"type": "number"}}, "'residents.age' isn't a field of the template"),  # in a list: not checked
    ({"age": {"type": "integer"}}, "'age': a rule has a type"),
    ({"age": {"type": "number", "colour": "red"}}, "'age': a rule has a type"),
    ({"age": {"type": "number", "required": "yes"}}, "'age': required is true or false"),
    ({"age": {"type": "number", "min": "old"}}, "'age': its range must be numbers"),
    ({"age": {"type": "number", "min": 70, "max": 14}}, "'age': its lowest is above its highest"),
    ({"dates.reported": {"type": "date", "min": "1920", "max": "1914"}}, "'dates.reported': its lowest is above its highest"),
    ({"name": {"type": "text", "max": 5}}, "'name': only a number or a date has a range"),
    ({"status": {"type": "one_of", "values": []}}, "'status': list the values it may take"),
    ({"status": {"type": "pattern"}}, "'status': give the pattern"),
    ({"status": {"type": "pattern", "pattern": "[A-"}}, "'status': its pattern isn't valid"),
    ({"status": {"type": "pattern", "pattern": r"\d+", "example": "A1"}}, "'status': its example A1 doesn't match its pattern"),
])
def test_rules_that_dont_fit_the_template_or_make_no_sense_are_refused(rules, problem):
    assert any(found.startswith(problem) for found in checks.rule_problems(rules, TEMPLATE))


def test_sensible_rules_pass():
    assert checks.rule_problems({"age": {"type": "number", "required": True, "min": 14, "max": 70},
                                 "status": {"type": "one_of", "values": STATUS},
                                 "dates.reported": {"type": "date", "min": "1914"}}, TEMPLATE) == []


def test_a_templates_rules_are_saved_with_it_changed_alone_and_refused_when_they_dont_fit(client, seeded):
    main_id = client.get("/instructions").json()["main"]["id"]
    rules = {"number_of_dwelling": {"type": "text", "required": True}}

    def save(**changes):
        return client.post("/instructions/main", json={"body": TEXTS["main"], "basedOn": main_id, "reviewerId": 1, **changes})

    assert save().json()["detail"] == "Nothing changed."
    refused = save(rules={"dwelling": {"type": "text"}})
    assert (refused.status_code, refused.json()["detail"]) == (400, ["'dwelling' isn't a field of the template"])
    saved = save(rules=rules)  # the rules alone are a new version of the template
    assert (saved.status_code, saved.json()["rules"]) == (201, rules)
    assert [v["rules"] for v in client.get("/instructions/main").json()] == [rules, {}]  # newest first; version 1 had none
    assert client.get("/instructions").json()["main"]["rules"] == rules
    prompt_id = client.get("/instructions").json()["prompt"]["id"]
    prompt = client.post("/instructions/prompt", json={"body": TEXTS["prompt"] + " ", "basedOn": prompt_id, "reviewerId": 1,
                                                        "rules": rules})
    assert (prompt.status_code, prompt.json()["detail"]) == (400, "The prompt has no fields to set rules on.")


def test_a_loaded_items_values_that_break_their_rules_are_flagged_and_a_new_check_replaces_the_last(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)
    engine = database.make_engine(url)
    monkeypatch.setattr(database, "engine", engine)
    rules = {"type_of_family": {"type": "one_of", "values": ["1 = Complete simple family", "2", "3"]},
             "normal_household_income": {"type": "number", "max": 300}, "weekly_rent": {"type": "number"},
             "washouse": {"type": "number", "required": True}}
    with sqlite3.connect(tmp_path / "test.db") as con:  # the coded card's newest template, with rules
        body, sha = con.execute("SELECT body, sha256 FROM instruction_versions WHERE kind = 'coded'").fetchone()
        con.execute("INSERT INTO instruction_versions (kind, body, sha256, rules) VALUES ('coded', ?, ?, ?)", (body, sha, json.dumps(rules)))
    loader.dump_into_db(run_folder(tmp_path) / "manifest.json")

    def invalid():
        with sqlite3.connect(tmp_path / "test.db") as con:
            return con.execute("SELECT page_id, field_title, reason FROM flags WHERE kind = 'invalid' ORDER BY field_title").fetchall()
    assert invalid() == [("216412_00002", "normal_household_income", "Should be at most 300")]  # weekly_rent is 1[?]: unreadable

    with engine.begin() as con:
        con.exec_driver_sql("UPDATE fields SET text_raw = '' WHERE field_title = 'washouse'")
        con.exec_driver_sql("UPDATE instruction_versions SET rules = ? WHERE rules IS NOT NULL",
                            (json.dumps({**rules, "normal_household_income": {"type": "number"}}),))
        checks.check_pages(con, ["216412_00001", "216412_00002"])
    assert invalid() == [("216412_00002", "washouse", "Required, but empty")]
    with sqlite3.connect(tmp_path / "test.db") as con:  # the other kinds of flag are left alone
        assert con.execute("SELECT kind FROM flags WHERE kind != 'invalid'").fetchall() == [("inconsistency",)]


def test_a_page_read_again_is_checked_against_its_types_rules(client, db, monkeypatch):
    from backend import worker
    from tests.unit.test_page_transcription import queue, setup_page
    setup_page(db, monkeypatch)  # reading the page again gives its address as 'New'
    db.add(models.InstructionVersion(kind="main", body='{"address":null}', sha256="m", rules=json.dumps({"address": {"type": "number"}})))
    db.commit()
    assert queue(client).status_code == 200
    assert worker.work_once(db)
    db.expire_all()
    assert [(f.page_id, f.field_title, f.kind, f.reason) for f in db.query(models.Flag)] == [("b/p4", "address", "invalid", "Should be a number")]
