"""An archive item added to a series keeps where its PDF goes, <node>/<node>.pdf, so it can be listed and run before it is
downloaded (the Wilfred Prest Survey's are in backend/archive_pdfs.txt)."""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("archive_items") as b:
        b.add_column(sa.Column("pdf", sa.String(), nullable=True))

def downgrade():
    with op.batch_alter_table("archive_items") as b:
        b.drop_column("pdf")
