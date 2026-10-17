"""Separate classification from transcription and preserve replaced content."""
from alembic import op
import sqlalchemy as sa
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("pages", sa.Column("needs_transcription", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("jobs", sa.Column("base_revision", sa.Integer(), nullable=True))
    op.create_table("page_versions",
        sa.Column("version_id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.String(), sa.ForeignKey("pages.page_id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("reviewers.reviewer_id"), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=False, server_default=sa.func.now()))

def downgrade():
    op.drop_table("page_versions")
    with op.batch_alter_table("jobs") as b: b.drop_column("base_revision")
    with op.batch_alter_table("pages") as b: b.drop_column("needs_transcription")
