"""Models' answers are kept in the db (saved_answers), so a PrestCribe file carries them."""
import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

def upgrade():
    #001 makes the tables of the models as they are now, so a db made since then has it already
    if "saved_answers" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table("saved_answers",
                        sa.Column("key", sa.String(), nullable=False),
                        sa.Column("answer", sa.Text(), nullable=False),
                        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
                        sa.PrimaryKeyConstraint("key", name=op.f("pk_saved_answers")))


def downgrade():
    op.drop_table("saved_answers")
