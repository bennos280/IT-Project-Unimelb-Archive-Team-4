"""The Prest survey's validation (US6) as rules and checks: its coded card's codebook (backend/db/data_dict.json) becomes that page
type's field rules, and its five checks across the main form and the coded card become the series' first checks. US6's own flags go:
the series' Check again flags what fails these."""
import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None

NOTE = "The Prest survey's checks, from its validation (US6)"
ROOM_COUNTS = {"total_number_of_rooms", "number_of_bedrooms", "number_of_living_rooms"}
CHECKS = [
    {"id": "dwelling_number", "kind": "compare", "left": ["main.number_of_dwelling"], "op": "=", "right": ["coded.number_of_dwelling"]},
    {"id": "municipality", "kind": "compare", "left": ["main.municipality"], "op": "names", "right": ["coded.municipality"]},
    {"id": "industry_code", "kind": "compare", "left": ["main.industry_of_head_code"], "op": "=", "right": ["coded.industry_of_head"], "as": "codes"},
    {"id": "occupation_code", "kind": "compare", "left": ["main.occupation_of_head_code"], "op": "=", "right": ["coded.occupation_of_head"], "as": "codes"},
    {"id": "children_living_plus_dead", "kind": "compare", "op": "=",
     "left": ["coded.children_of_head_or_wife_living", "coded.children_of_head_or_wife_dead"], "right": ["coded.children_of_head_or_wife_total"]},
]


def rules(codebook, fields):
    """The coded card's fields' rules from its codebook, for the fields its template has: a field with codes is one of them (a
    room count 0 to 11, 0 meaning over 11; whether used as bedrooms may be 0, none), a whole count from 0; its number isn't checked."""
    found = {}
    for name, spec in codebook.items():
        values = spec["possible_values"]
        if name not in fields or name == "number_of_dwelling":
            continue
        if name in ROOM_COUNTS:
            found[name] = {"type": "one_of", "values": ["0 = Over 11", "1-11 = Rooms"]}
        elif isinstance(values, dict):
            found[name] = {"type": "one_of", "values": [f"{code} = {meaning}" for code, meaning in values.items()]
                           + (["0 = None used as a bedroom"] if name == "whether_used_as_bedrooms" else [])}
        elif str(spec["data_type"]).upper() == "INTEGER":
            found[name] = {"type": "number", "min": "0"}
    return found


def leaves(template, parent=None):
    for key, value in template.items():
        path = f"{parent}.{key}" if parent else key
        if isinstance(value, dict):
            yield from leaves(value, path)
        elif not isinstance(value, list):
            yield path


#the newest coded template version, and its rules from the codebook; None without one
def seeded(con):
    coded = con.execute(sa.text("SELECT version_id, body FROM instruction_versions WHERE kind = 'coded' ORDER BY version_id DESC")).first()
    if not coded:
        return None
    codebook = json.loads((Path(__file__).parents[2] / "data_dict.json").read_text(encoding="utf-8"))["pages"]["3"]["fields"]
    return coded.version_id, json.dumps(rules(codebook, set(leaves(json.loads(coded.body)))))


def upgrade():  #only where nobody has set rules or checks yet
    con = op.get_bind()
    if found := seeded(con):
        con.execute(sa.text("UPDATE instruction_versions SET rules = :rules WHERE version_id = :id AND rules IS NULL"),
                    {"id": found[0], "rules": found[1]})
    if (con.execute(sa.text("SELECT 1 FROM collections WHERE collection_id = 1")).first()
            and not con.execute(sa.text("SELECT 1 FROM check_versions WHERE collection_id = 1")).first()):
        con.execute(sa.text("INSERT INTO check_versions (collection_id, body, note) VALUES (1, :body, :note)"),
                    {"body": json.dumps(CHECKS), "note": NOTE})
    con.execute(sa.text("DELETE FROM flags WHERE kind = 'inconsistency' AND reason LIKE 'Consistency: %'"))


def downgrade():  #what these rules and checks flagged goes with them; US6's flags aren't brought back: its code is gone
    con = op.get_bind()
    if con.execute(sa.text("DELETE FROM check_versions WHERE collection_id = 1 AND note = :note"), {"note": NOTE}).rowcount:
        con.execute(sa.text("DELETE FROM flags WHERE kind = 'check' AND page_id IN"
                            " (SELECT page_id FROM pages JOIN bundles USING (bundle_id) WHERE collection_id = 1)"))
    if (found := seeded(con)) and con.execute(sa.text("UPDATE instruction_versions SET rules = NULL WHERE kind = 'coded' AND rules = :rules"),
                                              {"rules": found[1]}).rowcount:
        con.execute(sa.text("DELETE FROM flags WHERE kind = 'invalid' AND page_id IN (SELECT page_id FROM pages WHERE category = 'coded')"))
