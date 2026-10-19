"""A collection says what one of its records is called on screen (the Wilfred Prest Survey's are surveys; None: record)."""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("collections") as b:
        b.add_column(sa.Column("record_name", sa.String(), nullable=True))
    op.execute("UPDATE collections SET record_name = 'survey' WHERE collection_id = 1")

def downgrade():
    with op.batch_alter_table("collections") as b:
        b.drop_column("record_name")
