"""A collection's items are each one record, all their pages together, or hold several, grouped by its page types; one with a
page type that starts a record (the Wilfred Prest Survey) holds several."""
from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("collections") as b:
        b.add_column(sa.Column("group_pages", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE collections SET group_pages = 1 WHERE collection_id IN (SELECT collection_id FROM page_types WHERE starts_record)")

def downgrade():
    with op.batch_alter_table("collections") as b:
        b.drop_column("group_pages")
