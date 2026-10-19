"""A template version keeps its fields' rules (backend/db/checks.py), and a value that breaks one is flagged (kind invalid)."""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("instruction_versions") as b:
        b.add_column(sa.Column("rules", sa.Text(), nullable=True))
    with op.batch_alter_table("flags") as b:
        b.drop_constraint(op.f("ck_flags_kind"), type_="check")
        b.create_check_constraint(op.f("ck_flags_kind"), "kind IN ('inconsistency', 'gibberish', 'uncertain', 'invalid')")

def downgrade():
    op.execute("DELETE FROM flags WHERE kind = 'invalid'")
    with op.batch_alter_table("flags") as b:
        b.drop_constraint(op.f("ck_flags_kind"), type_="check")
        b.create_check_constraint(op.f("ck_flags_kind"), "kind IN ('inconsistency', 'gibberish', 'uncertain')")
    with op.batch_alter_table("instruction_versions") as b:
        b.drop_column("rules")
