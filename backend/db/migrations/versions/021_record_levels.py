"""A collection's records come in levels between its items and their pages, each with its own name and page types that start or
join one; a collection whose items held several records (the Wilfred Prest Survey) gets one level from its old settings, and
the rest none (each item one record). The old settings go, and with them the record name of a collection that had no level."""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("record_levels",
                    sa.Column("level_id", sa.Integer(), primary_key=True, autoincrement=True),
                    sa.Column("collection_id", sa.Integer(), sa.ForeignKey("collections.collection_id"), nullable=False),
                    sa.Column("position", sa.Integer(), nullable=False),
                    sa.Column("name", sa.String(), nullable=False),
                    sa.Column("starts", sa.Text(), nullable=False, server_default="[]"),
                    sa.Column("matched", sa.Text(), nullable=False, server_default="[]"),
                    sa.Column("record_key", sa.String(), nullable=True),
                    sa.UniqueConstraint("collection_id", "position", name="uq_record_levels_position"),
                    sa.UniqueConstraint("collection_id", "name", name="uq_record_levels_name"))
    types = "(SELECT json_group_array(name) FROM (SELECT name FROM page_types WHERE collection_id = c.collection_id AND {} ORDER BY name))"
    op.execute("INSERT INTO record_levels (collection_id, position, name, starts, matched, record_key)"
               f" SELECT c.collection_id, 1, COALESCE(c.record_name, 'record'), {types.format('starts_record')},"
               f" {types.format('matched_by_key')}, c.record_key FROM collections c WHERE c.group_pages")
    with op.batch_alter_table("collections") as b:
        for column in ("record_key", "record_name", "group_pages"):
            b.drop_column(column)
    with op.batch_alter_table("page_types") as b:
        b.drop_column("starts_record")
        b.drop_column("matched_by_key")

def downgrade():  #from each collection's top level; the names of collections with none don't come back
    with op.batch_alter_table("collections") as b:
        b.add_column(sa.Column("record_key", sa.String(), nullable=True))
        b.add_column(sa.Column("record_name", sa.String(), nullable=True))
        b.add_column(sa.Column("group_pages", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("page_types") as b:
        b.add_column(sa.Column("starts_record", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("matched_by_key", sa.Boolean(), nullable=False, server_default=sa.false()))
    top = "SELECT {} FROM record_levels l WHERE l.collection_id = collections.collection_id AND l.position = 1"
    name, key = top.format("NULLIF(l.name, 'record')"), top.format("l.record_key")
    op.execute(f"UPDATE collections SET group_pages = 1, record_name = ({name}), record_key = ({key}) WHERE EXISTS ({top.format('1')})")
    for column, role in (("starts_record", "starts"), ("matched_by_key", "matched")):
        op.execute(f"UPDATE page_types SET {column} = 1 WHERE name IN"
                   f" (SELECT j.value FROM record_levels l, json_each(l.{role}) j WHERE l.position = 1)")
    op.drop_table("record_levels")
