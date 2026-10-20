"""The migrations build exactly the tables in backend/db/models.py, so the real db and the tests' db are the same; a later
migration keeps the reviewers' edits, the db is backed up before it runs, and one that breaks a link is undone."""
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
                    "INSERT INTO page_types(name) VALUES('main')",
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


def test_a_fresh_db_is_at_revision_001_with_every_table_of_the_models_and_no_rows(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)
    db = tmp_path / "test.db"
    assert rows(db, "SELECT version_num FROM alembic_version") == [("001",)]
    tables = {name for (name,) in rows(db, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(models.Base.metadata.tables) <= tables
    assert all(rows(db, f"SELECT count(*) FROM {table}") == [(0,)] for table in models.Base.metadata.tables)
