"""Page types added from the review screen (/page-types), and a page read again as another type: PUT /pages/{id}/type queues
a job, and backend/worker.py reads the page with that type's newest template and swaps what was read off it."""
from PIL import Image
import pytest

from backend import worker
from backend.db import models
from backend.pipeline.transcribe import transcribe as transcription
from tests.unit.test_backend_api import add_in_order, review

FOLLOWUP = '{"date_of_follow_up": null, "text": null}'
PAGE = "6789_00002"


@pytest.fixture
def setup(db):
    """A reviewer, the prompt and the main template, and a survey's main page read as main."""
    add_in_order(db, models.Reviewer(reviewer_id=1, name="Ben"),
                 models.InstructionVersion(kind="prompt", collection_id=1, body="Read it.", sha256="p"),
                 models.InstructionVersion(kind="main", body='{"number_of_dwelling": null}', sha256="m"),
                 models.Survey(survey_id="s", bundle_id="6789"),
                 models.Page(page_id=PAGE, survey_id="s", category="main", import_path="x.png", bundle_id="6789", model="opus"),
                 models.Field(page_id=PAGE, field_title="number_of_dwelling", text_raw="13"))
    db.commit()
    return db


def change(client, page_type, page=PAGE):
    return client.put(f"/pages/{page}/type", json={"pageType": page_type, "reviewerId": 1, "provider": "claude", "model": "sonnet", "effort": "low"})


def fields(db, page=PAGE):
    return dict(db.query(models.Field.field_title, models.Field.text_raw).filter_by(page_id=page))


def test_a_new_page_type_needs_a_template_before_pages_are_read_as_it(client, setup):
    assert [(t["name"], t["builtIn"], t["templateVersion"] is not None) for t in client.get("/page-types").json()] == [
        ("coded", True, False), ("main", True, True), ("notes", True, False), ("other", True, False)]

    def create(name, reviewer=1):
        return client.post("/page-types", json={"name": name, "reviewerId": reviewer}).status_code

    assert create("Follow up") == 400
    assert create("blank") == 400  # what page sorting answers for a blank page
    assert create("followup", reviewer=9) == 400
    assert create("followup") == 201
    assert create("followup") == 409
    assert change(client, "followup").json()["detail"] == "Give followup a template first."
    assert client.post("/instructions/other", json={"body": FOLLOWUP, "basedOn": None, "reviewerId": 1}).status_code == 404
    assert client.post("/instructions/followup", json={"body": FOLLOWUP, "basedOn": None, "reviewerId": 1}).status_code == 201

    queued = change(client, "followup").json()
    assert (queued["pageType"], queued["job"]["kind"], queued["job"]["pageType"], queued["job"]["status"]) == (
        "main", "page", "followup", "waiting")  # the page changes when the worker has read it
    assert change(client, "followup").status_code == 409  # already waiting


def test_a_page_types_label_is_what_people_see_and_is_unique_in_its_collection(client, setup):
    def create(name, label=None):
        return client.post("/page-types", json={"name": name, "label": label, "reviewerId": 1})

    assert create("followup", "Follow-up visit").json()["label"] == "Follow-up visit"
    assert create("letter").json()["label"] == "letter"  # the name if not given
    assert create("visit", " ").status_code == 400
    taken = create("visit", "Follow-up visit")
    assert (taken.status_code, taken.json()["detail"]) == (409, "There is already a page type labelled Follow-up visit.")
    assert create("visit", "Main page").status_code == 409  # a built-in type's label
    assert {t["name"]: t["label"] for t in client.get("/page-types").json()} == {
        "coded": "Coded page", "main": "Main page", "notes": "Notes page", "other": "Unknown",
        "followup": "Follow-up visit", "letter": "letter"}
    assert client.get("/survey/s").json()["pages"][0]["typeLabel"] == "Main page"


def test_reading_a_page_again_without_a_choice_uses_the_saved_one_or_is_refused(client, setup):
    client.post("/page-types", json={"name": "followup", "reviewerId": 1})
    client.post("/instructions/followup", json={"body": FOLLOWUP, "basedOn": None, "reviewerId": 1})
    asked = {"pageType": "followup", "reviewerId": 1}
    refused = client.put(f"/pages/{PAGE}/type", json=asked)
    assert (refused.status_code, refused.json()["detail"]) == (409, "Choose a transcription model on the Settings page first.")
    assert setup.query(models.Job).count() == 0
    client.put("/transcription-defaults", json={"provider": "codex", "model": "gpt-test", "effort": "medium"})
    queued = client.put(f"/pages/{PAGE}/type", json=asked)
    job = setup.get(models.Job, queued.json()["job"]["id"])
    assert (queued.status_code, job.transcription_provider, job.transcription_model, job.transcription_effort) == (200, "codex", "gpt-test", "medium")


def test_a_part_of_a_choice_is_checked_like_a_whole_one(client, setup):
    client.post("/page-types", json={"name": "followup", "reviewerId": 1})
    client.post("/instructions/followup", json={"body": FOLLOWUP, "basedOn": None, "reviewerId": 1})
    client.put("/transcription-defaults", json={"provider": "codex", "model": "gpt-test", "effort": "medium"})
    for part in ({"effort": "-low"}, {"provider": "unknown"}, {"model": "two words"}):
        assert client.put(f"/pages/{PAGE}/type", json={"pageType": "followup", "reviewerId": 1, **part}).status_code == 400
    assert setup.query(models.Job).count() == 0


def test_a_page_made_other_is_emptied_at_once(client, setup):
    assert change(client, "other").json() == {"pageType": "other", "job": None}
    setup.expire_all()
    page = setup.get(models.Page, PAGE)
    assert (page.category, page.revision_no, page.model, fields(setup)) == ("other", 1, None, {"text": None})


def test_the_unknown_setting_decides_not_the_name_other(client, setup):
    """Made the collection's Unknown type, any page type is emptied at once, can't have a template and is flagged for a
    check; other, no longer Unknown, is read like any type."""
    setup.get(models.PageType, "other").unknown = False
    setup.add(models.PageType(collection_id=1, name="unsorted", label="Unsorted", unknown=True))
    setup.commit()
    assert client.post("/instructions/unsorted", json={"body": FOLLOWUP, "basedOn": None, "reviewerId": 1}).status_code == 404
    assert change(client, "other").json()["detail"] == "Give other a template first."
    assert change(client, "unsorted").json() == {"pageType": "unsorted", "job": None}
    page = client.get("/survey/s").json()["pages"][0]
    assert (page["type"], page["typeLabel"], [f["fieldId"] for f in page["flags"]]) == ("unsorted", "Unsorted", ["text"])


def test_a_page_keeps_its_type_once_reviewed_or_when_the_change_is_unknown(client, setup):
    assert change(client, "notes", page="nope").status_code == 404
    assert change(client, "letters").status_code == 400
    assert change(client, "main").status_code == 400  # already main
    client.post("/reviews/s", json={"reviews": {PAGE: {"number_of_dwelling": review("14")}}, "revisions": {PAGE: 1}})
    assert change(client, "other").json()["detail"] == "This page has saved reviews, which reading it again would lose."


@pytest.fixture
def queued(setup, tmp_path, monkeypatch):
    """The followup type with a template, a job to read the page as it, and a scan of the page."""
    followup = models.InstructionVersion(kind="followup", body=FOLLOWUP, sha256="f")
    for row in (models.PageType(collection_id=1, name="followup", reviewer_id=1), followup, models.Job(kind="page", page_id=PAGE, page_type="followup", transcription_provider="claude", transcription_model="sonnet", transcription_effort="low")):
        setup.add(row)
        setup.flush()
    setup.commit()
    scan = tmp_path / "page.png"
    Image.new("RGB", (8, 8), "white").save(scan)
    monkeypatch.setattr(worker.scans, "page_scan", lambda import_path, source_pdf, page_id: scan)
    return followup


def test_the_worker_reads_the_page_again_and_swaps_what_was_read(setup, queued, monkeypatch):
    def transcribe(image, kind, texts, **choice):
        assert (image.name, kind, texts["followup"], texts["prompt"]) == ("page.png", "followup", FOLLOWUP, "Read it.")
        assert choice["fresh"]  # asked of the model, not a saved answer
        return {"date_of_follow_up": "3/43", "text": "moved to Kew", "provider": "claude", "model": "sonnet", "effort": "low", "seconds": 2.0}

    monkeypatch.setattr(transcription, "transcribe", transcribe)
    assert worker.work_once(setup)
    page = setup.get(models.Page, PAGE)
    assert (page.category, page.revision_no, page.model, page.template_version_id) == ("followup", 1, "sonnet", queued.version_id)
    assert page.prompt_version_id == setup.query(models.InstructionVersion).filter_by(kind="prompt").one().version_id
    assert fields(setup) == {"date_of_follow_up": "3/43", "text": "moved to Kew"}  # the main form's field is gone
    assert setup.query(models.Job).one().status == "done"


@pytest.fixture
def ship_page(setup, tmp_path, monkeypatch):
    """A page of series 2 (ships) with a job to read it again as ship; series 2 has no prompt yet."""
    scan = tmp_path / "page.png"
    Image.new("RGB", (8, 8), "white").save(scan)
    monkeypatch.setattr(worker.scans, "page_scan", lambda import_path, source_pdf, page_id: scan)
    for row in (models.Collection(collection_id=2, name="Ships"), models.PageType(collection_id=2, name="ship", reviewer_id=1),
                models.InstructionVersion(kind="ship", body='{"vessel": null}', sha256="t"),
                models.Bundle(bundle_id="ships", source_pdf="ships.pdf", collection_id=2),
                models.Page(page_id="ships_1", category="ship", import_path="x.png", bundle_id="ships"),
                models.Field(page_id="ships_1", field_title="vessel", text_raw="Ann"),
                models.Job(kind="page", page_id="ships_1", page_type="ship", transcription_provider="claude", transcription_model="sonnet", transcription_effort="low")):
        setup.add(row)
        setup.flush()
    setup.commit()
    return setup


def test_a_page_is_read_again_with_its_own_series_prompt_and_records_that_version(ship_page, monkeypatch):
    prompt = models.InstructionVersion(kind="prompt", collection_id=2, body="Read the ship.", sha256="s")
    ship_page.add(prompt)
    ship_page.commit()
    prompts = []

    def transcribe(image, kind, texts, **choice):
        prompts.append(texts["prompt"])
        return {"vessel": "Ann", "provider": "claude", "model": "sonnet", "effort": "low", "seconds": 1.0}

    monkeypatch.setattr(transcription, "transcribe", transcribe)
    worker.work_once(ship_page)
    assert (prompts, ship_page.query(models.Job).one().status) == (["Read the ship."], "done")
    ship = ship_page.query(models.InstructionVersion).filter_by(kind="ship").one()
    assert (ship_page.get(models.Page, "ships_1").prompt_version_id, ship_page.get(models.Page, "ships_1").template_version_id) == (
        prompt.version_id, ship.version_id)


def test_a_page_of_a_series_with_no_prompt_is_not_read_again(ship_page, monkeypatch):
    monkeypatch.setattr(transcription, "transcribe", lambda *args, **kwargs: pytest.fail("a model was asked"))
    worker.work_once(ship_page)
    job = ship_page.query(models.Job).one()
    assert (job.status, job.error) == ("failed", "this series has no prompt: add one in its Setup first")
    assert fields(ship_page, "ships_1") == {"vessel": "Ann"}


def test_a_page_reviewed_while_it_is_read_again_is_left_as_it_was(setup, queued, monkeypatch):
    def transcribe(image, kind, texts, **choice):
        setup.add(models.Edit(page_id=PAGE, edit_text="14", field_title="number_of_dwelling", reviewer_id=1))
        setup.commit()  # a reviewer saves while the model reads
        return {"text": "moved to Kew"}

    monkeypatch.setattr(transcription, "transcribe", transcribe)
    worker.work_once(setup)
    job = setup.query(models.Job).one()
    assert (job.status, job.error) == ("failed", "the page was reviewed while it was being read again, so it was left as it was")
    assert (setup.get(models.Page, PAGE).category, fields(setup)) == ("main", {"number_of_dwelling": "13"})


def test_a_read_that_fails_while_the_page_is_swapped_leaves_it_as_it_was(setup, queued, monkeypatch):
    monkeypatch.setattr(transcription, "transcribe", lambda image, kind, texts, **choice: {"residents": [["a list in a list"]]})
    worker.work_once(setup)
    assert setup.query(models.Job).one().status == "failed"
    page = setup.get(models.Page, PAGE)
    assert (page.category, page.revision_no, fields(setup)) == ("main", 0, {"number_of_dwelling": "13"})


def test_a_page_read_again_counts_for_accuracy_only_once_a_reviewer_saves_it(client, setup, queued, monkeypatch):
    monkeypatch.setattr(transcription, "transcribe", lambda image, kind, texts, **choice: {"text": "moved", "model": "sonnet", "effort": "low"})
    worker.work_once(setup)
    assert client.get("/accuracy").json() == []  # read again, but nobody has checked it
    assert client.post("/reviews/s", json={"reviews": {PAGE: {}}, "revisions": {PAGE: 2}}).status_code == 200
    assert [(row["model"], row["templateVersion"], row["pages"]) for row in client.get("/accuracy").json()] == [
        ("sonnet", queued.version_id, 1)]


def test_page_type_job_records_selected_transcription_model(client, setup):
    setup.get(models.Page, PAGE).category = 'notes'
    setup.commit()
    payload = {'pageType': 'main', 'reviewerId': 1, 'model': 'selected-model', 'provider': 'claude', 'effort': 'low'}
    assert client.put(f'/pages/{PAGE}/type', json={**payload, 'model': ''}).status_code == 400
    response = client.put(f'/pages/{PAGE}/type', json=payload)
    assert response.status_code == 200
    job = setup.get(models.Job, response.json()['job']['id'])
    assert (job.transcription_model, job.transcription_provider, job.transcription_effort) == ('selected-model', 'claude', 'low')
