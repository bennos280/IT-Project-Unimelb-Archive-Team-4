"""A record can sit inside another, a record of the level above (a folder's letter in the folder); the records so far are all
at the top."""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("surveys") as b:
        b.add_column(sa.Column("parent_id", sa.String(), nullable=True))
        b.create_foreign_key("fk_surveys_parent_id_surveys", "surveys", ["parent_id"], ["survey_id"], ondelete="CASCADE")

def downgrade():  #a record's pages stay with it; its place inside another goes
    with op.batch_alter_table("surveys") as b:
        b.drop_constraint("fk_surveys_parent_id_surveys", type_="foreignkey")
        b.drop_column("parent_id")
