"""Alembic runs the migrations in versions/ through this, on backend/db/prestcribe.db unless given another url."""
from pathlib import Path

from alembic import context
from alembic.migration import MigrationContext

from backend.db import models  # noqa: F401  (registers the tables)
from backend.db.database import SQLALCHEMY_DATABASE_URL, Base, make_engine


#refuses a migration that leaves rows pointing at nothing
def links_intact(ctx, step, heads, run_args):
    if broken := ctx.connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError(f"this migration leaves rows pointing at nothing: {broken[:5]}")


url = context.config.get_main_option("sqlalchemy.url") or SQLALCHEMY_DATABASE_URL
engine = make_engine(url)
try:
    with engine.connect() as connection:
        #back the db up before migrating it
        current = MigrationContext.configure(connection).get_current_revision()
        if current not in (None, context.get_head_revision()):
            db = Path(connection.engine.url.database)
            backup = db.with_name(f"{db.stem}-backup-{current}.db")
            if not backup.exists():
                connection.exec_driver_sql("VACUUM INTO ?", (str(backup),))
        #foreign keys off (only possible outside a transaction), or copying a table deletes the rows pointing at it
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        #render_as_batch: SQLite changes a table by copying it
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True,
                          on_version_apply=links_intact)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()  #lets go of the db file, so it can be moved or deleted once migrated
