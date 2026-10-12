"""loader.py puts a pipeline run (manifest.json + transcripts) into the database, pages in their surveys."""
import json
import sqlite3

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
    manifest = {"input": "216412.pdf", "pages": [
        {"file": f"{stem}.png", "path": str(out / "pages" / f"{stem}.png"), "label": label,
         "transcript": f"transcribe\\{stem}.json", "survey": survey} for stem, label, survey in pages]
        + [{"file": "216412_00004.png", "path": str(out / "pages" / "216412_00004.png"), "label": "blank", "survey": "216412-3"},
           {"file": "216412_00005.png", "path": str(out / "pages" / "216412_00005.png"), "label": "review", "survey": "216412-3"}],
        "transcripts": {f"{stem}.png": {"request": {"model": "opus"}} for stem, _, _ in pages}}  #the model .env asked for
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (out / "review.json").write_text(json.dumps([
        {"file": "216412_00005.png", "step": "identify", "reason": "unlike any known page type"},
        {"file": "216412_00001.png", "step": "group", "reason": "survey 216412-3: 2 coded cards"}]), encoding="utf-8")
    return out


def test_run_loads_into_its_surveys(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)
    monkeypatch.setattr(database, "engine", database.make_engine(url))
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
    assert db.execute("SELECT resident_no, text_raw FROM resident_fields ORDER BY resident_no").fetchall() == [
        (0, "Head"), (1, "Wife")]
    assert db.execute("SELECT residence, child_no, text_raw FROM other_children ORDER BY residence, child_no").fetchall() == [
        ("died", 0, "girl 2"), ("living_elsewhere", 0, "son 20"), ("living_elsewhere", 1, "son 18")]
    assert db.execute("SELECT page_id, field_title, kind, reason FROM flags").fetchall() == [
        ("216412_00001", "number_of_dwelling", "inconsistency", "Grouping: 2 coded cards")]
    assert dict(db.execute("SELECT field_title, decoded_value FROM fields WHERE page_id = '216412_00002'").fetchall()) == {
        "type_of_family": "Complete simple family", "normal_household_income": "Exact amount in shillings",
        "washouse": "In separate laundry", "weekly_rent": None}


def test_each_page_records_the_prompt_and_template_versions_that_read_it(tmp_path, monkeypatch):
    from backend.db.instructions import sha256
    from backend.pipeline.transcribe.transcribe import read_texts
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)  # version 1 of the prompt and each template: today's files
    monkeypatch.setattr(database, "engine", database.make_engine(url))
    out = run_folder(tmp_path)
    texts = read_texts()
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


def test_a_page_of_a_type_the_db_does_not_have_is_stored_as_other(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)
    monkeypatch.setattr(database, "engine", database.make_engine(url))
    out = run_folder(tmp_path)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["pages"][2]["label"] = "followup"  # read with a template, but no such page type here
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    loader.dump_into_db(out / "manifest.json")
    db = sqlite3.connect(tmp_path / "test.db")
    assert db.execute("SELECT category FROM pages WHERE page_id = '216412_00003'").fetchone() == ("other",)
