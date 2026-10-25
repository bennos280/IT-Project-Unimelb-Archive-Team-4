"""A finished pipeline run (output/<bundle>/manifest.json) into the database: uv run python -m backend.db.loader"""
import json
from functools import cache
from pathlib import Path, PurePosixPath

from backend.db import checks, database, models
from backend.common import ROOT, settings
from backend.pipeline.transcribe import areas

CODED_DICT = Path(__file__).parent / "data_dict.json"
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
        if not con.exec_driver_sql("INSERT OR IGNORE INTO bundles(bundle_id, source_pdf, collection_id) VALUES(?, ?, ?)",
                                   (bundle_id, stored_path(data["input"]), series(con, data))).rowcount:
            print(f"{bundle_id} is already in the database.")
            return
        #the bundle's collection's page types; a page sorting couldn't place, or not read, is its Unknown type
        types = con.exec_driver_sql("SELECT name, unknown FROM page_types WHERE collection_id ="
                                    " (SELECT collection_id FROM bundles WHERE bundle_id = ?)", (bundle_id,)).fetchall()
        page_types, unknown = {name for name, _ in types}, next((name for name, is_unknown in types if is_unknown), None)
        for record in data.get("records", []):  #parents first; an older run's records are its pages' surveys, all at the top
            con.exec_driver_sql("INSERT OR IGNORE INTO surveys(survey_id, bundle_id, parent_id) VALUES(?, ?, ?)",
                                (record["id"], bundle_id, record["parent"]))
        for p in data["pages"]:
            if p.get("path") is None or p.get("label") in (None, "blank"):
                continue
            #a manifest written on Windows uses \
            page = run_folder / p["transcript"].replace("\\", "/") if p.get("transcript") and p["label"] in page_types else None
            category = p["label"] if page else unknown
            if category is None:
                raise ValueError(f"Bundle {bundle_id}'s collection has no Unknown page type to store {p['file']} as.")
            insert_page(Path(p["file"]).stem, page, stored_path(p["path"]), category,
                        p.get("survey"), bundle_id, con, transcripts.get(p["file"], {}).get("request") if page else None)
        keys = [key for (key,) in con.exec_driver_sql("SELECT record_key FROM record_levels WHERE record_key IS NOT NULL AND"
                                                     " collection_id = (SELECT collection_id FROM bundles WHERE bundle_id = ?)", (bundle_id,))]
        insert_flags(run_folder / "review.json", con, keys)
        checks.check_pages(con, [p for (p,) in con.exec_driver_sql("SELECT page_id FROM pages WHERE bundle_id = ?", (bundle_id,))])


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
    collection = con.exec_driver_sql("SELECT collection_id FROM bundles WHERE bundle_id = ?", (bundle_id,)).scalar()
    versions = [version_id(con, kind, (request or {}).get(key), collection) for kind, key in (("prompt", "prompt"), (category, "template"))]
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
        if key == "annotations":
            for annotation_no, annotation in enumerate(value):
                area = annotation.get("area")  #older transcripts have none
                con.exec_driver_sql("INSERT INTO annotations(page_id, annotation_no, text_raw, location, area) VALUES(?, ?, ?, ?, ?)",
                                    (page_id, annotation_no, annotation["raw"], annotation["location"],
                                     area if area in areas.names(category) else None))
        elif key not in META:
            insert_field(page_id, key, value, con, category == "coded")

#deletes what was read off a page, and with it its flags and edits, before it is read again
def clear_content(page_id, con):
    for table in ("fields", "annotations"):
        con.exec_driver_sql(f"DELETE FROM {table} WHERE page_id = ?", (page_id,))

#a value read off a page into fields, by its dotted path: an object's values each by theirs; a list's items numbered from 0 in
#its list (of objects: each of their values; of text: one value with field_title ""); a list in a list's item is refused
def insert_field(page_id, title:str, raw, con, coded:bool, list_name="", item_no=0):
    if isinstance(raw, dict):
        for subtitle, subraw in raw.items():
            insert_field(page_id, f"{title}.{subtitle}" if title else subtitle, subraw, con, coded, list_name, item_no)
        return
    if isinstance(raw, list):
        if list_name:
            raise ValueError(f"{page_id}: a list in an item of list {list_name}")
        for item_no, item in enumerate(raw):
            insert_field(page_id, "", item, con, False, title, item_no)
        return
    con.exec_driver_sql("INSERT INTO fields(page_id, list_name, item_no, field_title, text_raw, decoded_value) VALUES(?, ?, ?, ?, ?, ?)",
                        (page_id, list_name, item_no, title, raw, decode(title, raw) if coded else None))

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

#grouping problems become flags, on the field a problem is about (its level's number field) if the page has it, else on any of
#its collection's levels' number fields it has
def insert_flags(review_p, con, keys):
    if not review_p.is_file():
        return
    for entry in json.loads(review_p.read_text(encoding="utf-8")):
        if entry.get("step") != "group":
            continue
        page_id = Path(entry["file"]).stem
        field = con.exec_driver_sql(f"""SELECT field_title FROM fields WHERE page_id = ? AND list_name = ''
            ORDER BY field_title IS NOT ?, field_title NOT IN ({', '.join('?' * len(keys))}), rowid LIMIT 1""",
                                    (page_id, entry.get("field"), *keys)).fetchone()
        if field is not None: #a blank page isn't in the db
            con.exec_driver_sql("""INSERT INTO flags(page_id, field_title, kind, reason)
                VALUES(?, ?, 'inconsistency', ?)""", (page_id, field[0], "Grouping: " + entry["reason"].split(": ", 1)[-1]))


#the first version of kind with this text's hash (a prompt: of this series); None if no version has it
def version_id(con, kind, sha, collection_id=None):
    return sha and con.exec_driver_sql("SELECT MIN(version_id) FROM instruction_versions WHERE kind = ? AND sha256 = ?"
                                       " AND collection_id IS ?", (kind, sha, collection_id if kind == "prompt" else None)).scalar()

#the series an item belongs to, by its number (its PDF's folder, or its folder of page images) in {item number: series};
#None: no series lists it
def series_of(owners, path):
    path = PurePosixPath(str(path).replace("\\", "/"))
    return owners.get(path.parent.name if path.suffix.lower() == ".pdf" else path.name)

#{item number: series} for every item a series lists: its archive items, and the items uploaded to it
def archive_owners(db):
    return {**{str(node): series for node, series in db.query(models.ArchiveItem.node, models.ArchiveItem.collection_id)},
            **{bundle: series for bundle, series in db.query(models.UploadedItem.bundle, models.UploadedItem.collection_id)}}

#the series a run's item is loaded into: the one it was run for, else the one that lists it; a ValueError if none does
def series(con, data):
    if data.get("collection"):
        return data["collection"]
    owners = dict(con.exec_driver_sql("SELECT CAST(node AS TEXT), collection_id FROM archive_items"
                                      " UNION ALL SELECT bundle, collection_id FROM uploaded_items").fetchall())
    found = series_of(owners, data["input"])
    if found is None:
        raise ValueError(f"No series lists {data['input']}: add it to one from the app first.")
    return found

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