"""The transcription prompt and templates as versions in the db (backend/db/instructions.py and /instructions): a save is
a new version, the newest is used, and a template is checked so it can't break loading, grouping or the review screen."""
import json

import pytest

from backend.db import instructions, models
from backend.pipeline.transcribe.transcribe import read_texts
from tests.unit.test_backend_api import add_in_order

TEXTS = read_texts()  # today's prompt.txt and templates


def main_with(**changes):
    """Today's main template with fields changed, added, or dropped (value "DROP")."""
    template = {**json.loads(TEXTS["main"]), **changes}
    return json.dumps({key: value for key, value in template.items() if value != "DROP"})


def test_todays_prompt_and_templates_pass_the_checks():
    assert {kind: instructions.problems(kind, body, TEXTS) for kind, body in TEXTS.items()} == {kind: [] for kind in TEXTS}


BROKEN = [
    ("main", "{not json", "main: not JSON"),
    ("main", "[]", "main: must be a JSON object of fields"),
    ("followup", "{}", "followup: needs at least one field"),
    ("main", main_with(number_of_dwelling="DROP"), "main: needs 'number_of_dwelling'"),
    ("notes", '{"annotations": [{"raw": null, "location": null}]}', "notes: needs 'text'"),
    ("main", main_with(model=None), "main: 'model' is filled in by the pipeline"),
    ("main", main_with(annotations=[{"raw": None}]), "main: 'annotations' must be"),
    ("main", main_with(residents={"age": None}), "main: 'residents' must be a list holding one object of null fields"),
    ("main", main_with(other_children={"died": []}), "main: 'other_children' must be"),
    ("main", main_with(**{"kitchen.shared": None}), "main: 'kitchen.shared': names are lower-case"),
    ("main", main_with(bath={"Location": None}), "main: 'bath.Location': names are lower-case"),
    ("main", main_with(address="5 Peel St."), "main: 'address' must be null"),
    ("main", main_with(rooms=[None]), "main: 'rooms' must be null"),
    ("main", main_with(extra={f"field_{n}": None for n in range(3000)}), "main: the prompt and template come to"),
]


@pytest.mark.parametrize("kind, body, problem", BROKEN, ids=[problem for _, _, problem in BROKEN])
def test_a_template_that_would_break_the_pipeline_or_the_review_screen_is_refused(kind, body, problem):
    assert any(found.startswith(problem) for found in instructions.problems(kind, body, TEXTS))


def test_an_empty_prompt_is_refused():
    assert instructions.problems("prompt", " \n", TEXTS) == ["The prompt is empty."]


@pytest.fixture
def seeded(db):
    """Version 1 of the prompt and each template, as migration 001 makes them, and a reviewer."""
    add_in_order(db, models.Reviewer(reviewer_id=1, name="Ben"),
                 *[models.InstructionVersion(kind=kind, body=body, sha256=instructions.sha256(body)) for kind, body in TEXTS.items()])
    db.commit()
    return db


def test_a_saved_template_becomes_the_newest_version_and_the_old_one_is_kept(client, seeded):
    current = client.get("/instructions").json()
    assert sorted(current) == ["coded", "main", "notes", "prompt"] and current["main"]["body"] == TEXTS["main"]
    body = main_with(tenure_notes=None)
    saved = client.post("/instructions/main", json={"body": body, "basedOn": current["main"]["id"], "reviewerId": 1,
                                                    "note": "tenure notes"})
    assert saved.status_code == 201
    assert (saved.json()["body"], saved.json()["reviewer"], saved.json()["note"]) == (body, "Ben", "tenure notes")
    assert client.get("/instructions").json()["main"]["id"] == saved.json()["id"]
    assert [v["body"] for v in client.get("/instructions/main").json()] == [body, TEXTS["main"]]  # newest first
    assert instructions.texts(seeded)["main"] == body  # what the next job reads with


def test_a_save_is_refused_when_unknown_unchanged_invalid_or_based_on_an_old_version(client, seeded):
    main_id = client.get("/instructions").json()["main"]["id"]

    def save(kind="main", **changes):
        return client.post(f"/instructions/{kind}", json={"body": main_with(tenure_notes=None), "basedOn": main_id,
                                                          "reviewerId": 1, **changes})

    assert save(kind="letters").status_code == 404
    assert save(reviewerId=9).status_code == 400
    assert save(body=TEXTS["main"]).json()["detail"] == "Nothing changed."
    refused = save(body=main_with(number_of_dwelling="DROP"))
    assert (refused.status_code, refused.json()["detail"]) == (400, ["main: needs 'number_of_dwelling'"])
    assert save().status_code == 201
    assert save(body=main_with(occupation=None)).status_code == 409  # its basedOn is no longer the newest
    assert len(client.get("/instructions/main").json()) == 2
    assert client.get("/instructions/letters").status_code == 404


def test_accuracy_is_kept_apart_for_each_prompt_and_template_version(client, seeded):
    newest = instructions.newest(seeded)
    later = models.InstructionVersion(kind="main", body=main_with(occupation=None), sha256="later")
    for row in [later, models.Survey(survey_id="s", bundle_id="6789"),
                *[models.Page(page_id=page, survey_id="s", category="main", import_path="x.png", bundle_id="6789", model="opus",
                               effort="low", prompt_version_id=newest["prompt"].version_id, template_version_id=template)
                  for page, template in (("p1", newest["main"].version_id), ("p2", None))],
                *[models.Field(page_id=page, field_title="address", text_raw="5 Peel St.") for page in ("p1", "p2")]]:
        seeded.add(row)
        seeded.flush()  # in order: the db checks each row's links
    seeded.query(models.Page).filter_by(page_id="p2").update({"template_version_id": later.version_id})
    seeded.commit()
    for page in ("p1", "p2"):
        client.post("/reviews/s", json={"reviews": {page: {}}, "revisions": {page: 1}})
    assert [(row["promptVersion"], row["templateVersion"], row["pages"]) for row in client.get("/accuracy").json()] == [
        (newest["prompt"].version_id, newest["main"].version_id, 1), (newest["prompt"].version_id, later.version_id, 1)]


def test_a_prompt_saved_with_only_its_line_endings_changed_is_no_change(client, seeded):
    prompt = client.get("/instructions").json()["prompt"]
    saved = client.post("/instructions/prompt", json={"body": prompt["body"].replace("\r\n", "\n"), "basedOn": prompt["id"],
                                                      "reviewerId": 1})
    assert saved.json()["detail"] == "Nothing changed."  # a browser sends a textarea back with plain line endings
