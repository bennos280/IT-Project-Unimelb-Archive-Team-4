"""Each series has its own transcription prompt: instruction_versions.collection_id says whose a prompt is. The prompts a db
has now go to its first series, with their ids and history (pages keep pointing at them); every other series gets a copy of
each, and its pages point at the copy."""
import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

def upgrade():
    con = op.get_bind()
    #001 makes the tables of the models as they are now, so a db made since then has the column already
    if "collection_id" not in {column["name"] for column in sa.inspect(con).get_columns("instruction_versions")}:
        with op.batch_alter_table("instruction_versions") as table:
            table.add_column(sa.Column("collection_id", sa.Integer(), nullable=True))
            table.create_foreign_key("fk_instruction_versions_collection_id_collections", "collections", ["collection_id"], ["collection_id"])
    series = [c for (c,) in con.exec_driver_sql("SELECT collection_id FROM collections ORDER BY collection_id")]
    prompts = con.exec_driver_sql("SELECT version_id, body, sha256, reviewer_id, note, created_at FROM instruction_versions"
                                  " WHERE kind = 'prompt' AND collection_id IS NULL ORDER BY version_id").fetchall()
    if not series or not prompts:  #a db with no prompt gets none here: a new series is given one when it is made
        return
    first, others = series[0], series[1:]
    con.exec_driver_sql("UPDATE instruction_versions SET collection_id = ? WHERE kind = 'prompt' AND collection_id IS NULL", (first,))
    for collection in others:
        for old, *row in prompts:
            copy = con.exec_driver_sql("INSERT INTO instruction_versions(kind, collection_id, body, sha256, reviewer_id, note, created_at)"
                                       " VALUES('prompt', ?, ?, ?, ?, ?, ?)", (collection, *row)).lastrowid
            con.exec_driver_sql("UPDATE pages SET prompt_version_id = ? WHERE prompt_version_id = ? AND bundle_id IN"
                                " (SELECT bundle_id FROM bundles WHERE collection_id = ?)", (copy, old, collection))


def downgrade():
    #ponytail: the copies made for other series stay as extra prompt versions; the newest one is what the older code reads
    with op.batch_alter_table("instruction_versions") as table:
        table.drop_constraint("fk_instruction_versions_collection_id_collections", type_="foreignkey")
        table.drop_column("collection_id")
