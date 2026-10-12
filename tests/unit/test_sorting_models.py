"""Page sorting retrained from the review screen: the model learns page types beyond the four, retrain() keeps a model only
if it passes the held-out check, the worker trains on the pages reviewers settled, and /sorting-models picks the model."""
from pathlib import Path

import numpy as np
import pytest

from backend import worker
from backend.db import models
from backend.pipeline.identify import identify
from backend.pipeline.identify.identify import Score
from backend.pipeline.identify.classifier import LABELS, REVIEW, Model
from tests.unit.test_backend_api import add_in_order

TYPES = (*LABELS, "followup")
rng = np.random.default_rng(0)
CENTRES = {page_type: rng.normal(size=16) * 10 for page_type in TYPES}


def pages(page_type, n):
    """Fingerprints of n pages of a type: points around its centre."""
    return CENTRES[page_type] + rng.normal(size=(n, 16))


def test_a_model_learns_a_page_type_beyond_the_four():
    X = np.vstack([pages(t, 30) for t in TYPES])
    model = Model.fit(X, np.repeat(TYPES, 30), labels=TYPES)
    said, _, _ = model.predict(pages("followup", 10))
    assert "followup" in said and set(said) <= {"followup", REVIEW}


@pytest.fixture
def fingerprints(monkeypatch):
    """The labelled pages (30 of each built-in type) and any image, by name, as made-up fingerprints."""
    labelled = [Path(f"{t}_{n}.jpg") for t in LABELS for n in range(30)]
    vectors = dict(zip(labelled, np.vstack([pages(t, 30) for t in LABELS])))
    monkeypatch.setattr(identify, "labelled_pages", lambda: (labelled, np.array([p.name.split("_")[0] for p in labelled])))
    monkeypatch.setattr(identify, "stored", lambda paths, compute=False, store=None: np.vstack([vectors[p] for p in paths]))
    return vectors


def test_retraining_learns_a_settled_page_type_and_keeps_the_model(fingerprints, tmp_path):
    settled = [Path(f"settled_{n}.jpg") for n in range(20)]
    fingerprints.update(zip(settled, pages("followup", 20)))
    result, page_types = identify.retrain([(p, "followup") for p in settled], tmp_path / "model.npz", tmp_path / "fingerprints")
    assert result.passes() and page_types == tuple(sorted(TYPES))
    said, _, _ = Model.load(tmp_path / "model.npz").predict(pages("followup", 10))
    assert "followup" in said and set(said) <= {"followup", REVIEW}


def test_a_retraining_that_fails_its_check_is_not_kept(fingerprints, tmp_path):
    settled = [Path(f"settled_{n}.jpg") for n in range(20)]
    fingerprints.update(zip(settled, pages("main", 20)))  # "followup" pages a model can't tell from main forms
    result, _ = identify.retrain([(p, "followup") for p in settled], tmp_path / "model.npz", tmp_path / "fingerprints")
    assert not result.passes() and not (tmp_path / "model.npz").exists()


@pytest.fixture
def settled(db):
    """A reviewer, two added page types, and pages: 12 followup and 3 letters pages reviewers settled, 2 main forms,
    an other page, and a notes page nobody has checked yet."""
    rows = [models.Reviewer(reviewer_id=1, name="Ben"), models.PageType(name="followup"), models.PageType(name="letters")]
    for n, (page_type, revision) in enumerate([("followup", 1)] * 12 + [("letters", 1)] * 3 + [("main", 2)] * 2
                                              + [("other", 1), ("notes", 0)]):
        rows.append(models.Page(page_id=f"6789_{n:05d}", category=page_type, revision_no=revision, import_path="x.png", bundle_id="6789"))
    add_in_order(db, *rows)
    db.commit()
    return db


def fake_retrain(monkeypatch, tmp_path, passes, no_scan=()):
    used = []

    def retrain(confirmed, out, store):
        assert store == tmp_path / "output" / "fingerprints" and out.parent == tmp_path / "output" / "sorting-models"
        used.extend(confirmed)
        wrong = [] if passes else [("p", "main", "followup")]
        return Score(total=200, answered=150, wrong=wrong, review=[], per_class={}), tuple(sorted(TYPES))

    monkeypatch.setattr(identify, "retrain", retrain)
    monkeypatch.setattr(worker.scans, "page_scan", lambda import_path, source_pdf, page_id: None if page_id in no_scan else Path(page_id))
    monkeypatch.setattr(worker, "settings", lambda: {"OUTPUT": str(tmp_path / "output")})
    return used


def test_the_worker_trains_on_settled_pages_and_uses_a_model_that_passes(settled, monkeypatch, tmp_path):
    used = fake_retrain(monkeypatch, tmp_path, passes=True)
    settled.add_all([models.SortingModel(path="old.npz", page_types="main", pages=1, answered=1, wrong=0, passed=True, active=True),
                     models.Job(kind="train", reviewer_id=1)])
    settled.commit()
    assert worker.work_once(settled)
    assert sorted(page_type for _, page_type in used) == ["followup"] * 12 + ["main"] * 2  # not letters, other or unchecked
    new = settled.query(models.SortingModel).order_by(models.SortingModel.model_id.desc()).first()
    assert (new.passed, new.active, new.reviewer_id, new.path.endswith("model-2.npz")) == (True, True, 1, True)
    assert new.note == "letters left out: 3 settled pages of the 10 it needs"
    assert [m.active for m in settled.query(models.SortingModel).order_by(models.SortingModel.model_id)] == [False, True]


def test_a_model_that_fails_its_check_is_recorded_but_not_used(settled, monkeypatch, tmp_path):
    fake_retrain(monkeypatch, tmp_path, passes=False)
    settled.add(models.Job(kind="train", reviewer_id=1))
    settled.commit()
    worker.work_once(settled)
    model = settled.query(models.SortingModel).one()
    assert (model.passed, model.active, model.path, model.wrong) == (False, False, None, 1)


def test_a_bundle_job_sorts_with_the_active_model(db, tmp_path, monkeypatch):
    (tmp_path / "model-1.npz").write_bytes(b"weights")
    db.add_all([models.SortingModel(path=str(tmp_path / "model-1.npz"), page_types="main", pages=1, answered=1, wrong=0,
                                    passed=True, active=True), models.Job(pdf=str(tmp_path / "216441" / "a.pdf"))])
    db.commit()
    used = []
    monkeypatch.setattr(worker, "settings", lambda: {"OUTPUT": str(tmp_path / "output")})
    monkeypatch.setattr(worker.pipeline, "run_steps", lambda run, names: used.append(run.sorting_model) or run.pages.append({"file": "a"}))
    monkeypatch.setattr(worker.loader, "dump_into_db", lambda manifest: None)
    worker.work_once(db)
    assert used == [tmp_path / "model-1.npz"]
    (tmp_path / "model-1.npz").unlink()  # e.g. output/ was cleared
    db.add(models.Job(pdf=str(tmp_path / "216441" / "a.pdf")))
    db.commit()
    worker.work_once(db)
    assert db.query(models.Job).order_by(models.Job.job_id.desc()).first().error.startswith("page sorting model 1's file")


def test_sorting_models_are_trained_listed_and_chosen_through_the_api(client, db):
    add_in_order(db, models.Reviewer(reviewer_id=1, name="Ben"),
                 models.SortingModel(path="a.npz", page_types="blank,coded,main,notes", pages=9, answered=8, wrong=0, passed=True),
                 models.SortingModel(path=None, page_types="blank,coded,followup,main,notes", pages=9, answered=9, wrong=2, passed=False))
    db.commit()
    queued = client.post("/sorting-models", json={"reviewerId": 1})
    assert (queued.status_code, queued.json()["kind"]) == (202, "train")
    assert client.post("/sorting-models", json={"reviewerId": 1}).status_code == 409  # already waiting
    assert client.post("/sorting-models", json={"reviewerId": 9}).status_code == 400
    assert [(m["id"], m["passed"], m["pageTypes"][2]) for m in client.get("/sorting-models").json()] == [
        (2, False, "followup"), (1, True, "main")]  # newest first

    def choose(model_id):
        return client.put("/sorting-models/active", json={"modelId": model_id, "reviewerId": 1})

    assert choose(7).status_code == 404
    assert choose(2).json()["detail"] == "That model failed its check, so it wasn't kept."
    assert choose(1).json() == {"active": 1}
    assert [m["active"] for m in client.get("/sorting-models").json()] == [False, True]
    assert choose(None).json() == {"active": None}  # back to the shipped model
    assert not any(m["active"] for m in client.get("/sorting-models").json())


def test_a_new_page_type_is_left_out_when_too_few_of_its_settled_pages_have_a_scan(settled, monkeypatch, tmp_path):
    used = fake_retrain(monkeypatch, tmp_path, passes=True, no_scan={f"6789_{n:05d}" for n in range(4)})  # 4 followup pages
    settled.add(models.Job(kind="train", reviewer_id=1))
    settled.commit()
    worker.work_once(settled)
    assert sorted(page_type for _, page_type in used) == ["main"] * 2
    assert settled.query(models.SortingModel).one().note == ("followup left out: 8 settled pages of the 10 it needs; "
                                                             "letters left out: 3 settled pages of the 10 it needs; "
                                                             "4 settled pages have no scan here or on the archive")


def test_retraining_keeps_its_fingerprints_apart_from_the_committed_ones(tmp_path, monkeypatch):
    """The real stored() and retrain(), with page fingerprints made up: the committed store is never written or pruned."""
    from PIL import Image
    committed, pages_dir = tmp_path / "committed" / "abc", tmp_path / "pages"
    for t in LABELS:
        (pages_dir / t).mkdir(parents=True)
        for n in range(30):
            Image.new("RGB", (4, 4), (LABELS.index(t) * 60, n, 0)).save(pages_dir / t / f"{n}.png")
    settled = []
    for n in range(20):
        settled.append(tmp_path / f"settled_{n}.png")
        Image.new("RGB", (4, 4), (250, n, 9)).save(settled[-1])
    centre = {**{f"{LABELS.index(t) * 60}": t for t in LABELS}, "250": "followup"}
    calls = []

    def fingerprint(paths):
        calls.append(len(paths))
        return np.zeros((0, 16)) if not paths else np.vstack([pages(centre[str(Image.open(p).getpixel((0, 0))[0])], 1) for p in paths])

    monkeypatch.setattr(identify, "PAGES", pages_dir)
    monkeypatch.setattr(identify, "STORE", committed)
    monkeypatch.setattr(identify, "fingerprint", fingerprint)
    identify.stored(identify.labelled_pages()[0], compute=True)  # the committed fingerprints, as `survey train` makes them
    before = sorted(committed.iterdir())
    result, _ = identify.retrain([(p, "followup") for p in settled], tmp_path / "model.npz", tmp_path / "output" / "fingerprints")
    assert result.passes() and sorted(committed.iterdir()) == before
    assert len(list((tmp_path / "output" / "fingerprints" / identify.CODE_HASH).iterdir())) == 20
    identify.retrain([(p, "followup") for p in settled], tmp_path / "model.npz", tmp_path / "output" / "fingerprints")
    assert [n for n in calls if n] == [120, 20]  # the second retraining reused every fingerprint
