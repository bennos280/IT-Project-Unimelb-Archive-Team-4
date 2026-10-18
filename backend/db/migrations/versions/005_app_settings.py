"""Settings edited in the app, such as the transcription defaults."""
from alembic import op
import sqlalchemy as sa
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("app_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()))

def downgrade():
    op.drop_table("app_settings")
