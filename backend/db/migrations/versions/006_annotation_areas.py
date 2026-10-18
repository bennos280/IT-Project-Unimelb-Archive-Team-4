"""Each annotation gets the named area of the card it is in, and a box of its own where the location is more exact; the prompt and templates that ask for it are saved as versions."""
import hashlib
from pathlib import Path

from alembic import op
import sqlalchemy as sa

TRANSCRIBE = Path(__file__).resolve().parents[3] / "pipeline" / "transcribe"
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("annotations", sa.Column("area", sa.String(), nullable=True))
    op.add_column("annotations", sa.Column("region", sa.String(), nullable=True)) #JSON {"x", "y", "width", "height"}
    #a file that differs from its kind's newest version is saved as a newer one; a fresh db was seeded from the files by 001
    files = {"prompt": TRANSCRIBE / "prompt.txt",
             **{kind: TRANSCRIBE / "templates" / f"{kind}.json" for kind in ("main", "coded", "notes")}}
    versions = sa.table("instruction_versions", sa.column("kind", sa.String), sa.column("body", sa.Text),
                        sa.column("sha256", sa.String), sa.column("note", sa.Text))
    for kind, path in files.items():
        newest = op.get_bind().execute(sa.text("SELECT body FROM instruction_versions WHERE kind = :kind"
                                               " ORDER BY version_id DESC LIMIT 1"), {"kind": kind}).scalar()
        if newest is not None and newest.replace("\r\n", "\n") != path.read_bytes().decode("utf-8").replace("\r\n", "\n"):
            op.bulk_insert(versions, [{"kind": kind, "body": path.read_bytes().decode("utf-8"),
                                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "note": "Annotation areas"}])

def downgrade():
    with op.batch_alter_table("annotations") as b:
        b.drop_column("region")
        b.drop_column("area")
