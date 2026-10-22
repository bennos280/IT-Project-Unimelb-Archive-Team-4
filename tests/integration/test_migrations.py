"""The migrations build exactly the tables in backend/db/models.py, so the real db and the tests' db are the same; a later
migration keeps the reviewers' edits, the db is backed up before it runs, and one that breaks a link is undone; 002 gives each
series its own prompt."""
import json
import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from backend.db import database, models

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
        for sql in ["INSERT INTO collections(collection_id, name) VALUES(1, 'c')",
                    "INSERT INTO page_types(collection_id, name, label) VALUES(1, 'main', 'Main')",
                    "INSERT INTO bundles(bundle_id, source_pdf, collection_id) VALUES('b', 'b.pdf', 1)",
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


def test_a_fresh_db_is_at_revision_002_with_every_table_of_the_models_and_no_rows(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)
    db = tmp_path / "test.db"
    assert rows(db, "SELECT version_num FROM alembic_version") == [("002",)]
    tables = {name for (name,) in rows(db, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(models.Base.metadata.tables) <= tables
    assert all(rows(db, f"SELECT count(*) FROM {table}") == [(0,)] for table in models.Base.metadata.tables)


def db_at_001(tmp_path):
    """A db as revision 001 made it: instruction_versions without the column of 002, two series, and a page in each of them
    read with its prompt versions (series 2's with series 1's, one with none)."""
    path = tmp_path / "old.db"
    database.migrate(f"sqlite:///{path.as_posix()}")
    con = sqlite3.connect(path)
    con.executescript("""
        PRAGMA foreign_keys = OFF;
        CREATE TABLE old_versions (version_id INTEGER NOT NULL, kind VARCHAR NOT NULL, body TEXT NOT NULL, rules TEXT, sha256 VARCHAR NOT NULL,
            reviewer_id INTEGER, note TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, CONSTRAINT pk_instruction_versions PRIMARY KEY (version_id),
            CONSTRAINT fk_instruction_versions_reviewer_id_reviewers FOREIGN KEY(reviewer_id) REFERENCES reviewers (reviewer_id));
        DROP TABLE instruction_versions;
        ALTER TABLE old_versions RENAME TO instruction_versions;
        UPDATE alembic_version SET version_num = '001';
        INSERT INTO reviewers(reviewer_id, name) VALUES (1, 'Ben');
        INSERT INTO collections(collection_id, name) VALUES (1, 'Prest'), (2, 'Letters');
        INSERT INTO page_types(name, label, collection_id) VALUES ('main', 'Main', 1), ('letter', 'Letter', 2);
        INSERT INTO instruction_versions(version_id, kind, body, sha256, reviewer_id, note, created_at) VALUES
            (1, 'prompt', 'first', 'a', NULL, NULL, '2026-01-01 00:00:00'), (2, 'main', '{}', 'm', NULL, NULL, '2026-01-01 00:00:00'),
            (3, 'prompt', 'second', 'b', 1, 'longer', '2026-02-02 00:00:00');
        INSERT INTO bundles(bundle_id, source_pdf, collection_id) VALUES ('b1', 'b1.pdf', 1), ('b2', 'b2.pdf', 2);
        INSERT INTO pages(page_id, import_path, bundle_id, category, prompt_version_id) VALUES
            ('p1', 'p1.png', 'b1', 'main', 1), ('p2', 'p2.png', 'b2', 'main', 1), ('p3', 'p3.png', 'b2', 'main', 3),
            ('p4', 'p4.png', 'b2', 'main', NULL);
    """)
    con.commit()
    con.close()
    return path


def test_each_series_gets_the_prompts_a_db_had_series_1_keeping_its_ids_and_pages(tmp_path):
    path = db_at_001(tmp_path)
    database.migrate(f"sqlite:///{path.as_posix()}")
    assert rows(path, "SELECT version_num FROM alembic_version") == [("002",)]
    assert rows(path, "SELECT version_id, collection_id, body, sha256, reviewer_id, note, created_at FROM instruction_versions"
                      " WHERE kind = 'prompt' ORDER BY version_id") == [
        (1, 1, "first", "a", None, None, "2026-01-01 00:00:00"), (3, 1, "second", "b", 1, "longer", "2026-02-02 00:00:00"),
        (4, 2, "first", "a", None, None, "2026-01-01 00:00:00"), (5, 2, "second", "b", 1, "longer", "2026-02-02 00:00:00")]
    assert rows(path, "SELECT collection_id FROM instruction_versions WHERE kind = 'main'") == [(None,)]  # a template is a page type's
    assert rows(path, "SELECT page_id, prompt_version_id FROM pages ORDER BY page_id") == [("p1", 1), ("p2", 4), ("p3", 5), ("p4", None)]
    assert rows(tmp_path / "old-backup-001.db", "SELECT count(*) FROM pages WHERE prompt_version_id = 1") == [(2,)]  # backed up first
    command.check(database.alembic_config(f"sqlite:///{path.as_posix()}"))  # and it is the models' table


def test_a_db_with_no_prompt_gets_none_from_the_migration(tmp_path):
    path = db_at_001(tmp_path)
    sqlite3.connect(path).executescript("PRAGMA foreign_keys = OFF; UPDATE pages SET prompt_version_id = NULL;"
                                        " DELETE FROM instruction_versions WHERE kind = 'prompt'")
    database.migrate(f"sqlite:///{path.as_posix()}")
    assert rows(path, "SELECT kind, collection_id FROM instruction_versions") == [("main", None)]
