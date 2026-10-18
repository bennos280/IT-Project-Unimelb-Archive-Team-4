"""Each collection names its series on the University of Melbourne Archives' website (archives.library.unimelb.edu.au/nodes/view/<id>);
the Wilfred Prest Survey's is 499420 (UMA-SR-000000842)."""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("collections") as b:
        b.add_column(sa.Column("archive_series", sa.Integer(), nullable=True))
    op.execute("UPDATE collections SET archive_series = 499420 WHERE collection_id = 1")

def downgrade():
    with op.batch_alter_table("collections") as b:
        b.drop_column("archive_series")
