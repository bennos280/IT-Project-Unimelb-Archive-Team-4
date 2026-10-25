"""loader.py puts a pipeline run (manifest.json + transcripts) into the database, pages in their surveys."""
import json
import sqlite3

import pytest
import sqlalchemy.exc

from backend.db import database, loader


def run_folder(tmp_path):
    """A run as the pipeline writes it: a main form, a page identify wasn't sure about and a coded card in one survey,
    a page in no survey, a blank page, and grouping's problem with the survey."""
    out = tmp_path / "output" / "216412"
    (out / "transcribe").mkdir(parents=True)
    meta = {"engine": "claude", "model": "claude-haiku-4-5-20251001+claude-opus-5-5", "effort": "low", "seconds": 1.0}  # as older runs say it
    transcripts = {
        "216412_00001": {"address": "5 Raeburn Cres.", "number_of_dwelling": "3",
                         "residents": [{"relationship": "Head"}, {"relationship": "Wife"}],
                         "other_children": {"died": ["girl 2"], "living_elsewhere": ["son 20", "son 18"]}},
        "216412_00002": {"type_of_family": "1", "normal_household_income": "350", "washouse": "1", "weekly_rent": "1[?]"},
        "216412_00003": {"text": "notes before the first main form"},
    }
    for stem, answer in transcripts.items():
        (out / "transcribe" / f"{stem}.json").write_text(json.dumps({**answer, **meta}), encoding="utf-8")
    pages = [("216412_00001", "main", "216412-3"), ("216412_00002", "coded", "216412-3"), ("216412_00003", "notes", None)]
    manifest = {"input": "216412/216412.pdf", "pages": [
        {"file": f"{stem}.png", "path": str(out / "pages" / f"{stem}.png"), "label": label,
         "transcript": f"transcribe\\{stem}.json", "survey": survey} for stem, label, survey in pages]
        + [{"file": "216412_00004.png", "path": str(out / "pages" / "216412_00004.png"), "label": "blank", "survey": "216412-3"},
           {"file": "216412_00005.png", "path": str(out / "pages" / "216412_00005.png"), "label": "review", "survey": "216412-3"}],
        "transcripts": {f"{stem}.png": {"request": {"model": "opus"}} for stem, _, _ in pages}}  #the model the run was given
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (out / "review.json").write_text(json.dumps([
        {"file": "216412_00005.png", "step": "identify", "reason": "unlike any known page type"},
        {"file": "216412_00001.png", "step": "group", "reason": "survey 216412-3: 2 coded cards"}]), encoding="utf-8")
    return out


def start_db(tmp_path, monkeypatch):
    """A new database holding the Prest series (its page types and record level) listing item 216412, as the app is set up."""
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)
    with database.make_engine(url).begin() as con:
        con.exec_driver_sql("INSERT INTO collections (collection_id, name) VALUES (1, 'Wilfred Prest Survey')")
        for name in ("main", "notes", "coded", "other"):
            con.exec_driver_sql("INSERT INTO page_types (name, label, collection_id, unknown) VALUES (?, ?, 1, ?)", (name, name, name == "other"))
        con.exec_driver_sql("INSERT INTO record_levels (collection_id, position, name, record_key, parts) VALUES"
                            " (1, 1, 'survey', 'number_of_dwelling', '[]')")
        con.exec_driver_sql("INSERT INTO archive_items (node, collection_id, identifier, title, pdf) VALUES"
                            " (216412, 1, 'UMA-ITE-216412', 'Item 216412', '216412/216412.pdf')")
    monkeypatch.setattr(database, "engine", database.make_engine(url))
    return url


def test_run_loads_into_its_surveys(tmp_path, monkeypatch):
    start_db(tmp_path, monkeypatch)
    manifest = run_folder(tmp_path) / "manifest.json"
    loader.dump_into_db(manifest)
    loader.dump_into_db(manifest)  # a bundle already in the db is left as it is

    db = sqlite3.connect(tmp_path / "test.db")
    assert db.execute("SELECT bundle_id FROM bundles").fetchall() == [("216412",)]
    assert db.execute("SELECT survey_id, bundle_id FROM surveys").fetchall() == [("216412-3", "216412")]
    assert db.execute("SELECT page_id, survey_id, category FROM pages ORDER BY page_id").fetchall() == [
        ("216412_00001", "216412-3", "main"), ("216412_00002", "216412-3", "coded"), ("216412_00003", None, "notes"),
        ("216412_00005", "216412-3", "other")]
    assert db.execute("SELECT field_title, text_raw FROM fields WHERE page_id = '216412_00005'").fetchall() == [("text", None)]
    assert db.execute("SELECT DISTINCT provider, model FROM pages WHERE model IS NOT NULL").fetchall() == [("claude", "claude-opus-5-5")]
    assert db.execute("SELECT * FROM fields WHERE field_title = 'engine'").fetchall() == []  # not mistaken for a field
    # a list's items are numbered from 0: objects' values each under their title, text with no title
    assert db.execute("SELECT list_name, item_no, field_title, text_raw FROM fields WHERE list_name != ''"
                      " ORDER BY list_name, item_no").fetchall() == [
        ("other_children.died", 0, "", "girl 2"), ("other_children.living_elsewhere", 0, "", "son 20"),
        ("other_children.living_elsewhere", 1, "", "son 18"), ("residents", 0, "relationship", "Head"),
        ("residents", 1, "relationship", "Wife")]
    assert db.execute("SELECT page_id, field_title, kind, reason FROM flags").fetchall() == [
        ("216412_00001", "number_of_dwelling", "inconsistency", "Grouping: 2 coded cards")]
    assert dict(db.execute("SELECT field_title, decoded_value FROM fields WHERE page_id = '216412_00002'").fetchall()) == {
        "type_of_family": "Complete simple family", "normal_household_income": "Exact amount in shillings",
        "washouse": "In separate laundry", "weekly_rent": None}



def test_a_run_loads_its_records_inside_one_another_parents_first(tmp_path, monkeypatch):
    start_db(tmp_path, monkeypatch)
    out = run_folder(tmp_path)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["records"] = [{"id": "216412-3", "parent": None}, {"id": "216412-3-n1", "parent": "216412-3"}]
    manifest["pages"][1]["survey"] = "216412-3-n1"  # the coded card in a record inside the survey
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (out / "review.json").write_text(json.dumps([{"file": "216412_00002.png", "step": "group", "reason": "card 216412-3-n1: no 'washouse'",
                                                  "field": "washouse"}]), encoding="utf-8")
    loader.dump_into_db(out / "manifest.json")
    db = sqlite3.connect(tmp_path / "test.db")
    assert db.execute("SELECT survey_id, parent_id FROM surveys ORDER BY survey_id").fetchall() == [
        ("216412-3", None), ("216412-3-n1", "216412-3")]
    assert db.execute("SELECT page_id, survey_id FROM pages WHERE page_id IN ('216412_00001', '216412_00002') ORDER BY page_id").fetchall() == [
        ("216412_00001", "216412-3"), ("216412_00002", "216412-3-n1")]
    assert db.execute("SELECT page_id, field_title FROM flags").fetchall() == [("216412_00002", "washouse")]  # the field it's about

def test_a_run_loads_into_the_series_its_manifest_names_reading_nothing_into_a_type_that_series_lacks(tmp_path, monkeypatch):
    start_db(tmp_path, monkeypatch)
    with sqlite3.connect(tmp_path / "test.db") as con:
        con.execute("INSERT INTO collections (collection_id, name) VALUES (2, 'Letters')")
        con.execute("INSERT INTO page_types (name, label, collection_id, unknown) VALUES ('unknown_2', 'Unknown', 2, 1)")
    manifest = run_folder(tmp_path) / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest.write_text(json.dumps({**data, "collection": 2}), encoding="utf-8")
    loader.dump_into_db(manifest)
    db = sqlite3.connect(tmp_path / "test.db")
    assert db.execute("SELECT bundle_id, collection_id FROM bundles").fetchall() == [("216412", 2)]
    assert {category for (category,) in db.execute("SELECT category FROM pages")} == {"unknown_2"}
    assert db.execute("SELECT DISTINCT field_title FROM fields").fetchall() == [("text",)]  # an empty one each, to type into


def test_each_page_records_the_prompt_and_template_versions_that_read_it(tmp_path, monkeypatch):
    from backend.db.instructions import sha256
    from backend.pipeline.transcribe.transcribe import read_texts
    start_db(tmp_path, monkeypatch)
    out = run_folder(tmp_path)
    texts = read_texts()
    with database.engine.begin() as con:  # version 1 of the prompt and each template
        for kind in ("prompt", "main", "coded"):
            con.exec_driver_sql("INSERT INTO instruction_versions(kind, collection_id, body, sha256) VALUES(?, ?, ?, ?)",
                                (kind, 1 if kind == "prompt" else None, texts[kind], sha256(texts[kind])))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["transcripts"] = {  # what each page was read with, as the pipeline records it
        "216412_00001.png": {"request": {"prompt": sha256(texts["prompt"]), "template": sha256(texts["main"])}},
        "216412_00002.png": {"request": {"prompt": "the hash of a prompt in no version", "template": sha256(texts["coded"])}}}
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    loader.dump_into_db(out / "manifest.json")

    db = sqlite3.connect(tmp_path / "test.db")
    version = dict(db.execute("SELECT kind, version_id FROM instruction_versions"))
    assert db.execute("SELECT page_id, prompt_version_id, template_version_id FROM pages ORDER BY page_id").fetchall() == [
        ("216412_00001", version["prompt"], version["main"]), ("216412_00002", None, version["coded"]),
        ("216412_00003", None, None), ("216412_00005", None, None)]  # no record, or not read


def test_a_page_records_its_own_series_prompt_version_when_two_series_have_the_same_prompt(tmp_path, monkeypatch):
    from backend.db.instructions import sha256
    start_db(tmp_path, monkeypatch)
    prompt, template = "Read it.", '{"text": null}'
    with database.engine.begin() as con:
        con.exec_driver_sql("INSERT INTO collections (collection_id, name) VALUES (2, 'Letters')")
        con.exec_driver_sql("INSERT INTO page_types (name, label, collection_id, unknown) VALUES ('letter', 'Letter', 2, 0), ('unknown_2', 'Unknown', 2, 1)")
        for collection in (1, 2):  # series 2 starts as a copy of series 1's prompt
            con.exec_driver_sql("INSERT INTO instruction_versions(kind, collection_id, body, sha256) VALUES('prompt', ?, ?, ?)",
                                (collection, prompt, sha256(prompt)))
        con.exec_driver_sql("INSERT INTO instruction_versions(kind, body, sha256) VALUES('letter', ?, ?)", (template, sha256(template)))
    manifest_p = run_folder(tmp_path) / "manifest.json"
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    notes = next(page for page in manifest["pages"] if page["file"] == "216412_00003.png")
    manifest.update(collection=2, pages=[{**notes, "label": "letter"}],
                    transcripts={"216412_00003.png": {"request": {"prompt": sha256(prompt), "template": sha256(template)}}})
    manifest_p.write_text(json.dumps(manifest), encoding="utf-8")
    loader.dump_into_db(manifest_p)

    db = sqlite3.connect(tmp_path / "test.db")
    series_2 = db.execute("SELECT version_id FROM instruction_versions WHERE kind = 'prompt' AND collection_id = 2").fetchone()[0]
    assert db.execute("SELECT min(version_id) FROM instruction_versions WHERE kind = 'prompt'").fetchone()[0] != series_2  # not series 1's
    assert db.execute("SELECT prompt_version_id FROM pages").fetchall() == [(series_2,)]


def test_a_page_of_a_type_the_db_does_not_have_is_stored_as_other(tmp_path, monkeypatch):
    start_db(tmp_path, monkeypatch)
    out = run_folder(tmp_path)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["pages"][2]["label"] = "followup"  # read with a template, but no such page type here
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    loader.dump_into_db(out / "manifest.json")
    db = sqlite3.connect(tmp_path / "test.db")
    assert db.execute("SELECT category FROM pages WHERE page_id = '216412_00003'").fetchone() == ("other",)


def test_a_page_sorting_was_unsure_about_is_stored_as_the_collections_unknown_type(tmp_path, monkeypatch):
    url = start_db(tmp_path, monkeypatch)
    with database.make_engine(url).begin() as con:
        con.exec_driver_sql("UPDATE page_types SET unknown = 0")
        con.exec_driver_sql("INSERT INTO page_types(name, label, collection_id, unknown) VALUES('unsorted', 'Unsorted', 1, 1)")
    loader.dump_into_db(run_folder(tmp_path) / "manifest.json")
    db = sqlite3.connect(tmp_path / "test.db")
    assert db.execute("SELECT category FROM pages WHERE page_id = '216412_00005'").fetchone() == ("unsorted",)  # sorting said review


def test_a_collection_has_at_most_one_unknown_type_and_without_one_the_bundle_is_refused_by_name(tmp_path, monkeypatch):
    url = start_db(tmp_path, monkeypatch)
    with pytest.raises(sqlalchemy.exc.IntegrityError, match="UNIQUE"), database.make_engine(url).begin() as con:
        con.exec_driver_sql("INSERT INTO page_types(name, label, collection_id, unknown) VALUES('unsorted', 'Unsorted', 1, 1)")
    with database.make_engine(url).begin() as con:
        con.exec_driver_sql("UPDATE page_types SET unknown = 0")
    with pytest.raises(ValueError, match="216412's collection has no Unknown page type to store 216412_00005.png as"):
        loader.dump_into_db(run_folder(tmp_path) / "manifest.json")
    assert sqlite3.connect(tmp_path / "test.db").execute("SELECT COUNT(*) FROM bundles").fetchone() == (0,)  # all or nothing


def test_an_annotation_is_stored_with_its_area_when_the_page_type_has_it(tmp_path, monkeypatch):
    start_db(tmp_path, monkeypatch)
    out = run_folder(tmp_path)
    for stem, annotations in (("216412_00001", [{"raw": "R", "location": "right margin", "area": "right_margin"},
                                                {"raw": "/", "location": "by the kitchen", "area": "middle_column"},  # a coded card's area
                                                {"raw": "x", "location": "somewhere", "area": None},
                                                {"raw": "old", "location": "a transcript from before areas"}]),
                              ("216412_00002", [{"raw": "9", "location": "bottom-left", "area": "bottom_left"}])):
        path = out / "transcribe" / f"{stem}.json"
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "annotations": annotations}), encoding="utf-8")
    loader.dump_into_db(out / "manifest.json")
    db = sqlite3.connect(tmp_path / "test.db")
    assert db.execute("SELECT page_id, annotation_no, text_raw, area FROM annotations ORDER BY page_id, annotation_no").fetchall() == [
        ("216412_00001", 0, "R", "right_margin"), ("216412_00001", 1, "/", None), ("216412_00001", 2, "x", None),
        ("216412_00001", 3, "old", None), ("216412_00002", 0, "9", "bottom_left")]


def test_a_run_no_series_lists_is_refused_by_name(tmp_path, monkeypatch):
    start_db(tmp_path, monkeypatch)
    with sqlite3.connect(tmp_path / "test.db") as con:
        con.execute("DELETE FROM archive_items")
    with pytest.raises(ValueError, match="No series lists 216412/216412.pdf: add it to one from the app first."):
        loader.dump_into_db(run_folder(tmp_path) / "manifest.json")
    assert sqlite3.connect(tmp_path / "test.db").execute("SELECT COUNT(*) FROM bundles").fetchone() == (0,)


def test_a_run_of_an_item_uploaded_to_a_series_loads_into_it(tmp_path, monkeypatch):
    start_db(tmp_path, monkeypatch)
    with sqlite3.connect(tmp_path / "test.db") as con:
        con.execute("DELETE FROM archive_items")
        con.execute("INSERT INTO uploaded_items (bundle, collection_id) VALUES ('216412', 1)")
    loader.dump_into_db(run_folder(tmp_path) / "manifest.json")
    assert sqlite3.connect(tmp_path / "test.db").execute("SELECT collection_id FROM bundles").fetchall() == [(1,)]
