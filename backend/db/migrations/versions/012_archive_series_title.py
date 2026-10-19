"""A collection keeps its archive series' catalogue identifier, title and number of items, as the archive showed them when it
was linked, so lists can describe the series without asking the archive; the Wilfred Prest Survey's are UMA-SR-000000842,
its forms, and 45 items."""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("collections") as b:
        b.add_column(sa.Column("archive_identifier", sa.String(), nullable=True))
        b.add_column(sa.Column("archive_title", sa.String(), nullable=True))
        b.add_column(sa.Column("archive_items", sa.Integer(), nullable=True))
    op.execute("UPDATE collections SET archive_identifier = 'UMA-SR-000000842',"
               " archive_title = 'University of Melbourne Social Survey forms', archive_items = 45 WHERE archive_series = 499420")

def downgrade():
    with op.batch_alter_table("collections") as b:
        b.drop_column("archive_items")
        b.drop_column("archive_title")
        b.drop_column("archive_identifier")
