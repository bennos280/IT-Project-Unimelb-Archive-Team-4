"""The migrations build exactly the tables in backend/db/models.py, so the real db and the tests' db are the same; a later
migration keeps the reviewers' edits, the db is backed up before it runs, and one that breaks a link is undone."""
import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from backend.db import database

# a later migration, on top of the real ones
LATER = '''
from alembic import op
revision, down_revision, branch_labels, depends_on = "later", {head!r}, None, None
def upgrade():
{body}
'''


@pytest.fixture
def url(tmp_path):
    """A db made by the migrations, holding one field and a reviewer's edit of it."""
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)
    with database.make_engine(url).begin() as db:
        for sql in ["INSERT INTO bundles(bundle_id, source_pdf) VALUES('b', 'b.pdf')",
                    "INSERT INTO pages(page_id, import_path, bundle_id, category) VALUES('p', 'p.png', 'b', 'main')",
                    "INSERT INTO fields(page_id, field_title, text_raw) VALUES('p', 'address', '5 Peel St.')",
                    "INSERT INTO edits(edit_text, page_id, field_title) VALUES('6 Peel St.', 'p', 'address')"]:
            db.exec_driver_sql(sql)
    return url


def migrate_with_later(url, body, tmp_path, monkeypatch):
    """Applies a later migration doing `body`; returns the revision the db was at before it."""
    config = database.alembic_config(url)
    head = ScriptDirectory.from_config(config).get_current_head()
    (tmp_path / "versions").mkdir()
    (tmp_path / "versions" / "later.py").write_text(LATER.format(head=head, body=body))
    real = Path(database.__file__).parent / "migrations" / "versions"
    config.set_main_option("version_locations", os.pathsep.join([str(real), str(tmp_path / "versions")]))
    monkeypatch.setattr(database, "alembic_config", lambda url: config)
    database.migrate(url)
    return head


def rows(db, sql):
    return sqlite3.connect(db).execute(sql).fetchall()


def test_migrations_match_the_models(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)
    command.check(database.alembic_config(url))  # raises if models.py has a change no migration makes yet


def test_a_table_change_keeps_the_edits_on_it_and_backs_the_db_up_first(url, tmp_path, monkeypatch):
    # changing a column of fields: SQLite can't, so the table is copied to a new one and the old dropped
    head = migrate_with_later(url, '    with op.batch_alter_table("fields", recreate="always"):\n        pass',
                              tmp_path, monkeypatch)
    assert rows(tmp_path / "test.db", "SELECT edit_text FROM edits") == [("6 Peel St.",)]
    assert rows(tmp_path / f"test-backup-{head}.db", "SELECT edit_text FROM edits") == [("6 Peel St.",)]


def test_a_migration_that_breaks_a_link_is_undone(url, tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="pointing at nothing"):
        migrate_with_later(url, '    op.execute("DELETE FROM bundles")', tmp_path, monkeypatch)
    assert rows(tmp_path / "test.db", "SELECT bundle_id FROM bundles") == [("b",)]
    assert rows(tmp_path / "test.db", "SELECT version_num FROM alembic_version") != [("later",)]


def test_version_1_of_the_prompt_and_templates_is_the_files_byte_for_byte(url):
    """So the transcripts already made from the files are reused, not read (and paid for) again."""
    from backend.pipeline.run import digest
    from backend.pipeline.transcribe.transcribe import HERE
    files = {"prompt": HERE / "prompt.txt", **{path.stem: path for path in sorted((HERE / "templates").glob("*.json"))}}
    with database.make_engine(url).connect() as db:
        rows = db.exec_driver_sql("SELECT kind, body, sha256 FROM instruction_versions ORDER BY version_id").fetchall()
    assert [kind for kind, _, _ in rows] == list(files)
    assert all(body.encode("utf-8") == files[kind].read_bytes() and sha == digest(files[kind]) for kind, body, sha in rows)


def test_a_db_at_004_has_no_saved_choice_so_a_command_line_run_exits(url, tmp_path, monkeypatch):
    """The committed db before 005: no app_settings table yet, so the choice reads as not set, not as a crash."""
    from sqlalchemy.orm import sessionmaker
    from backend.db import app_settings
    command.downgrade(database.alembic_config(url), "004")
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=database.make_engine(url)))
    with pytest.raises(SystemExit, match="Choose a transcription model on the Settings page first."):
        app_settings.saved_choice_or_exit()


def test_005_adds_the_app_settings_table_and_keeps_the_rows_already_there(url, tmp_path):
    """The committed db at 004 gets the table on the next start; the reviewers' edits stay."""
    config = database.alembic_config(url)
    command.downgrade(config, "004")
    assert rows(tmp_path / "test.db", "SELECT name FROM sqlite_master WHERE name = 'app_settings'") == []
    database.migrate(url)
    assert [r[1:3] + r[5:] for r in rows(tmp_path / "test.db", "PRAGMA table_info(app_settings)")] == [("key", "VARCHAR", 1), ("value", "VARCHAR", 0), ("updated_at", "DATETIME", 0)]
    assert rows(tmp_path / "test.db", "SELECT edit_text FROM edits") == [("6 Peel St.",)]
    with database.make_engine(url).begin() as db:
        db.exec_driver_sql("INSERT INTO app_settings(key, value) VALUES('transcription.model', 'opus')")
    assert rows(tmp_path / "test.db", "SELECT value, updated_at IS NOT NULL FROM app_settings") == [("opus", 1)]


def test_006_adds_the_area_and_region_columns_and_saves_only_the_changed_instructions_as_new_versions(url, tmp_path):
    """A db at 005 has the old prompt and main template as its newest versions: they get a newer version from today's files,
    once. The coded and notes templates already match the files, so they get none; a fresh db (seeded from the files) gets none."""
    from backend.pipeline.run import digest
    from backend.pipeline.transcribe.transcribe import HERE
    db = tmp_path / "test.db"
    versions = "SELECT kind, note FROM instruction_versions ORDER BY version_id"
    assert [kind for kind, _ in rows(db, versions)] == ["prompt", "coded", "main", "notes"]  # fresh: just version 1 of each
    config = database.alembic_config(url)
    command.downgrade(config, "005")
    assert not {"area", "region"} & {r[1] for r in rows(db, "PRAGMA table_info(annotations)")}
    with database.make_engine(url).begin() as con:
        con.exec_driver_sql("UPDATE instruction_versions SET body = 'old ' || kind, sha256 = 'old' WHERE kind IN ('prompt', 'main')")
        con.exec_driver_sql("INSERT INTO annotations(page_id, annotation_no, text_raw, location) VALUES('p', 0, '*', 'top-left')")
    database.migrate(url)
    assert [r[1:3] for r in rows(db, "PRAGMA table_info(annotations)")][-2:] == [("area", "VARCHAR"), ("region", "VARCHAR")]
    assert rows(db, "SELECT text_raw, location, area, region FROM annotations") == [("*", "top-left", None, None)]
    assert rows(db, "SELECT edit_text FROM edits") == [("6 Peel St.",)]
    assert [kind for kind, _ in rows(db, versions)] == ["prompt", "coded", "main", "notes", "prompt", "main"]
    for kind, body, sha in rows(db, "SELECT kind, body, sha256 FROM instruction_versions ORDER BY version_id DESC LIMIT 2"):
        path = HERE / "prompt.txt" if kind == "prompt" else HERE / "templates" / f"{kind}.json"
        assert body.encode("utf-8") == path.read_bytes() and sha == digest(path)
    command.downgrade(config, "005")  # drops the columns and leaves the versions
    assert not {"area", "region"} & {r[1] for r in rows(db, "PRAGMA table_info(annotations)")} and len(rows(db, versions)) == 6
    database.migrate(url)
    assert len(rows(db, versions)) == 6  # the newest versions already match the files
