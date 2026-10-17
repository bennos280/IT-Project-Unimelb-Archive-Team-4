"""A finished pipeline run (output/<bundle>/manifest.json) into the database: uv run python -m backend.db.loader"""
import json
from functools import cache
from pathlib import Path

from backend.db import database
from backend.common import ROOT, settings

CODED_DICT = Path(__file__).parent / "data_dict.json"
OTHER_CAT = "other" #a page identify wasn't sure about
META = ("provider", "model", "effort", "seconds") #how a page was read

#a run's pages into the db, all or nothing
def dump_into_db(manifest_path):
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not data.get("pages"):
        print("Bundle has no pages.")
        return
    run_folder = Path(manifest_path).resolve().parent
    bundle_id = run_folder.name

    transcripts = data.get("transcripts") or {}
    with database.engine.begin() as con:
        if not con.exec_driver_sql("INSERT OR IGNORE INTO bundles(bundle_id, source_pdf) VALUES(?, ?)",
                                   (bundle_id, stored_path(data["input"]))).rowcount:
            print(f"{bundle_id} is already in the database.")
            return
        page_types = {name for (name,) in con.exec_driver_sql("SELECT name FROM page_types")}
        for p in data["pages"]:
            if p.get("path") is None or p.get("label") in (None, "blank"):
                continue
            #a manifest written on Windows uses \
            page = run_folder / p["transcript"].replace("\\", "/") if p.get("transcript") else None
            category = p["label"] if page and p["label"] in page_types else OTHER_CAT
            insert_page(Path(p["file"]).stem, page, stored_path(p["path"]), category,
                        p.get("survey"), bundle_id, con, transcripts.get(p["file"], {}).get("request") if page else None)
        insert_flags(run_folder / "review.json", con)
        insert_check_flags(run_folder / "validation" / "output_flagged.json", con)


#request: how the page was read (from the manifest); its prompt and template hashes find their versions
def insert_page(page_id, page_p, src_img_p:str, category:str, survey_id:str | None, bundle_id:str, con, request=None):
    if survey_id is not None:
        con.exec_driver_sql("INSERT OR IGNORE INTO surveys(survey_id, bundle_id) VALUES(?, ?)", (survey_id, bundle_id))
    data = json.loads(page_p.read_text(encoding="utf-8")) if page_p else None
    if data and "engine" in data: #older runs call the provider engine
        data["provider"] = data.pop("engine")
    if data and "+" in (data.get("model") or ""): #older runs list every model Claude Code used: keep the one the run asked for
        asked = (request or {}).get("model")
        data["model"] = next((m for m in data["model"].split("+") if asked and asked in m), data["model"])
    versions = [version_id(con, kind, (request or {}).get(key)) for kind, key in (("prompt", "prompt"), (category, "template"))]
    con.exec_driver_sql("INSERT INTO pages(page_id, import_path, survey_id, bundle_id, category, provider, model, effort, runtime,"
                        " prompt_version_id, template_version_id) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (page_id, src_img_p, survey_id, bundle_id, category, *((data or {}).get(key) for key in META), *versions))
    insert_content(page_id, data, category, con)

#what was read off a page, into its tables; None (not read): just an empty text field to type into
def insert_content(page_id, data, category, con):
    if data is None:
        insert_field(page_id, "text", None, con, False)
        return
    for key, value in data.items():
        if key == "residents":
            for resident_no, resident in enumerate(value):
                con.exec_driver_sql("INSERT INTO residents(page_id, resident_no) VALUES(?, ?)", (page_id, resident_no))
                for title, raw in resident.items():
                    con.exec_driver_sql("INSERT INTO resident_fields(page_id, resident_no, resident_field_title, text_raw)"
                                        " VALUES(?, ?, ?, ?)", (page_id, resident_no, title, raw))
        elif key == "annotations":
            for annotation_no, annotation in enumerate(value):
                con.exec_driver_sql("INSERT INTO annotations(page_id, annotation_no, text_raw, location) VALUES(?, ?, ?, ?)",
                                    (page_id, annotation_no, annotation["raw"], annotation["location"]))
        elif key == "other_children":
            for residence in ("died", "living_elsewhere"):
                for child_no, child in enumerate(value.get(residence) or []):
                    con.exec_driver_sql("INSERT INTO other_children(page_id, residence, child_no, text_raw) VALUES(?, ?, ?, ?)",
                                        (page_id, residence, child_no, child))
        elif key not in META:
            insert_field(page_id, key, value, con, category == "coded")

#deletes what was read off a page, and with it its flags and edits, before it is read again
def clear_content(page_id, con):
    for table in ("fields", "residents", "other_children", "annotations"):
        con.exec_driver_sql(f"DELETE FROM {table} WHERE page_id = ?", (page_id,))

def insert_field(page_id, title:str, raw, con, coded:bool):
    if isinstance(raw, dict):
        for subtitle, subraw in raw.items():
            insert_field(page_id, f"{title}.{subtitle}", subraw, con, coded)
        return
    con.exec_driver_sql("INSERT INTO fields(page_id, field_title, text_raw, decoded_value) VALUES(?, ?, ?, ?)",
                        (page_id, title, raw, decode(title, raw) if coded else None))

#a coded field's value's meaning, from data_dict.json; None if it isn't one of the field's codes
def decode(title, raw):
    meaning = None
    if isinstance(raw, str) and raw.strip().isdigit():
        codes = coded_fields().get(title, {}).get("possible_values")
        for num, text in (codes if isinstance(codes, dict) else {}).items():
            low, _, high = num.partition("-") #a code is one number (07) or a range (000-996)
            if int(low) <= int(raw) <= int(high or low):
                meaning = text
    return meaning

#grouping problems become flags, on the page's dwelling number if it has one
def insert_flags(review_p, con):
    if not review_p.is_file():
        return
    for entry in json.loads(review_p.read_text(encoding="utf-8")):
        if entry.get("step") != "group":
            continue
        page_id = Path(entry["file"]).stem
        field = con.exec_driver_sql("""SELECT field_title FROM fields WHERE page_id = ?
            ORDER BY field_title != 'number_of_dwelling', rowid LIMIT 1""", (page_id,)).fetchone()
        if field is not None: #a blank page isn't in the db
            con.exec_driver_sql("""INSERT INTO flags(page_id, field_title, kind, reason)
                VALUES(?, ?, 'inconsistency', ?)""", (page_id, field[0], "Grouping: " + entry["reason"].split(": ", 1)[-1]))

#the consistency check's conflicts become flags on the fields they name (a resident's field isn't in fields: skipped);
#"comparison incomplete" (one side blank or unreadable) isn't a conflict
def insert_check_flags(check_p, con):
    if not check_p.is_file():
        return
    for survey in json.loads(check_p.read_text(encoding="utf-8"))["surveys"]:
        pages = {"Page 1": survey["page_files"]["main"], "Page 3": survey["page_files"]["coded"]}
        for flag in survey["validation_flags"]:
            if "incomplete" in flag["type"]:
                continue
            for path in flag["fields"]:
                page, _, field_title = path.partition(": ")
                if page in pages:
                    con.exec_driver_sql("""INSERT INTO flags(page_id, field_title, kind, reason)
                        SELECT page_id, field_title, 'inconsistency', ? FROM fields WHERE page_id = ? AND field_title = ?""",
                        ("Consistency: " + flag["reason"], Path(pages[page]).stem, field_title))

#the first version of kind with this text's hash; None if no version has it
def version_id(con, kind, sha):
    return sha and con.exec_driver_sql("SELECT MIN(version_id) FROM instruction_versions WHERE kind = ? AND sha256 = ?",
                                       (kind, sha)).scalar()

#relative to the repo with /, so the db works on any checkout
def stored_path(path):
    path = Path(path).resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)

@cache
def coded_fields():
    return json.loads(CODED_DICT.read_text(encoding="utf-8"))["pages"]["3"]["fields"]

def main():
    from backend.pipeline.run import FULL, completed
    database.migrate()
    with database.engine.connect() as con:
        loaded = {bundle_id for (bundle_id,) in con.exec_driver_sql("SELECT bundle_id FROM bundles")}
    for file_path in sorted((ROOT / settings()["OUTPUT"]).rglob('manifest.json')):
        if file_path.parent.name in loaded:
            continue
        if completed(file_path.parent, FULL):
            print(file_path)
            dump_into_db(file_path)
        else:
            print(f"{file_path}: run not finished, not loaded")

if __name__ == "__main__":
    main()