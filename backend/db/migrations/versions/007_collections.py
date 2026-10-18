"""Collections: a collection owns its bundles and page types; the Wilfred Prest Survey is collection 1 and holds everything so far."""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("collections",
                    sa.Column("collection_id", sa.Integer(), nullable=False),
                    sa.Column("name", sa.String(), nullable=False),
                    sa.PrimaryKeyConstraint("collection_id", name=op.f("pk_collections")),
                    sa.UniqueConstraint("name", name=op.f("uq_collections_name")))
    op.bulk_insert(sa.table("collections", sa.column("collection_id", sa.Integer), sa.column("name", sa.String)),
                   [{"collection_id": 1, "name": "Wilfred Prest Survey"}])
    for table in ("bundles", "page_types"):
        with op.batch_alter_table(table) as b:
            b.add_column(sa.Column("collection_id", sa.Integer(), nullable=False, server_default="1"))
            b.create_foreign_key(op.f(f"fk_{table}_collection_id_collections"), "collections", ["collection_id"], ["collection_id"])

def downgrade():
    for table in ("bundles", "page_types"):
        with op.batch_alter_table(table) as b:
            b.drop_constraint(op.f(f"fk_{table}_collection_id_collections"), type_="foreignkey")
            b.drop_column("collection_id")
    op.drop_table("collections")
