"""A series keeps its checks across fields as versions (backend/db/checks.py); a value failing one is flagged (kind check), and a
job checks a series' pages again (kind check)."""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("check_versions",
                    sa.Column("version_id", sa.Integer(), primary_key=True, autoincrement=True),
                    sa.Column("collection_id", sa.Integer(), sa.ForeignKey("collections.collection_id", name=op.f("fk_check_versions_collection_id_collections")), nullable=False),
                    sa.Column("body", sa.Text(), nullable=False),
                    sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("reviewers.reviewer_id", name=op.f("fk_check_versions_reviewer_id_reviewers")), nullable=True),
                    sa.Column("note", sa.Text(), nullable=True),
                    sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True))
    op.create_index("ix_edits_page_field", "edits", ["page_id", "field_title"])  #a field's newest edit, which the checks read
    with op.batch_alter_table("flags") as b:
        b.drop_constraint(op.f("ck_flags_kind"), type_="check")
        b.create_check_constraint(op.f("ck_flags_kind"), "kind IN ('inconsistency', 'gibberish', 'uncertain', 'invalid', 'check')")
    with op.batch_alter_table("jobs") as b:
        b.drop_constraint(op.f("ck_jobs_kind"), type_="check")
        b.create_check_constraint(op.f("ck_jobs_kind"), "kind IN ('bundle', 'page', 'train', 'items', 'check')")

def downgrade():
    op.execute("DELETE FROM flags WHERE kind = 'check'")
    op.execute("DELETE FROM jobs WHERE kind = 'check'")
    with op.batch_alter_table("jobs") as b:
        b.drop_constraint(op.f("ck_jobs_kind"), type_="check")
        b.create_check_constraint(op.f("ck_jobs_kind"), "kind IN ('bundle', 'page', 'train', 'items')")
    with op.batch_alter_table("flags") as b:
        b.drop_constraint(op.f("ck_flags_kind"), type_="check")
        b.create_check_constraint(op.f("ck_flags_kind"), "kind IN ('inconsistency', 'gibberish', 'uncertain', 'invalid')")
    op.drop_index("ix_edits_page_field", "edits")
    op.drop_table("check_versions")
