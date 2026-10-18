"""The Page types screen's API: a new page type named from its label (POST /page-types), a type's label and how it groups
(PATCH /page-types/{name}), and the collection's survey number field (/collections/{id})."""
from backend.db import grouping, models
from tests.unit.test_backend_api import add_in_order


def setup(db):
    add_in_order(db, models.Reviewer(reviewer_id=1, name="Ben"),
                 models.InstructionVersion(kind="prompt", body="Read it.", sha256="p"),
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


def test_a_page_types_label_and_grouping_change_within_the_rules(client, db):
    setup(db)

    def patch(name, **body):
        return client.patch(f"/page-types/{name}", json=body)

    assert patch("notes", startsRecord=True).json()["detail"] == "Add the survey number field 'number_of_dwelling' to its template first."
    assert patch("other", matchedByKey=True).json()["detail"] == "Unknown pages aren't read, so they can't start or join a survey."
    assert patch("coded", startsRecord=True).json()["detail"] == "A page type starts a survey or joins one by number, not both."
    assert patch("notes", label="Main page").status_code == 409
    assert patch("notes", label=" ").status_code == 400
    assert patch("missing", label="x").status_code == 404
    changed = patch("notes", label="Interviewer notes").json()
    assert (changed["label"], changed["startsRecord"], changed["matchedByKey"]) == ("Interviewer notes", False, False)
    # a type with no template yet can start surveys; its first template then needs the number field
    client.post("/page-types", json={"label": "Letter", "reviewerId": 1})
    assert patch("letter", startsRecord=True).json()["startsRecord"] is True
    refused = client.post("/instructions/letter", json={"body": '{"text": null}', "basedOn": None, "reviewerId": 1})
    assert refused.json()["detail"] == ["letter: needs 'number_of_dwelling'"]
    assert grouping.rule(db, 1)["starts"] == {"main", "letter"}


def test_the_survey_number_field_must_be_in_the_templates_that_group_by_it(client, db):
    setup(db)
    assert client.get("/collections/1").json()["recordKey"] == "number_of_dwelling"
    refused = client.patch("/collections/1", json={"recordKey": "address"})
    assert (refused.status_code, refused.json()["detail"]) == (400, "These page types' templates don't have 'address': Coded page.")
    assert client.patch("/collections/1", json={"recordKey": "Bad key"}).status_code == 400
    assert client.patch("/collections/1", json={"recordKey": ""}).json()["recordKey"] is None  # page order only
    assert client.get("/collections/9").status_code == 404
