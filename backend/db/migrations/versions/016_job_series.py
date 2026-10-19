"""A job can add a series' items from the archive (kind items): it names the series and, when it adds only a search's
results, the search."""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("jobs") as b:
        b.add_column(sa.Column("collection_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("search", sa.String(), nullable=True))
        b.create_foreign_key(op.f("fk_jobs_collection_id_collections"), "collections", ["collection_id"], ["collection_id"])
        b.drop_constraint(op.f("ck_jobs_kind"), type_="check")
        b.create_check_constraint(op.f("ck_jobs_kind"), "kind IN ('bundle', 'page', 'train', 'items')")

def downgrade():
    op.execute("DELETE FROM jobs WHERE kind = 'items'")
    with op.batch_alter_table("jobs") as b:
        b.drop_constraint(op.f("ck_jobs_kind"), type_="check")
        b.create_check_constraint(op.f("ck_jobs_kind"), "kind IN ('bundle', 'page', 'train')")
        b.drop_constraint(op.f("fk_jobs_collection_id_collections"), type_="foreignkey")
        b.drop_column("search")
        b.drop_column("collection_id")
