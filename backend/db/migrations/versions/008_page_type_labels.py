"""Page types get a label, what people see, unique within a collection; their name stays the id that pages, jobs and templates use."""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

LABELS = {"main": "Main page", "notes": "Notes page", "coded": "Coded page", "other": "Other page"} #as the review screen named them

def upgrade():
    with op.batch_alter_table("page_types") as b:
        b.add_column(sa.Column("label", sa.String(), nullable=True))
    op.execute("UPDATE page_types SET label = name")
    for name, label in LABELS.items():
        op.execute(sa.text("UPDATE page_types SET label = :label WHERE name = :name").bindparams(label=label, name=name))
    with op.batch_alter_table("page_types") as b:
        b.alter_column("label", existing_type=sa.String(), nullable=False)
        b.create_unique_constraint(op.f("uq_page_types_collection_id"), ["collection_id", "label"])

def downgrade():
    with op.batch_alter_table("page_types") as b:
        b.drop_constraint(op.f("uq_page_types_collection_id"), type_="unique")
        b.drop_column("label")
