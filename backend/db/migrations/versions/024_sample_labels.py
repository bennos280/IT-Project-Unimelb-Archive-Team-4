"""Which page type a page of an item not yet read is, as said while its series was set up on it (a sample)."""
from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("sample_labels",
                    sa.Column("node", sa.Integer(), sa.ForeignKey("archive_items.node"), primary_key=True),
                    sa.Column("page", sa.Integer(), primary_key=True),
                    sa.Column("page_type", sa.String(), sa.ForeignKey("page_types.name"), nullable=False))

def downgrade():
    op.drop_table("sample_labels")
