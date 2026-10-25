"""A series' checks across fields (backend/db/checks.py): saved as versions, and a record's values that fail one flagged for review
(kind check) when its item loads, a page is read again, or the series is checked again."""
import json
import logging

import pytest

from backend import worker
from backend.db import checks, models

ROOMS = {"id": "rooms", "kind": "compare", "left": ["main.living", "main.bedrooms"], "op": "=", "right": ["coded.total_rooms"]}
AT_MOST_11 = {"id": "max", "kind": "compare", "left": ["coded.total_rooms"], "op": "<=", "value": "11"}
DEATH = {"id": "death", "kind": "if", "if": "card.status", "is": "is", "isValue": "Killed", "then": "card.date_of_death", "must": "filled"}


@pytest.mark.parametrize("check, values, reason", [
    (ROOMS, {"main.living": "2", "main.bedrooms": "3", "coded.total_rooms": "6"}, "Living + Bedrooms (2 + 3) should equal Total rooms (6)"),
    (ROOMS, {"main.living": "2", "main.bedrooms": "3", "coded.total_rooms": "5"}, None),
    (ROOMS, {"main.living": "2", "main.bedrooms": "/", "coded.total_rooms": "6"}, None),  # crossed out: can't be told
    (ROOMS, {"main.living": "2", "main.bedrooms": "3[?]", "coded.total_rooms": "6"}, None),  # unreadable: can't be told
    (ROOMS, {"main.living": "2", "coded.total_rooms": "6"}, None),  # a field the page lacks
    ({**ROOMS, "message": "Rooms don't add up"}, {"main.living": "2", "main.bedrooms": "3", "coded.total_rooms": "6"}, "Rooms don't add up"),
    (AT_MOST_11, {"coded.total_rooms": "12"}, "Total rooms (12) should be at most 11"),
    ({"id": "d", "kind": "compare", "left": ["card.reported"], "op": ">=", "right": ["card.casualty"]},
     {"card.reported": "1916", "card.casualty": "12 March 1917"}, "Reported (1916) should be at least Casualty (12 March 1917)"),
    ({"id": "d", "kind": "compare", "left": ["card.reported"], "op": ">=", "right": ["card.casualty"]},
     {"card.reported": "March 1917", "card.casualty": "12 March 1917"}, None),  # the same, as far as both go
    ({"id": "t", "kind": "compare", "left": ["main.built_of"], "op": "=", "right": ["coded.material"]},
     {"main.built_of": "Brick", "coded.material": " brick "}, None),
    ({"id": "t", "kind": "compare", "left": ["main.built_of"], "op": "=", "right": ["coded.material"]},
     {"main.built_of": "Brick", "coded.material": "Stone"}, "Built of (Brick) should equal Material (Stone)"),
    ({"id": "t", "kind": "compare", "left": ["main.built_of"], "op": "<", "right": ["coded.material"]},
     {"main.built_of": "Brick", "coded.material": "Stone"}, None),  # words aren't more or less
    (DEATH, {"card.status": "killed", "card.date_of_death": ""}, "Status is Killed, so Date of death should be filled"),
    (DEATH, {"card.status": "Killed", "card.date_of_death": "3/5/1917"}, None),
    (DEATH, {"card.status": "Wounded", "card.date_of_death": None}, None),
    (DEATH, {"card.status": "Killed.", "card.date_of_death": "/"}, "Status is Killed, so Date of death should be filled"),
    ({"id": "d", "kind": "compare", "left": ["card.reported"], "op": "=", "right": ["card.casualty"]},
     {"card.reported": "12 March 1917.", "card.casualty": "12 March 1917"}, None),  # the card's own full stop
    ({"id": "d", "kind": "compare", "left": ["card.reported"], "op": "=", "right": ["card.casualty"]},
     {"card.reported": "12/3/17", "card.casualty": "12/03/1917"}, None),  # a two-digit year: can't be told
    ({"id": "s", "kind": "compare", "left": ["a.x", "a.y"], "op": "=", "right": ["a.z"]},
     {"a.x": "0.1", "a.y": "0.2", "a.z": "0.3"}, None),  # decimals add up
    ({"id": "s", "kind": "compare", "left": ["a.x", "a.y"], "op": "=", "right": ["a.z"]},
     {"a.x": "nil", "a.y": "2", "a.z": "2"}, None),  # nil is none
    ({"id": "v", "kind": "compare", "left": ["a.tenure"], "op": "=", "value": "N/A"},
     {"a.tenure": "Owner"}, "Tenure (Owner) should equal N/A"),  # a check's own value is never unsure
    ({"id": "t", "kind": "compare", "left": ["a.x"], "op": "=", "right": ["b.x"]},
     {"a.x": "Owner (part)", "b.x": "owner (part)"}, None),  # brackets around words aren't unsure
    ({"id": "t", "kind": "compare", "left": ["a.area"], "op": "=", "right": ["b.area"]},
     {"a.area": "1.5 acres", "b.area": "15 acres"}, "Area (1.5 acres) should equal Area (15 acres)"),  # a decimal point counts
    ({"id": "t", "kind": "compare", "left": ["a.tick"], "op": "=", "right": ["b.tick"]},
     {"a.tick": "✓", "b.tick": "✗"}, "Tick (✓) should equal Tick (✗)"),
    ({"id": "e", "kind": "if", "if": "card.discharged", "is": "filled", "then": "card.unit", "must": "empty"},
     {"card.discharged": "1919", "card.unit": "7th Bn"}, "Discharged is filled, so Unit should be empty"),
])
def test_a_check_says_why_it_fails(check, values, reason):
    assert checks.check_failure(check, values.get) == reason


FIELDS = {"main": {"living", "bedrooms"}, "coded": {"total_rooms"}}


@pytest.mark.parametrize("found, problem", [
    ({"kind": "compare"}, "Check 1: needs an id of its own"),
    ({"id": "a", "kind": "sum"}, "Check 1: compares fields, or says if one field is so another must be"),
    ({**ROOMS, "left": ["main.kitchen"]}, "Check 1: main.kitchen isn't a field of this series' page types"),
    ({**ROOMS, "right": ["letters.name"]}, "Check 1: letters.name isn't a field of this series' page types"),
    ({**ROOMS, "op": "=="}, "Check 1: compares with one of"),
    ({**ROOMS, "left": []}, "Check 1: needs a field to compare"),
    ({**ROOMS, "value": "5"}, "Check 1: compares with fields or with a value"),
    ({**AT_MOST_11, "value": " "}, "Check 1: compares with fields or with a value"),
    ({"id": "i", "kind": "if", "if": "main.living", "is": "is", "then": "coded.total_rooms", "must": "filled"}, "Check 1: is is filled, empty, or a value"),
    ({**ROOMS, "on": "yes"}, "Check 1: on is true or false"),
    ({**ROOMS, "left": [{"main": "living"}]}, "Check 1: isn't written as a check"),
])
def test_checks_that_name_no_field_of_the_series_or_make_no_sense_are_refused(found, problem):
    assert any(p.startswith(problem) for p in checks.check_problems([found], FIELDS))


def test_sensible_checks_pass_and_ids_are_their_own():
    assert checks.check_problems([ROOMS, AT_MOST_11], FIELDS) == []
    assert checks.check_problems([ROOMS, ROOMS], FIELDS) == ["Check 2: needs an id of its own"]
    assert checks.check_problems({"rooms": ROOMS}, FIELDS) == ["Checks must be a list"]


def add(db, *rows):
    """Adds rows one at a time: the db checks foreign keys, and the models don't say which to insert first."""
    for row in rows:
        db.add(row)
        db.flush()


def record(db, survey, pages):
    """A record (survey) of pages, each {page: (type, {field: value})}, in bundle b of the Prest series."""
    if not db.get(models.Bundle, "b"):
        add(db, models.Bundle(bundle_id="b", source_pdf="b.pdf", collection_id=1))
    add(db, models.Survey(survey_id=survey, bundle_id="b"),
                 *[models.Page(page_id=page, bundle_id="b", survey_id=survey, category=kind, import_path=f"{page}.png")
                   for page, (kind, _) in pages.items()],
                 *[models.Field(page_id=page, field_title=field, text_raw=value)
                   for page, (_, fields) in pages.items() for field, value in fields.items()])


def flags(db, kind="check"):
    return sorted((f.page_id, f.field_title, f.reason) for f in db.query(models.Flag).filter_by(kind=kind))


def test_a_records_values_failing_a_check_are_flagged_on_each_field_it_names_and_checked_again_as_reviewers_left_them(db):
    record(db, "s1", {"s1-main": ("main", {"living": "2", "bedrooms": "3"}), "s1-coded": ("coded", {"total_rooms": "12"})})
    record(db, "s2", {"s2-coded-a": ("coded", {"total_rooms": "5"}), "s2-coded-b": ("coded", {"total_rooms": "14"})})
    db.add_all([models.CheckVersion(collection_id=1, body=json.dumps([ROOMS, AT_MOST_11, {**ROOMS, "id": "off", "on": False}])),
                models.Flag(page_id="s1-main", field_title="living", kind="inconsistency", reason="Grouping: 2 coded cards")])
    db.commit()
    checks.check_pages(db.connection(), ["s1-coded", "s2-coded-a"])  # each page's whole record is checked
    db.commit()
    assert flags(db) == [
        ("s1-coded", "total_rooms", "Living + Bedrooms (2 + 3) should equal Total rooms (12)"),
        ("s1-coded", "total_rooms", "Total rooms (12) should be at most 11"),
        ("s1-main", "bedrooms", "Living + Bedrooms (2 + 3) should equal Total rooms (12)"),
        ("s1-main", "living", "Living + Bedrooms (2 + 3) should equal Total rooms (12)"),
        ("s2-coded-b", "total_rooms", "Total rooms (14) should be at most 11"),  # two coded cards: the rooms check can't pair them
    ]
    db.add(models.Edit(page_id="s1-coded", field_title="total_rooms", edit_text="5", reviewer_id=None))
    db.commit()
    checks.check_pages(db.connection(), ["s1-main"])
    db.commit()
    assert flags(db) == [("s2-coded-b", "total_rooms", "Total rooms (14) should be at most 11")]  # s1 as its reviewer corrected it
    assert flags(db, "inconsistency") == [("s1-main", "living", "Grouping: 2 coded cards")]  # other flags are left alone


@pytest.fixture
def series(db):
    """The Prest series' main and coded templates, holding the fields its checks name, and a reviewer."""
    add(db, models.Reviewer(reviewer_id=1, name="Ben"),
                 models.InstructionVersion(kind="main", body='{"living": null, "bedrooms": null}', sha256="m"),
                 models.InstructionVersion(kind="coded", body='{"total_rooms": null}', sha256="c"))
    db.commit()
    return db


def test_a_series_checks_are_saved_as_versions_refused_when_they_dont_fit_and_an_old_one_can_come_back(client, series):
    assert client.get("/collections/1/checks").json() == []
    assert client.get("/collections/9/checks").status_code == 404

    def save(found, based_on=None, **extra):
        return client.post("/collections/1/checks", json={"checks": found, "basedOn": based_on, "reviewerId": 1, **extra})

    refused = save([{**ROOMS, "left": ["main.kitchen"]}])
    assert (refused.status_code, refused.json()["detail"]) == (400, ["Check 1: main.kitchen isn't a field of this series' page types"])
    first = save([ROOMS], note="rooms add up").json()
    assert (first["number"], first["checks"], first["reviewer"], first["note"]) == (1, [ROOMS], "Ben", "rooms add up")
    assert save([ROOMS], first["id"]).json()["detail"] == "Nothing changed."
    second = save([ROOMS, AT_MOST_11], first["id"]).json()
    assert save([AT_MOST_11], first["id"]).status_code == 409  # based on an older version
    third = save([ROOMS], second["id"])  # the first, brought back
    assert (third.status_code, third.json()["number"]) == (201, 3)
    assert [(v["number"], len(v["checks"])) for v in client.get("/collections/1/checks").json()] == [(3, 1), (2, 2), (1, 1)]
    assert save([], third.json()["id"]).status_code == 201  # no checks at all is a version too


def test_checking_a_series_again_is_a_task_that_flags_its_pages_and_logs_how_many(client, series, caplog):
    record(series, "s1", {"s1-main": ("main", {"living": "2", "bedrooms": "3"}), "s1-coded": ("coded", {"total_rooms": "12"})})
    series.add(models.CheckVersion(collection_id=1, body=json.dumps([ROOMS])))
    series.commit()
    queued = client.post("/collections/1/check")
    assert (queued.status_code, queued.json()["kind"]) == (202, "check")
    assert client.post("/collections/1/check").json()["detail"] == "This series is already being checked."
    assert client.get("/jobs").json()[0]["label"] == "Checking Wilfred Prest Survey"
    with caplog.at_level(logging.INFO, logger="worker"):
        assert worker.work_once(series)
    series.expire_all()
    job = series.get(models.Job, queued.json()["id"])
    assert (job.status, job.done_pages, job.total_pages) == ("done", 2, 2)
    assert len(flags(series)) == 3
    n = job.job_id
    assert [r.getMessage() for r in caplog.records][1:] == [
        f"job {n} step: check", f"job {n}: checking 2 pages with version 1 of the series' checks", f"job {n}: 3 fields flagged", f"job {n} done"]
    assert client.post("/collections/9/check").status_code == 404


def test_a_page_waiting_to_be_read_again_isnt_checked_and_its_last_flags_go(db):
    record(db, "s1", {"s1-main": ("main", {"living": "2", "bedrooms": "3"}), "s1-coded": ("coded", {"total_rooms": "12"})})
    db.add(models.CheckVersion(collection_id=1, body=json.dumps([ROOMS, AT_MOST_11])))
    db.commit()
    checks.check_pages(db.connection(), ["s1-main"])
    db.get(models.Page, "s1-coded").needs_transcription = True
    db.flush()
    checks.check_pages(db.connection(), ["s1-main"])
    db.commit()
    assert flags(db) == []  # its record has no coded page to check against until it's read


def test_a_page_moved_to_another_record_is_checked_there_and_the_record_it_left_again(client, series):
    record(series, "s1", {"s1-main": ("main", {"living": "2", "bedrooms": "3"}), "s1-coded": ("coded", {"total_rooms": "6"})})
    record(series, "s2", {"s2-main": ("main", {"living": "3", "bedrooms": "3"})})
    series.add(models.CheckVersion(collection_id=1, body=json.dumps([ROOMS])))
    series.commit()
    checks.check_pages(series.connection(), ["s1-main", "s2-main"])
    series.commit()
    assert {page for page, _, _ in flags(series)} == {"s1-main", "s1-coded"}
    moved = client.put("/page-moves/s1-coded", json={"surveyId": "s2", "sourceSurveyId": "s1", "reviewerId": 1, "revision": 0})
    assert moved.status_code == 200
    series.expire_all()
    assert flags(series) == []  # 3 + 3 is 6 in s2, and s1 has no coded page left


def test_a_page_changed_to_another_type_is_checked_against_that_types_rules(client, series):
    record(series, "s1", {"s1-main": ("main", {"living": "two"})})
    series.add(models.InstructionVersion(kind="main", body='{"living": null, "bedrooms": null}', sha256="m",
                                         rules=json.dumps({"living": {"type": "number"}})))
    series.commit()
    checks.check_pages(series.connection(), ["s1-main"])
    series.commit()
    assert flags(series, "invalid") == [("s1-main", "living", "Should be a number")]
    changed = client.put("/page-classification/s1-main", json={"pageType": "other", "reviewerId": 1, "revision": 0})
    assert changed.status_code == 200
    series.expire_all()
    assert flags(series, "invalid") == []  # the Unknown type has no rules


def _prest():
    """The Prest survey's checks and its coded card's rules, as its setup file (setups/wilfred-prest-survey.prestcribe) has them."""
    import sqlite3
    from pathlib import Path
    setup = sqlite3.connect(Path(checks.__file__).parents[2] / "setups" / "wilfred-prest-survey.prestcribe")
    [(body,)] = setup.execute("SELECT body FROM check_versions").fetchall()
    [(rules,)] = setup.execute("SELECT rules FROM instruction_versions WHERE kind = 'coded'").fetchall()
    setup.close()
    return {c["id"]: c for c in json.loads(body)}, json.loads(rules)


PREST_CHECKS, PREST_RULES = _prest()


@pytest.mark.parametrize("check, left, right, reason", [  # values as transcribed on the main form and the coded card
    ("dwelling_number", "24A", "24 a", None),
    ("dwelling_number", "03", "3", None),
    ("dwelling_number", "125A", "125", "Number of dwelling (125A) should equal Number of dwelling (125)"),
    ("dwelling_number", "4.", "265", "Number of dwelling (4.) should equal Number of dwelling (265)"),
    ("dwelling_number", "10/", "101", None),  # unsure as written
    ("dwelling_number", "45(1)", "45", None),
    ("industry_code", "0133", "133", None),
    ("industry_code", "013.3", "0133", None),  # a code is its digits
    ("industry_code", "17?", "173", None),
    ("occupation_code", "4309m", "4309", None),
    ("occupation_code", "173", "172", "Occupation of head code (173) should equal Occupation of head (172)"),
    ("municipality", "Camberwell", "03", None),
    ("municipality", "N. Fitzroy", "03", None),  # a suburb, not a council: can't be told
    ("municipality", "Brighton", "03", "Municipality (Brighton) should name Municipality 03 (Camberwell)"),
])
def test_the_prest_surveys_checks_flag_what_its_validation_did(check, left, right, reason):
    found = PREST_CHECKS[check]
    values = {found["left"][0]: left, found["right"][0]: right}
    def lists(ref):
        return PREST_RULES.get(ref.partition(".")[2], {}).get("values")
    assert checks.check_failure(found, values.get, lists) == reason


def test_the_prest_surveys_children_living_and_dead_add_up_to_the_total():
    found = PREST_CHECKS["children_living_plus_dead"]
    fields = dict(zip(found["left"] + found["right"], ("2", "3", "5")))
    assert checks.check_failure(found, fields.get) is None
    assert checks.check_failure(found, {**fields, found["right"][0]: "6"}.get).startswith("Children of head or wife living + ")


@pytest.mark.parametrize("found, problem", [
    ({**ROOMS, "op": "names"}, "Check 1: names compares one field with one coded field"),
    ({**ROOMS, "as": "letters"}, "Check 1: compares as values, or as codes"),
])
def test_names_and_codes_are_checked_when_saved(found, problem):
    assert any(p.startswith(problem) for p in checks.check_problems([found], FIELDS))
