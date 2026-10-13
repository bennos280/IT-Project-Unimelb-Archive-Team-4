"""Record reviewer moves between surveys."""
from alembic import op
import sqlalchemy as sa
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("page_moves",
        sa.Column("move_id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.String(), sa.ForeignKey("pages.page_id"), nullable=False),
        sa.Column("from_survey", sa.String(), nullable=True),
        sa.Column("to_survey", sa.String(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("reviewers.reviewer_id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=False, server_default=sa.func.now()))

def downgrade():
    op.drop_table("page_moves")
