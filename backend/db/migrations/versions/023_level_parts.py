"""A level of record says what one is made of, in order: each part a page type, how many of it one has, and how its pages are
found (one starts it, the next follow the page before them, or are matched by number wherever they were filed). A level from
before starts at its first starting page type (one or more: a second sheet of a form is the same record), then has any number
of its series' other read page types (its other starting ones among them: only one type starts a record), then exactly one of
each type matched by number; one with no starting type, each of whose pages was a record, is made of nothing, with no number
field."""
import json

from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("record_levels") as b:
        b.add_column(sa.Column("parts", sa.Text(), nullable=False, server_default="[]"))
    con = op.get_bind()
    for level_id, collection_id, starts, matched, key in con.execute(
            sa.text("SELECT level_id, collection_id, starts, matched, record_key FROM record_levels")).all():
        starts, matched = json.loads(starts), json.loads(matched)
        others = [name for (name,) in con.execute(sa.text("SELECT name FROM page_types WHERE collection_id = :c AND NOT unknown ORDER BY name"),
                                                  {"c": collection_id}) if name not in starts + matched]
        parts = [{"type": starts[0], "count": "one_or_more", "how": "starts"}] + [
            {"type": t, "count": "any", "how": "follows"} for t in starts[1:] + others] + [
            {"type": t, "count": "one", "how": "matched"} for t in matched] if starts else []
        con.execute(sa.text("UPDATE record_levels SET parts = :parts, record_key = :key WHERE level_id = :id"),
                    {"parts": json.dumps(parts), "key": key if starts else None, "id": level_id})
    with op.batch_alter_table("record_levels") as b:
        b.drop_column("starts")
        b.drop_column("matched")

def downgrade():  #what starts and is matched comes back; how many of each, and the order, go
    with op.batch_alter_table("record_levels") as b:
        b.add_column(sa.Column("starts", sa.Text(), nullable=False, server_default="[]"))
        b.add_column(sa.Column("matched", sa.Text(), nullable=False, server_default="[]"))
    con = op.get_bind()
    for level_id, parts in con.execute(sa.text("SELECT level_id, parts FROM record_levels")).all():
        parts = json.loads(parts)
        con.execute(sa.text("UPDATE record_levels SET starts = :s, matched = :m WHERE level_id = :id"),
                    {"s": json.dumps([p["type"] for p in parts if p["how"] == "starts"]),
                     "m": json.dumps([p["type"] for p in parts if p["how"] == "matched"]), "id": level_id})
    with op.batch_alter_table("record_levels") as b:
        b.drop_column("parts")
