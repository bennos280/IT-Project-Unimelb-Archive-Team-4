"""Each series' transcription prompt and each page type's template as versions in the db (backend/db/instructions.py,
/instructions and /collections/{id}/prompt): a save is a new version, the newest is used, and a version is checked so it can't
break loading, grouping or the review screen."""
import json

import pytest

from backend.db import instructions, models
from backend.pipeline.transcribe.transcribe import read_texts
from tests.unit.test_backend_api import add_in_order

TEXTS = read_texts()  # today's prompt.txt and templates
PREST = {"main": {"number_of_dwelling"}, "coded": {"number_of_dwelling"}}  # the field Prest's grouping reads, as migration 021 sets it


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
    ("main", main_with(model=None), "main: 'model' is filled in by the pipeline"),
    ("main", main_with(annotations=[{"raw": None}]), "main: 'annotations' must be"),
    ("main", main_with(annotations=[{"raw": None, "location": None}]), "main: 'annotations' must be"),  # no area
    ("coded", json.dumps({**json.loads(TEXTS["coded"]), "annotations": [{"raw": None, "location": None}]}), "coded: 'annotations' must be"),
    ("main", main_with(residents={"age": None}), "main: 'residents' must be a list holding one object of null fields"),
    ("main", main_with(other_children={"died": []}), "main: 'other_children' must be"),
    ("main", main_with(**{"kitchen.shared": None}), "main: 'kitchen.shared': names are lower-case"),
    ("main", main_with(bath={"Location": None}), "main: 'bath.Location': names are lower-case"),
    ("main", main_with(address=5), "main: 'address' must be null, its description, or an object of fields"),
    ("main", main_with(rooms=[None]), "main: 'rooms' must be null"),
    ("main", main_with(extra={f"field_{n}": None for n in range(3000)}), "main: the prompt and template come to"),
]


@pytest.mark.parametrize("kind, body, problem", BROKEN, ids=[problem for _, _, problem in BROKEN])
def test_a_template_that_would_break_the_pipeline_or_the_review_screen_is_refused(kind, body, problem):
    assert any(found.startswith(problem) for found in instructions.problems(kind, body, TEXTS, PREST))


def test_an_empty_prompt_is_refused():
    assert instructions.problems("prompt", " \n", TEXTS) == ["The prompt is empty."]


@pytest.fixture
def seeded(db):
    """Version 1 of series 1's prompt and of each template, and a reviewer."""
    add_in_order(db, models.Reviewer(reviewer_id=1, name="Ben"),
                 *[models.InstructionVersion(kind=kind, collection_id=1 if kind == "prompt" else None, body=body,
                                             sha256=instructions.sha256(body)) for kind, body in TEXTS.items()])
    db.commit()
    return db


@pytest.fixture
def two_series(seeded):
    """The seeded db with a second series: its own prompt, and a page type with a template."""
    for row in [models.Collection(collection_id=2, name="Ships"), models.PageType(name="ship", label="Ship", collection_id=2),
                models.InstructionVersion(kind="prompt", collection_id=2, body="Read the ship.", sha256=instructions.sha256("Read the ship.")),
                models.InstructionVersion(kind="ship", body='{"vessel": null}', sha256="s")]:
        seeded.add(row)
        seeded.flush()
    seeded.commit()
    return seeded


def test_a_saved_template_becomes_the_newest_version_and_the_old_one_is_kept(client, seeded):
    current = client.get("/instructions").json()
    assert sorted(current) == ["coded", "main", "notes"] and current["main"]["body"] == TEXTS["main"]  # templates only
    body = main_with(tenure_notes=None)
    saved = client.post("/instructions/main", json={"body": body, "basedOn": current["main"]["id"], "reviewerId": 1,
                                                    "note": "tenure notes"})
    assert saved.status_code == 201
    assert (saved.json()["body"], saved.json()["reviewer"], saved.json()["note"]) == (body, "Ben", "tenure notes")
    assert client.get("/instructions").json()["main"]["id"] == saved.json()["id"]
    assert [v["body"] for v in client.get("/instructions/main").json()] == [body, TEXTS["main"]]  # newest first
    assert instructions.texts(seeded, 1)["main"] == body  # what the next job reads with


def test_versions_are_numbered_within_their_kind_and_only_the_newest_is_current(client, seeded):
    main_id = client.get("/instructions").json()["main"]["id"]
    assert client.post("/instructions/main", json={"body": main_with(tenure_notes=None), "basedOn": main_id, "reviewerId": 1}).status_code == 201
    versions = client.get("/instruction-versions").json()
    assert [(v["kind"], v["number"], v["label"], v["current"]) for v in versions] == [
        ("prompt", 1, "Prompt", True), ("coded", 1, "Coded page", True), ("main", 1, "Main page", False), ("notes", 1, "Notes page", True),
        ("main", 2, "Main page", True)]  # oldest first
    assert [v["id"] for v in versions] == sorted(v["id"] for v in versions) and versions[0]["body"] == TEXTS["prompt"]
    assert [v["number"] for v in client.get("/instructions/main").json()] == [2, 1]  # newest first
    assert [v["number"] for v in client.get("/collections/1/prompt").json()] == [1]
    assert client.get("/instructions/prompt").status_code == 404  # a prompt belongs to a series, not to a page type


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
    newest = instructions.newest(seeded, 1)
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


def test_accuracy_can_be_limited_to_one_series(client, seeded):
    seeded.add(models.Collection(collection_id=2, name="Ships"))
    seeded.flush()
    for row in [models.Bundle(bundle_id="ship", source_pdf="ship.pdf", collection_id=2),
                models.Survey(survey_id="s", bundle_id="6789"), models.Survey(survey_id="t", bundle_id="ship"),
                models.Page(page_id="p1", survey_id="s", category="main", import_path="x.png", bundle_id="6789", model="opus", effort="low"),
                models.Page(page_id="p2", survey_id="t", category="main", import_path="x.png", bundle_id="ship", model="sonnet", effort="low"),
                *[models.Field(page_id=page, field_title="address", text_raw="5 Peel St.") for page in ("p1", "p2")]]:
        seeded.add(row)
        seeded.flush()  # in order: the db checks each row's links
    seeded.commit()
    for survey, page in (("s", "p1"), ("t", "p2")):
        client.post(f"/reviews/{survey}", json={"reviews": {page: {}}, "revisions": {page: 1}})

    def models_in(query=""):
        return [row["model"] for row in client.get(f"/accuracy{query}").json()]

    assert models_in("?collection=1") == ["opus"]
    assert models_in("?collection=2") == ["sonnet"]
    assert sorted(models_in()) == ["opus", "sonnet"]
    assert models_in("?collection=9") == []  # no such series: nothing, not an error


def test_a_prompt_saved_with_only_its_line_endings_changed_is_no_change(client, seeded):
    prompt = client.get("/collections/1/prompt").json()[0]
    saved = client.post("/collections/1/prompt", json={"body": prompt["body"].replace("\r\n", "\n"), "basedOn": prompt["id"],
                                                       "reviewerId": 1})
    assert saved.json()["detail"] == "Nothing changed."  # a browser sends a textarea back with plain line endings


def prompt_save(client, series, **changes):
    """Saves the series' newest prompt with ' More.' added, unless the request says otherwise."""
    newest = client.get(f"/collections/{series}/prompt").json()[0]
    return client.post(f"/collections/{series}/prompt", json={"body": newest["body"] + " More.", "basedOn": newest["id"], "reviewerId": 1,
                                                              **changes})


def test_each_series_has_its_own_prompt_history_and_a_save_changes_that_series_only(client, two_series):
    saved = prompt_save(client, 2, note="ships")
    assert saved.status_code == 201
    assert (saved.json()["number"], saved.json()["collectionId"], saved.json()["reviewer"], saved.json()["note"]) == (2, 2, "Ben", "ships")
    assert [(v["number"], v["body"]) for v in client.get("/collections/2/prompt").json()] == [(2, "Read the ship. More."), (1, "Read the ship.")]
    assert [(v["number"], v["body"]) for v in client.get("/collections/1/prompt").json()] == [(1, TEXTS["prompt"])]  # newest first
    assert instructions.texts(two_series, 2)["prompt"] == "Read the ship. More."
    assert instructions.texts(two_series, 1)["prompt"] == TEXTS["prompt"]
    assert prompt_save(client, 1).json()["number"] == 2  # series 1's second version, though series 2 has two


def test_a_series_is_read_with_its_own_prompt_and_page_types_templates_only(two_series):
    assert sorted(instructions.texts(two_series, 1)) == ["coded", "main", "notes", "prompt"]
    assert instructions.texts(two_series, 2) == {"prompt": "Read the ship.", "ship": '{"vessel": null}'}
    assert sorted(instructions.newest(two_series)) == ["coded", "main", "notes", "ship"]  # the templates of every series
    assert instructions.texts(two_series, 3) == {}  # a series with no prompt has none to read with: its jobs refuse to start


def test_a_prompt_save_is_refused_when_unknown_unchanged_invalid_or_based_on_an_old_version(client, two_series):
    assert client.get("/collections/9/prompt").status_code == 404
    assert client.post("/collections/9/prompt", json={"body": "x", "basedOn": None, "reviewerId": 1}).status_code == 404
    assert prompt_save(client, 2, reviewerId=9).status_code == 400
    assert prompt_save(client, 2, body="Read the ship.").json()["detail"] == "Nothing changed."
    assert prompt_save(client, 2, body=" \n").json()["detail"] == ["The prompt is empty."]
    too_long = prompt_save(client, 2, body="x" * 40_000)
    assert (too_long.status_code, too_long.json()["detail"][0].startswith("ship: the prompt and template come to")) == (400, True)
    first = client.get("/collections/2/prompt").json()[0]["id"]
    assert prompt_save(client, 2).status_code == 201
    stale = client.post("/collections/2/prompt", json={"body": "Another.", "basedOn": first, "reviewerId": 1})
    assert stale.status_code == 409  # the newest is no longer the one it started from
    other_series = client.get("/collections/1/prompt").json()[0]["id"]
    assert client.post("/collections/2/prompt", json={"body": "Another.", "basedOn": other_series, "reviewerId": 1}).status_code == 409
    assert [v["number"] for v in client.get("/collections/2/prompt").json()] == [2, 1]


def test_a_save_is_checked_with_its_own_series_only(client, two_series):
    two_series.query(models.InstructionVersion).filter_by(kind="main").update({"body": "{not json"})  # series 1's template is broken
    two_series.commit()
    refused = prompt_save(client, 1)
    assert (refused.status_code, refused.json()["detail"][0].startswith("main: not JSON")) == (400, True)
    assert prompt_save(client, 2, body="x" * 25_000).status_code == 201  # series 2's templates are fine, and this fits the ship one
    ship = client.get("/instructions").json()["ship"]
    template = json.dumps({"vessel": None, **{f"field_{n}": None for n in range(100)}})  # fits with series 1's prompt, not series 2's
    refused = client.post("/instructions/ship", json={"body": template, "basedOn": ship["id"], "reviewerId": 1})
    assert (refused.status_code, refused.json()["detail"][0].startswith("ship: the prompt and template come to")) == (400, True)
    assert instructions.problems("ship", template, {"prompt": TEXTS["prompt"]}) == []


def test_a_new_series_starts_with_the_general_prompt_and_series_1_is_left_as_it_was(client, seeded):
    from backend.pipeline.transcribe.transcribe import full_prompt, read_starter_prompt
    series = client.post("/collections", json={"name": "Letters", "archiveSeries": "7"}).json()["id"]
    [first] = client.get(f"/collections/{series}/prompt").json()
    assert (first["number"], first["collectionId"], first["reviewer"], first["body"]) == (1, series, None, read_starter_prompt())
    assert [(v["number"], v["body"]) for v in client.get("/collections/1/prompt").json()] == [(1, TEXTS["prompt"])]
    for prest_only in ("archive_reference", "Annotation areas", "dwelling", "Main survey form only", "Notes page", "card"):
        assert prest_only not in first["body"]
    assert first["body"].replace("\r\n", "\n").endswith("Fill in this structure, same keys, every value a string or null:\n")
    assert full_prompt(first["body"], {"text": None}).endswith('every value a string or null:\n\n{\n  "text": null\n}')
    assert instructions.problems("prompt", first["body"], {}) == []
    assert prompt_save(client, series).status_code == 201  # and it is edited like any other


def test_instruction_versions_number_each_series_prompt_from_1(client, two_series):
    assert prompt_save(client, 2).status_code == 201
    versions = client.get("/instruction-versions").json()
    assert [(v["collectionId"], v["number"], v["current"]) for v in versions if v["kind"] == "prompt"] == [
        (1, 1, True), (2, 1, False), (2, 2, True)]
    only = client.get("/instruction-versions?collection=2").json()
    assert [(v["number"], v["current"]) for v in only if v["kind"] == "prompt"] == [(1, False), (2, True)]
    assert sorted({v["kind"] for v in only}) == ["coded", "main", "notes", "prompt", "ship"]  # and every template
