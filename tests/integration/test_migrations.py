"""The migrations build exactly the tables in backend/db/models.py, so the real db and the tests' db are the same; a later
migration keeps the reviewers' edits, the db is backed up before it runs, and one that breaks a link is undone; 002 gives each
series its own prompt, 003 a table of the models' saved answers, and 004 moves the values in lists on a page into fields."""
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


def test_a_fresh_db_is_at_revision_004_with_every_table_of_the_models_and_no_rows(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)
    db = tmp_path / "test.db"
    assert rows(db, "SELECT version_num FROM alembic_version") == [("004",)]
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
    assert rows(path, "SELECT version_num FROM alembic_version") == [("004",)]
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


def test_003_gives_a_db_without_saved_answers_the_table_and_keeps_its_rows(url, tmp_path):
    db = tmp_path / "test.db"
    sqlite3.connect(db).executescript("DROP TABLE saved_answers; UPDATE alembic_version SET version_num = '002';")
    database.migrate(url)
    assert rows(db, "SELECT version_num FROM alembic_version") == [("004",)]
    assert rows(db, "SELECT edit_text FROM edits") == [("6 Peel St.",)] and rows(db, "SELECT count(*) FROM saved_answers") == [(0,)]
    command.check(database.alembic_config(url))  # and it is the model's table


def db_at_003(tmp_path):
    """A db as revision 003 had it: residents, resident_fields and other_children as tables of their own, and a page with a field,
    two residents, a child on each list and an annotation, a flag, and an edit of each of them."""
    path = tmp_path / "old.db"
    database.migrate(f"sqlite:///{path.as_posix()}")
    con = sqlite3.connect(path)
    con.executescript("""
        PRAGMA foreign_keys = OFF;
        DROP TABLE edits; DROP TABLE flags; DROP TABLE fields; DROP INDEX IF EXISTS ix_edits_page_field;
        CREATE TABLE fields (page_id VARCHAR NOT NULL, field_title VARCHAR NOT NULL, text_raw TEXT, decoded_value TEXT,
            CONSTRAINT pk_fields PRIMARY KEY (page_id, field_title),
            CONSTRAINT fk_fields_page_id_pages FOREIGN KEY(page_id) REFERENCES pages (page_id) ON DELETE CASCADE);
        CREATE TABLE residents (page_id VARCHAR NOT NULL, resident_no INTEGER NOT NULL, CONSTRAINT pk_residents PRIMARY KEY (page_id, resident_no),
            CONSTRAINT fk_residents_page_id_pages FOREIGN KEY(page_id) REFERENCES pages (page_id) ON DELETE CASCADE);
        CREATE TABLE resident_fields (page_id VARCHAR NOT NULL, resident_no INTEGER NOT NULL, resident_field_title VARCHAR NOT NULL, text_raw VARCHAR,
            CONSTRAINT pk_resident_fields PRIMARY KEY (page_id, resident_no, resident_field_title),
            CONSTRAINT fk_resident_fields_page_id_residents FOREIGN KEY(page_id, resident_no) REFERENCES residents (page_id, resident_no) ON DELETE CASCADE);
        CREATE TABLE other_children (page_id VARCHAR NOT NULL, residence VARCHAR NOT NULL, child_no INTEGER NOT NULL, text_raw VARCHAR,
            CONSTRAINT pk_other_children PRIMARY KEY (page_id, residence, child_no),
            CONSTRAINT fk_other_children_page_id_pages FOREIGN KEY(page_id) REFERENCES pages (page_id) ON DELETE CASCADE);
        CREATE TABLE flags (flag_id INTEGER NOT NULL, page_id VARCHAR NOT NULL, field_title VARCHAR NOT NULL, kind VARCHAR NOT NULL, reason TEXT NOT NULL,
            CONSTRAINT pk_flags PRIMARY KEY (flag_id),
            CONSTRAINT fk_flags_page_id_fields FOREIGN KEY(page_id, field_title) REFERENCES fields (page_id, field_title) ON DELETE CASCADE);
        CREATE TABLE edits (edit_id INTEGER NOT NULL, edit_text TEXT, reviewer_id INTEGER, time DATETIME, page_id VARCHAR NOT NULL, field_title VARCHAR,
            resident_field_title VARCHAR, resident_no INTEGER, child_residence VARCHAR, child_no INTEGER, annotation_no INTEGER,
            CONSTRAINT pk_edits PRIMARY KEY (edit_id),
            CONSTRAINT fk_edits_page_id_fields FOREIGN KEY(page_id, field_title) REFERENCES fields (page_id, field_title) ON DELETE CASCADE,
            CONSTRAINT fk_edits_page_id_resident_fields FOREIGN KEY(page_id, resident_field_title, resident_no)
                REFERENCES resident_fields (page_id, resident_field_title, resident_no) ON DELETE CASCADE,
            CONSTRAINT fk_edits_page_id_other_children FOREIGN KEY(page_id, child_residence, child_no)
                REFERENCES other_children (page_id, residence, child_no) ON DELETE CASCADE,
            CONSTRAINT fk_edits_page_id_annotations FOREIGN KEY(page_id, annotation_no) REFERENCES annotations (page_id, annotation_no) ON DELETE CASCADE,
            CONSTRAINT fk_edits_reviewer_id_reviewers FOREIGN KEY(reviewer_id) REFERENCES reviewers (reviewer_id));
        CREATE INDEX ix_edits_page_field ON edits (page_id, field_title);
        UPDATE alembic_version SET version_num = '003';
        INSERT INTO reviewers(reviewer_id, name) VALUES (1, 'Ben');
        INSERT INTO collections(collection_id, name) VALUES (1, 'Prest');
        INSERT INTO page_types(name, label, collection_id) VALUES ('main', 'Main', 1);
        INSERT INTO bundles(bundle_id, source_pdf, collection_id) VALUES ('b', 'b.pdf', 1);
        INSERT INTO pages(page_id, import_path, bundle_id, category) VALUES ('p', 'p.png', 'b', 'main');
        INSERT INTO fields(page_id, field_title, text_raw, decoded_value) VALUES ('p', 'address', '5 Peel St.', NULL), ('p', 'age', '61', NULL);
        INSERT INTO residents(page_id, resident_no) VALUES ('p', 0), ('p', 1);
        INSERT INTO resident_fields(page_id, resident_no, resident_field_title, text_raw) VALUES ('p', 0, 'age', '43'), ('p', 1, 'age', '40');
        INSERT INTO other_children(page_id, residence, child_no, text_raw) VALUES ('p', 'died', 0, 'girl 2'), ('p', 'living_elsewhere', 0, 'son 20');
        INSERT INTO annotations(page_id, annotation_no, text_raw) VALUES ('p', 0, '*');
        INSERT INTO flags(flag_id, page_id, field_title, kind, reason) VALUES (7, 'p', 'address', 'check', 'odd');
        INSERT INTO edits(edit_id, edit_text, reviewer_id, page_id, field_title, resident_field_title, resident_no, child_residence, child_no, annotation_no)
            VALUES (3, '6 Peel St.', 1, 'p', 'address', NULL, NULL, NULL, NULL, NULL), (5, '44', 1, 'p', NULL, 'age', 1, NULL, NULL, NULL),
                   (8, 'girl 3', 1, 'p', NULL, NULL, NULL, 'died', 0, NULL), (9, 'x', 1, 'p', NULL, NULL, NULL, NULL, NULL, 0);
    """)
    con.commit()
    con.close()
    return path


def test_004_moves_residents_and_children_into_fields_keeping_every_edit_and_flag(tmp_path):
    path = db_at_003(tmp_path)
    url = f"sqlite:///{path.as_posix()}"
    database.migrate(url)
    assert rows(path, "SELECT version_num FROM alembic_version") == [("004",)]
    assert rows(path, "SELECT page_id, list_name, item_no, field_title, text_raw FROM fields ORDER BY rowid") == [
        ("p", "", 0, "address", "5 Peel St."), ("p", "", 0, "age", "61"), ("p", "residents", 0, "age", "43"),
        ("p", "residents", 1, "age", "40"), ("p", "other_children.died", 0, "", "girl 2"), ("p", "other_children.living_elsewhere", 0, "", "son 20")]
    assert rows(path, "SELECT edit_id, edit_text, list_name, item_no, field_title, annotation_no FROM edits ORDER BY edit_id") == [
        (3, "6 Peel St.", "", 0, "address", None), (5, "44", "residents", 1, "age", None),
        (8, "girl 3", "other_children.died", 0, "", None), (9, "x", "", 0, None, 0)]
    assert rows(path, "SELECT flag_id, list_name, item_no, field_title FROM flags") == [(7, "", 0, "address")]
    tables = {name for (name,) in rows(path, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not tables & {"residents", "resident_fields", "other_children", "fields_new", "flags_new", "edits_new"}
    assert rows(tmp_path / "old-backup-003.db", "SELECT count(*) FROM resident_fields") == [(2,)]  # backed up first
    command.check(database.alembic_config(url))  # and it is the models' tables
    # the links hold with foreign keys on: an edit needs its value, and clearing a page's values drops their edits and flags
    with database.make_engine(url).begin() as db:
        with pytest.raises(Exception, match="FOREIGN KEY"):
            with db.begin_nested():
                db.exec_driver_sql("INSERT INTO edits(edit_text, page_id, list_name, item_no, field_title) VALUES('?', 'p', 'residents', 5, 'age')")
        db.exec_driver_sql("DELETE FROM fields WHERE page_id = 'p'")
    assert rows(path, "SELECT edit_id FROM edits") == [(9,)] and rows(path, "SELECT count(*) FROM flags") == [(0,)]
