"""Archive items: each item of a collection's archive series, by its page on the archive (/nodes/view/<node>), with its
catalogue identifier and title as the archive lists them; the Wilfred Prest Survey's 45 items are put in."""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None

PREST_ITEMS = [
    (216412, "UMA-ITE-1973000200001", "Box Hill 00"),
    (216413, "UMA-ITE-1973000200002", "Brighton 01 - Part 1"),
    (216414, "UMA-ITE-1973000200003", "Brighton 01 - Part 2"),
    (216415, "UMA-ITE-1973000200004", "Brunswick 02 - Part 1"),
    (216416, "UMA-ITE-1973000200005", "Brunswick 02 - Part 2"),
    (216417, "UMA-ITE-1973000200006", "Brunswick 02 - Part 3"),
    (216418, "UMA-ITE-1973000200007", "Camberwell 03 - Part 1"),
    (216419, "UMA-ITE-1973000200008", "Camberwell 03 - Part 2"),
    (216420, "UMA-ITE-1973000200009", "Caulfield 04"),
    (216421, "UMA-ITE-1973000200010", "Chelsea 05"),
    (216422, "UMA-ITE-1973000200011", "Coburg 06 - Part 1"),
    (216423, "UMA-ITE-1973000200012", "Coburg 06 - Part 2"),
    (216424, "UMA-ITE-1973000200013", "Collingwood 07"),
    (216425, "UMA-ITE-1973000200014", "Essendon 08 - Part 1"),
    (216426, "UMA-ITE-1973000200015", "Essendon 08 - Part 2"),
    (216427, "UMA-ITE-1973000200016", "Essendon 08 - Part 3"),
    (216428, "UMA-ITE-1973000200017", "Prest survey- Fitzroy"),
    (216429, "UMA-ITE-1973000200018", "Prest survey- North Fitzroy"),
    (216431, "UMA-ITE-1973000200020", "Rise in income- Footscray"),
    (216433, "UMA-ITE-1973000200022", "Hawthorn 11"),
    (216434, "UMA-ITE-1973000200023", "Heidelberg 12"),
    (216435, "UMA-ITE-1973000200024", "Kew 13"),
    (216436, "UMA-ITE-1973000200025", "Malvern 14"),
    (216437, "UMA-ITE-1973000200026", "Melbourne 15"),
    (216438, "UMA-ITE-1973000200027", "Moorabbin 16"),
    (216439, "UMA-ITE-1973000200028", "Northcote 18 - Part 1"),
    (216440, "UMA-ITE-1973000200029", "Northcote 18 - Part 2"),
    (216441, "UMA-ITE-1973000200030", "Oakleigh 19"),
    (216442, "UMA-ITE-1973000200031", "Port Melbourne 20"),
    (216443, "UMA-ITE-1973000200032", "Prahran 21 - Part 1"),
    (216444, "UMA-ITE-1973000200033", "Prahran 21 - Part 2"),
    (216445, "UMA-ITE-1973000200034", "Prahran 21 - Part 3"),
    (216446, "UMA-ITE-1973000200035", "Prahran 21 - Part 4"),
    (216447, "UMA-ITE-1973000200036", "Preston 22"),
    (216448, "UMA-ITE-1973000200037", "Sandringham 24"),
    (216449, "UMA-ITE-1973000200038", "Richmond 23"),
    (216450, "UMA-ITE-1973000200039", "South Melbourne 25 - Part 1"),
    (216451, "UMA-ITE-1973000200040", "South Melbourne 25 - Part 2"),
    (216452, "UMA-ITE-1973000200041", "St Kilda 26 - Part 1"),
    (216453, "UMA-ITE-1973000200042", "St Kilda 26 - Part 2"),
    (216454, "UMA-ITE-1973000200043", "Braybrook 28, Maribyrnong, Sunshine"),
    (216459, "UMA-ITE-1973000200048", "Williamstown"),
    (216460, "UMA-ITE-1973000200049", "Williamstown 27"),
    (216461, "UMA-ITE-1973000200050", "Shared houses Prahran"),
    (216463, "UMA-ITE-1973000200052", "Shared houses St Kilda"),
]

def upgrade():
    items = op.create_table("archive_items",
                            sa.Column("node", sa.Integer(), nullable=False),
                            sa.Column("collection_id", sa.Integer(), nullable=False),
                            sa.Column("identifier", sa.String(), nullable=False),
                            sa.Column("title", sa.String(), nullable=False),
                            sa.ForeignKeyConstraint(["collection_id"], ["collections.collection_id"],
                                                    name=op.f("fk_archive_items_collection_id_collections")),
                            sa.PrimaryKeyConstraint("node", name=op.f("pk_archive_items")))
    prest = op.get_bind().execute(sa.text("SELECT collection_id FROM collections WHERE archive_series = 499420")).scalar()
    if prest is not None:
        op.bulk_insert(items, [{"node": node, "collection_id": prest, "identifier": identifier, "title": title}
                               for node, identifier, title in PREST_ITEMS])

def downgrade():
    op.drop_table("archive_items")
