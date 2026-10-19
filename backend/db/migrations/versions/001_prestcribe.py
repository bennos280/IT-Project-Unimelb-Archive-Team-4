"""PrestCribe's first database: the tables in backend/db/models.py, and nothing in them. A series is added in the app, or opened
with its setup from a PrestCribe file (the Wilfred Prest Survey's is setups/wilfred-prest-survey.prestcribe). Earlier databases
started afresh at this one; what they held was exported to results/."""
from alembic import op

from backend.db import models

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    models.Base.metadata.create_all(op.get_bind())


def downgrade():
    models.Base.metadata.drop_all(op.get_bind())
