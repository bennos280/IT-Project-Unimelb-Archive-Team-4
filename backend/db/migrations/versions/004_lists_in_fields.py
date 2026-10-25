"""A value in a list on a page is a row of fields, with its list's name and item number, so a series' templates can have lists
of any name: a Prest card's residents become list "residents" and its other children lists "other_children.died" and
"other_children.living_elsewhere" (one value per child, field_title ""). The tables residents, resident_fields and
other_children go; edits and flags point at a value by page, list, item and field, keeping their ids."""
import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

VALUE = ["page_id", "list_name", "item_no", "field_title"]


def value_columns():
    return [sa.Column("page_id", sa.String(), nullable=False),
            sa.Column("list_name", sa.String(), server_default="", nullable=False),
            sa.Column("item_no", sa.Integer(), server_default="0", nullable=False)]


def upgrade():
    #001 makes the tables of the models as they are now, so a db made since then has them already
    if "resident_fields" not in sa.inspect(op.get_bind()).get_table_names():
        return
    for table in ("fields_new", "flags_new", "edits_new"):  #left by a run of this that stopped part way
        op.execute(f"DROP TABLE IF EXISTS {table}")

    op.create_table("fields_new", *value_columns(),
                    sa.Column("field_title", sa.String(), nullable=False),
                    sa.Column("text_raw", sa.Text(), nullable=True),
                    sa.Column("decoded_value", sa.Text(), nullable=True),
                    sa.ForeignKeyConstraint(["page_id"], ["pages.page_id"], name=op.f("fk_fields_page_id_pages"), ondelete="CASCADE"),
                    sa.PrimaryKeyConstraint(*VALUE, name=op.f("pk_fields")))
    op.execute("INSERT INTO fields_new(page_id, list_name, item_no, field_title, text_raw, decoded_value)"
               " SELECT page_id, '', 0, field_title, text_raw, decoded_value FROM fields")
    op.execute("INSERT INTO fields_new(page_id, list_name, item_no, field_title, text_raw)"
               " SELECT page_id, 'residents', resident_no, resident_field_title, text_raw FROM resident_fields")
    op.execute("INSERT INTO fields_new(page_id, list_name, item_no, field_title, text_raw)"
               " SELECT page_id, 'other_children.' || residence, child_no, '', text_raw FROM other_children")

    op.create_table("flags_new",
                    sa.Column("flag_id", sa.Integer(), nullable=False), *value_columns(),
                    sa.Column("field_title", sa.String(), nullable=False),
                    sa.Column("kind", sa.String(), nullable=False),
                    sa.Column("reason", sa.Text(), nullable=False),
                    sa.CheckConstraint("kind IN ('inconsistency', 'gibberish', 'uncertain', 'invalid', 'check')", name=op.f("ck_flags_kind")),
                    sa.ForeignKeyConstraint(VALUE, [f"fields.{c}" for c in VALUE], name=op.f("fk_flags_page_id_fields"), ondelete="CASCADE"),
                    sa.PrimaryKeyConstraint("flag_id", name=op.f("pk_flags")))
    op.execute("INSERT INTO flags_new(flag_id, page_id, field_title, kind, reason) SELECT flag_id, page_id, field_title, kind, reason FROM flags")

    op.create_table("edits_new",
                    sa.Column("edit_id", sa.Integer(), nullable=False),
                    sa.Column("edit_text", sa.Text(), nullable=True),
                    sa.Column("reviewer_id", sa.Integer(), nullable=True),
                    sa.Column("time", sa.DateTime(), nullable=True), *value_columns(),
                    sa.Column("field_title", sa.String(), nullable=True),
                    sa.Column("annotation_no", sa.Integer(), nullable=True),
                    sa.CheckConstraint("(field_title IS NOT NULL) + (annotation_no IS NOT NULL) = 1"
                                       " AND (annotation_no IS NULL OR (list_name = '' AND item_no = 0))", name=op.f("ck_edits_exclusivity")),
                    sa.ForeignKeyConstraint(VALUE, [f"fields.{c}" for c in VALUE], name=op.f("fk_edits_page_id_fields"), ondelete="CASCADE"),
                    sa.ForeignKeyConstraint(["page_id", "annotation_no"], ["annotations.page_id", "annotations.annotation_no"],
                                            name=op.f("fk_edits_page_id_annotations"), ondelete="CASCADE"),
                    sa.ForeignKeyConstraint(["reviewer_id"], ["reviewers.reviewer_id"], name=op.f("fk_edits_reviewer_id_reviewers")),
                    sa.PrimaryKeyConstraint("edit_id", name=op.f("pk_edits")))
    op.execute("""INSERT INTO edits_new(edit_id, edit_text, reviewer_id, time, page_id, list_name, item_no, field_title, annotation_no)
        SELECT edit_id, edit_text, reviewer_id, time, page_id,
               CASE WHEN resident_no IS NOT NULL THEN 'residents' WHEN child_no IS NOT NULL THEN 'other_children.' || child_residence ELSE '' END,
               COALESCE(resident_no, child_no, 0),
               CASE WHEN resident_no IS NOT NULL THEN resident_field_title WHEN child_no IS NOT NULL THEN '' ELSE field_title END,
               annotation_no
        FROM edits""")

    for table in ("edits", "flags", "resident_fields", "residents", "other_children", "fields"):
        op.drop_table(table)
    for table in ("fields", "flags", "edits"):
        op.rename_table(f"{table}_new", table)
    op.create_index("ix_edits_page_field", "edits", VALUE)


def downgrade():
    #ponytail: no way back here; migrating backs the db up first (prestcribe-backup-003.db), which is the old db
    raise NotImplementedError("Restore the backup made before migrating to 004.")
