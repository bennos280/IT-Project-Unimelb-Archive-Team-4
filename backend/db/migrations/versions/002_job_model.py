"""Remember the transcription settings selected for each bundle job."""
from alembic import op
import sqlalchemy as sa
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

def upgrade():
    for name in ("transcription_model", "transcription_provider", "transcription_effort"):
        op.add_column("jobs", sa.Column(name, sa.String(), nullable=True))

def downgrade():
    with op.batch_alter_table("jobs") as batch:
        for name in ("transcription_model", "transcription_provider", "transcription_effort"):
            batch.drop_column(name)
