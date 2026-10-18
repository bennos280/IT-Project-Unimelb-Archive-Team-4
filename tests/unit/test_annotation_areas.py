"""backend/db/annotation_areas.py: gives the annotations without an area one; a dry run writes nothing, --apply backs the db up first."""
import csv
import json
import shutil
import sqlite3
import subprocess
from contextlib import closing

import pytest
from alembic import command

from backend.common import ROOT
from backend.db import annotation_areas, database

ANNOTATIONS = [  # page, no, location, area already stored
    ("m", 0, "right margin below codes, red pencil", None),
    ("m", 1, "residential pref row (red)", None),
    ("m", 2, "after municipality", "header"),  # has an area: left alone
    ("m", 3, "somewhere odd", None),
    ("m", 4, "star by the fold", None),  # a phrases file knows it
    ("c", 0, "bottom centre, red pencil", None),
    ("c", 1, "star by the fold", None),
    ("n", 0, "top-left", None),  # a notes page: left alone
]
BAND = {"x": 0.04, "y": 0.67, "width": 0.57, "height": 0.028}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    database.migrate(f"sqlite:///{path.as_posix()}")
    with closing(sqlite3.connect(path)) as con, con:
        con.execute("INSERT INTO bundles(bundle_id, source_pdf) VALUES('b', 'b.pdf')")
        for page, category in (("m", "main"), ("c", "coded"), ("n", "notes")):
            con.execute("INSERT INTO pages(page_id, import_path, bundle_id, category) VALUES(?, 'p.png', 'b', ?)", (page, category))
        con.executemany("INSERT INTO annotations(page_id, annotation_no, text_raw, location, area) VALUES(?, ?, '*', ?, ?)", ANNOTATIONS)
    return path


def stored(db):
    with closing(sqlite3.connect(db)) as con:
        rows = con.execute("SELECT page_id, annotation_no, area, region FROM annotations ORDER BY page_id, annotation_no").fetchall()
    return [(p, n, area, region and json.loads(region)) for p, n, area, region in rows]


def csv_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(db, tmp_path, *args):
    annotation_areas.main(["--db", str(db), "--report", str(tmp_path / "report"), *args])


def test_a_dry_run_writes_nothing_to_the_db_and_reports(db, tmp_path, capsys):
    before = db.read_bytes()
    run(db, tmp_path)
    assert db.read_bytes() == before and not list(tmp_path.glob("*backup*"))
    out = capsys.readouterr().out
    assert "annotations without an area (main/coded): 6" in out and "matched by rules: 3" in out
    assert "unmatched: 3" in out and "with a region: 1" in out
    assert "main right_margin: 1" in out and "main residents_table: 1" in out and "coded bottom_centre: 1" in out
    assert "nothing written" in out
    mapped = csv_rows(tmp_path / "report" / "mapped.csv")
    assert [(r["page_id"], r["annotation_no"], r["page_type"], r["area"], r["source"]) for r in mapped] == [
        ("m", "0", "main", "right_margin", "rules"), ("m", "1", "main", "residents_table", "rules"),
        ("c", "0", "coded", "bottom_centre", "rules")]
    assert json.loads(mapped[1]["region"]) == pytest.approx(BAND) and mapped[0]["region"] == ""
    assert sorted((r["page_type"], r["location"], r["count"]) for r in csv_rows(tmp_path / "report" / "leftovers.csv")) == [
        ("coded", "star by the fold", "1"), ("main", "somewhere odd", "1"), ("main", "star by the fold", "1")]


def test_the_leftovers_are_counted_and_the_most_frequent_comes_first(db, tmp_path):
    with closing(sqlite3.connect(db)) as con, con:
        con.executemany("INSERT INTO annotations(page_id, annotation_no, text_raw, location) VALUES('m', ?, '*', 'odd twice')", [(10,), (11,)])
    run(db, tmp_path)
    assert [(r["location"], r["count"]) for r in csv_rows(tmp_path / "report" / "leftovers.csv")][0] == ("odd twice", "2")


def test_a_report_folder_is_made_when_none_is_given(db, capsys):
    annotation_areas.main(["--db", str(db)])
    folder = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("report: "))[len("report: "):]
    try:
        assert csv_rows(f"{folder}/mapped.csv") and csv_rows(f"{folder}/leftovers.csv")
    finally:
        shutil.rmtree(folder)


def test_apply_backs_the_db_up_then_sets_only_the_rows_without_an_area(db, tmp_path, capsys):
    before = stored(db)
    run(db, tmp_path, "--apply")
    assert stored(db) == [
        ("c", 0, "bottom_centre", None), ("c", 1, None, None),
        ("m", 0, "right_margin", None), ("m", 1, "residents_table", pytest.approx(BAND)),
        ("m", 2, "header", None),  # its area is kept
        ("m", 3, None, None), ("m", 4, None, None), ("n", 0, None, None)]
    (backup,) = tmp_path.glob("wilfprestsurvey-backup-areas-*.db")
    assert stored(backup) == before
    out = capsys.readouterr().out
    assert "integrity_check: ok" in out and "before 1 / 6, after 4 / 3" in out and str(backup) in out


def test_apply_twice_changes_nothing_the_second_time(db, tmp_path):
    run(db, tmp_path, "--apply")
    once = stored(db)
    run(db, tmp_path, "--apply")
    assert stored(db) == once


def test_phrases_fill_in_only_what_the_rules_did_not_match_and_unknown_areas_are_ignored(db, tmp_path, capsys):
    phrases = tmp_path / "phrases.json"
    phrases.write_text(json.dumps({
        "main": {"star by the fold": "kitchen_block", "right margin below codes, red pencil": "header",  # the rules win
                 "somewhere odd": "unknown"},
        "coded": {"star by the fold": "kitchen_block",  # a main form's area on a coded card
                  "bottom centre, red pencil": "left_column"}}), encoding="utf-8")
    run(db, tmp_path, "--phrases", str(phrases))
    out = capsys.readouterr().out
    assert "matched by rules: 3, by phrases: 1, unmatched: 2" in out and 'phrases ignored (unknown area or "unknown"): 2' in out
    assert [(r["page_id"], r["annotation_no"], r["area"], r["source"]) for r in csv_rows(tmp_path / "report" / "mapped.csv")] == [
        ("m", "0", "right_margin", "rules"), ("m", "1", "residents_table", "rules"), ("m", "4", "kitchen_block", "phrases"),
        ("c", "0", "bottom_centre", "rules")]
    run(db, tmp_path, "--phrases", str(phrases), "--apply")
    rows = stored(db)
    assert rows[:2] == [("c", 0, "bottom_centre", None), ("c", 1, None, None)] and rows[6] == ("m", 4, "kitchen_block", None)


def test_a_phrases_file_of_the_wrong_shape_stops_the_run(db, tmp_path):
    phrases = tmp_path / "phrases.json"
    phrases.write_text('["not", "a", "map"]', encoding="utf-8")
    before = db.read_bytes()
    with pytest.raises(SystemExit, match="expected"):
        run(db, tmp_path, "--phrases", str(phrases), "--apply")
    assert db.read_bytes() == before and not list(tmp_path.glob("*backup*"))


def test_apply_refuses_a_db_that_has_not_been_migrated_and_a_dry_run_still_counts(db, tmp_path, capsys):
    command.downgrade(database.alembic_config(f"sqlite:///{db.as_posix()}"), "005")
    before = db.read_bytes()
    run(db, tmp_path)  # every annotation counts as without an area
    assert "annotations without an area (main/coded): 7" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="start the app once to migrate"):
        run(db, tmp_path, "--apply")
    assert db.read_bytes() == before and not list(tmp_path.glob("*backup*"))


def test_a_missing_db_is_not_created(tmp_path):
    with pytest.raises(SystemExit, match="No db"):
        annotation_areas.main(["--db", str(tmp_path / "nothing.db")])
    assert not (tmp_path / "nothing.db").exists()


def test_the_backups_are_ignored_by_git():
    check = subprocess.run(["git", "check-ignore", "-q", "backend/db/wilfprestsurvey-backup-areas-20261018-120000.db"], cwd=ROOT)
    assert check.returncode == 0
