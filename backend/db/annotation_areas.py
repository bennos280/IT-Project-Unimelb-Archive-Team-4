"""Gives the annotations that have no area one, from their location text: a dry run unless --apply.
uv run python -m backend.db.annotation_areas [--db PATH] [--report DIR] [--phrases FILE] [--apply]"""
import argparse
import csv
import json
import sqlite3
import sys
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path

from backend.pipeline.transcribe import area_rules, areas

DB = Path(__file__).with_name("wilfprestsurvey.db")
PAGE_TYPES = ("main", "coded")
SELECT = ("SELECT a.page_id, a.annotation_no, p.category, a.location FROM annotations a JOIN pages p USING(page_id)"
          " WHERE p.category IN ('main', 'coded')")


def columns(con):
    return {row[1] for row in con.execute("PRAGMA table_info(annotations)")}


def counts(con):
    """(annotations with an area, without one) on main and coded pages."""
    return con.execute("SELECT COALESCE(SUM(a.area IS NOT NULL), 0), COALESCE(SUM(a.area IS NULL), 0) FROM annotations a"
                       " JOIN pages p USING(page_id) WHERE p.category IN ('main', 'coded')").fetchone()


def load_phrases(path):
    """{page type: {exact location text: area name}} with the unknown areas left out, and how many were."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(data.get(t, {}), dict) for t in PAGE_TYPES):
        sys.exit(f"{path}: expected {{\"main\": {{text: area}}, \"coded\": {{text: area}}}}")
    phrases, ignored = {t: {} for t in PAGE_TYPES}, 0
    for page_type in PAGE_TYPES:
        for text, area in data.get(page_type, {}).items():
            if area in areas.names(page_type): phrases[page_type][text] = area
            else: ignored += 1
    return phrases, ignored


def classify(rows, phrases):
    """(mapped, leftovers): mapped rows are (page_id, annotation_no, page type, location, area, region, source);
    leftovers counts the (page type, location) of the rest."""
    mapped, leftovers = [], Counter()
    for page_id, annotation_no, page_type, location in rows:
        area, region = area_rules.place(page_type, location)
        if area: mapped.append((page_id, annotation_no, page_type, location, area, region, "rules"))
        elif location in phrases[page_type]:
            mapped.append((page_id, annotation_no, page_type, location, phrases[page_type][location], None, "phrases"))
        else: leftovers[(page_type, location or "")] += 1
    return mapped, leftovers


def write_report(folder, mapped, leftovers):
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "mapped.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["page_id", "annotation_no", "page_type", "location", "area", "region", "source"])
        for row in mapped: out.writerow([*row[:5], json.dumps(row[5]) if row[5] else "", row[6]])
    with open(folder / "leftovers.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["page_type", "location", "count"])
        for (page_type, location), n in leftovers.most_common():
            if location: out.writerow([page_type, location, n])  #no location: nothing to go on


def apply(db, mapped):
    """Backs up the db, then sets the area and region of the rows still without an area, in one transaction."""
    with closing(sqlite3.connect(db)) as con:
        migrated = {"area", "region"} <= columns(con)
    if not migrated:
        sys.exit("The db has no area/region columns: start the app once to migrate it, then run this again.")
    backup = db.with_name(f"wilfprestsurvey-backup-areas-{datetime.now():%Y%m%d-%H%M%S}.db")
    with closing(sqlite3.connect(db)) as src, closing(sqlite3.connect(backup)) as dst:
        src.backup(dst)
    con = sqlite3.connect(db, isolation_level=None)
    before = counts(con)
    con.execute("BEGIN IMMEDIATE")
    try:
        for page_id, annotation_no, _, _, area, region, _ in mapped:
            con.execute("UPDATE annotations SET area = ?, region = ? WHERE page_id = ? AND annotation_no = ? AND area IS NULL",
                        (area, json.dumps(region) if region else None, page_id, annotation_no))
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    print(f"backup: {backup}\nintegrity_check: {con.execute('PRAGMA integrity_check').fetchone()[0]}")
    after = counts(con)
    con.close()
    print(f"main/coded annotations with an area / without: before {before[0]} / {before[1]}, after {after[0]} / {after[1]}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--phrases", type=Path)
    parser.add_argument("--apply", action="store_true", help="write the areas (after a backup); without it nothing is written")
    args = parser.parse_args(argv)
    if not args.db.is_file(): sys.exit(f"No db at {args.db}")
    phrases, ignored = load_phrases(args.phrases) if args.phrases else ({t: {} for t in PAGE_TYPES}, 0)
    #read-only: a dry run cannot write to the db
    with closing(sqlite3.connect(f"{args.db.resolve().as_uri()}?mode=ro", uri=True)) as con:
        #a db before the migration has no area: every annotation is without one
        rows = con.execute(SELECT + (" AND a.area IS NULL" if "area" in columns(con) else "")).fetchall()
    mapped, leftovers = classify(rows, phrases)
    report = args.report or Path(tempfile.mkdtemp(prefix="annotation-areas-"))
    write_report(report, mapped, leftovers)
    print(f"report: {report}\nannotations without an area (main/coded): {len(rows)}")
    print(f"matched by rules: {sum(m[6] == 'rules' for m in mapped)}, by phrases: {sum(m[6] == 'phrases' for m in mapped)}, "
          f"unmatched: {sum(leftovers.values())}, with a region: {sum(bool(m[5]) for m in mapped)}")
    if args.phrases: print(f"phrases ignored (unknown area or \"unknown\"): {ignored}")
    for (page_type, area), n in sorted(Counter((m[2], m[4]) for m in mapped).items()):
        print(f"  {page_type} {area}: {n}")
    if args.apply: apply(args.db, mapped)
    else: print("dry run: nothing written (--apply to write)")


if __name__ == "__main__":
    main()
