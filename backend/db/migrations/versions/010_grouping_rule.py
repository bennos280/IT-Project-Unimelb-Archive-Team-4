"""How a collection's pages group into surveys, which the code knew by Prest's names before: a page type can start a survey
or join the survey whose number it shows, and the collection names the field that holds that number."""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("collections") as b:
        b.add_column(sa.Column("record_key", sa.String(), nullable=True))
    with op.batch_alter_table("page_types") as b:
        b.add_column(sa.Column("starts_record", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("matched_by_key", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE collections SET record_key = 'number_of_dwelling' WHERE collection_id = 1")
    op.execute("UPDATE page_types SET starts_record = 1 WHERE name = 'main'")
    op.execute("UPDATE page_types SET matched_by_key = 1 WHERE name = 'coded'")

def downgrade():
    with op.batch_alter_table("page_types") as b:
        b.drop_column("matched_by_key")
        b.drop_column("starts_record")
    with op.batch_alter_table("collections") as b:
        b.drop_column("record_key")
