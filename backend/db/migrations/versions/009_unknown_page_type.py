"""Each collection has one Unknown page type, where a page sorting couldn't place waits, unread, for a reviewer to pick its type.
Prest's is other, relabelled Unknown; the code knew it by its name before."""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("page_types") as b:
        b.add_column(sa.Column("unknown", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE page_types SET unknown = 1, label = 'Unknown' WHERE name = 'other'")
    op.create_index("uq_page_types_unknown", "page_types", ["collection_id"], unique=True, sqlite_where=sa.text("unknown"))

def downgrade():
    op.drop_index("uq_page_types_unknown", "page_types")
    op.execute("UPDATE page_types SET label = 'Other page' WHERE name = 'other'")
    with op.batch_alter_table("page_types") as b:
        b.drop_column("unknown")
