"""The Setup tab's page types API: a new page type named from its label (POST /page-types) and a type's label (PATCH
/page-types/{name}); how pages group is the series' levels' (test_record_levels.py)."""
from backend.db import grouping, models
from tests.unit.test_backend_api import add_in_order


def setup(db):
    add_in_order(db, models.Reviewer(reviewer_id=1, name="Ben"),
                 models.InstructionVersion(kind="prompt", collection_id=1, body="Read it.", sha256="p"),
                 models.InstructionVersion(kind="main", body='{"number_of_dwelling": null, "address": null}', sha256="m"),
                 models.InstructionVersion(kind="coded", body='{"number_of_dwelling": null}', sha256="c"),
                 models.InstructionVersion(kind="notes", body='{"text": null}', sha256="n"))
    db.commit()


def test_a_new_page_type_is_named_from_its_label(client, db):
    setup(db)

    def add(label):
        return client.post("/page-types", json={"label": label, "reviewerId": 1})

    assert add("Follow-up visit").json()["name"] == "follow_up_visit"
    assert add("Follow-up  Visit!").json()["name"] == "follow_up_visit_2"  # another label, the same name: numbered
    assert add("2nd letter").json()["name"] == "type_2nd_letter"  # a name starts with a letter
    assert add("Blank").json()["name"] == "blank_2"  # blank is what page sorting answers
    assert add("  ").status_code == 400


def test_a_page_types_label_changes_and_must_be_its_series_own(client, db):
    setup(db)

    def patch(name, **body):
        return client.patch(f"/page-types/{name}", json=body)

    assert patch("notes", label="Main page").status_code == 409
    assert patch("notes", label=" ").json()["detail"] == "A page type's label can't be empty."
    assert patch("missing", label="x").status_code == 404
    changed = patch("notes", label=" Interviewer notes ").json()
    assert (changed["label"], "startsRecord" in changed) == ("Interviewer notes", False)
