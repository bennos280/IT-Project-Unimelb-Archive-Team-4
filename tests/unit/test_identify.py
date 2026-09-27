"""Unit tests for mainly pipeline/identify/identify.py"""

from pathlib import Path

import numpy as np
import pytest

from pipeline.identify import identify
from pipeline.identify.identify import (MIN_COVERAGE, Score, identify_pages,
                                        labelled_pages, score, stored)
from pipeline.identify.model import LABELS, REVIEW



# ---------------------------------------------------------------- score()
def pages(count):
    """Throwaway Path objects; `score` only ever uses them for reporting."""
    return [Path(f"page{index}.jpg") for index in range(count)]


def test_score_counts_correct_wrong_and_abstained_separately():

    # fake data
    paths = pages(4)
    labels = ["main", "notes", REVIEW, "blank"]
    truth = ["main", "coded", "notes", "blank"]      # index 1 is wrong, index 2 abstained

    result = score(labels, truth, paths)

    assert result.total == 4
    assert result.answered == 3                       # everything except the abstention
    assert [(p.name, said, was) for p, said, was in result.wrong] == \
        [("page1.jpg", "notes", "coded")]
    assert [(p.name, was) for p, was in result.review] == [("page2.jpg", "notes")]

def test_abstaining_is_never_counted_as_wrong():

    paths = pages(3)

    result = score([REVIEW] * 3, ["main", "notes", "coded"], paths)

    assert result.wrong == []
    assert result.answered == 0
    assert result.coverage == 0.0
    assert len(result.review) == 3

def test_answering_a_other_card_is_always_wrong():
    paths = pages(2)

    result = score(["main", REVIEW], ["other", "other"], paths)

    assert len(result.wrong) == 1
    assert result.wrong[0][1:] == ("main", "other")
    assert len(result.review) == 1

def test_per_class_counts_answered_out_of_total_for_each_truth():

    paths = pages(5)
    labels = ["main", "main", REVIEW, "notes", REVIEW]
    truth = ["main", "main", "main", "notes", "blank"]

    result = score(labels, truth, paths)

    assert result.per_class == {"blank": (0, 1), "main": (2, 3), "notes": (1, 1)}
    assert list(result.per_class) == sorted(result.per_class)      # sorted by label

def test_score_of_an_empty_set_is_safe():
    result = score([], [], [])

    assert result.total == 0 and result.coverage == 0.0

def test_coverage_is_the_answered_fraction():
    """coverage = answered / total, as a plain float."""
    result = Score(total=4, answered=3, wrong=[], review=[], per_class={})

    assert result.coverage == 0.75

@pytest.mark.parametrize("wrong,coverage_answered,expected", [
    ([], 100, True),                                    # perfect: 100% answered, none wrong
    ([], int(MIN_COVERAGE * 100), True),                # exactly at the minimum passes
    ([], int(MIN_COVERAGE * 100) - 1, False),           # one page below it fails
    ([("p", "main", "notes")], 100, False),             # a single wrong answer fails outright
])
def test_passes_requires_zero_wrong_and_enough_coverage(wrong, coverage_answered, expected):
    result = Score(total=100, answered=coverage_answered, wrong=wrong, review=[], per_class={})

    assert result.passes() is expected

def test_summary_lists_the_headline_numbers_and_every_mistake():
    result = score(["main", REVIEW, REVIEW], ["notes", "coded", "other"], pages(3))

    text = result.summary("held-out")

    assert text.startswith("held-out: 1/3 answered = 33.3%, 1 wrong")
    assert "WRONG  page0.jpg: said main, truth notes" in text
    assert "REVIEW page1.jpg (truth coded)" in text
    assert "page2.jpg" not in text        # abstaining on a other card is correct


# ---------------------------------------------------------------- labelled_pages()
def test_labelled_pages_takes_the_truth_from_the_top_folder(tmp_path, monkeypatch):

    root = tmp_path / "pages"
    for relative in ["coded/layout_a/x.jpg", "coded/y.png", "main/z.jpeg",
                     "other/f.jpg"]:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"image bytes")
    (root / "main" / "notes.txt").write_text("ignore", encoding="utf-8")    # basically tests if it ignores non image files
    monkeypatch.setattr(identify, "PAGES", root)

    paths, truth = labelled_pages()

    # sorted() orders by the whole path string, so coded/layout_a/x.jpg sorts
    # before coded/y.png ("l" < "y"), not by filename alone.
    assert [p.name for p in paths] == ["x.jpg", "y.png", "z.jpeg", "f.jpg"]
    assert list(truth) == ["coded", "coded", "main", "other"]
    assert not any(p.suffix == ".txt" for p in paths)      # non-images excluded


def test_labelled_pages_is_deterministic_in_order(tmp_path, monkeypatch):

    root = tmp_path / "pages"
    for name in ["main/c.jpg", "main/a.jpg", "main/b.jpg"]:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
    monkeypatch.setattr(identify, "PAGES", root)

    first, _ = labelled_pages()
    second, _ = labelled_pages()

    assert first == second
    assert [p.name for p in first] == ["a.jpg", "b.jpg", "c.jpg"]

# ---------------------------------------------------------------- stored()
def test_stored_tells_you_to_train_when_a_fingerprint_is_missing(tmp_path, monkeypatch):

    # The error message shows STORE relative to the project root, so both
    # constants are redirected into tmp_path together.
    monkeypatch.setattr(identify, "ROOT", tmp_path)
    monkeypatch.setattr(identify, "STORE", tmp_path / "fingerprints" / "abc123")
    page = tmp_path / "new.jpg"
    page.write_bytes(b"a brand new page")

    with pytest.raises(FileNotFoundError, match="1 pages have no fingerprint"):
        stored([page])


def test_stored_loads_fingerprints_by_image_content_not_filename(tmp_path, monkeypatch):
    """Cached fingerprints are keyed by a hash of the image bytes.

    Renaming or moving a page therefore costs nothing, while *editing* one
    correctly invalidates its cache. We write a fingerprint under the hash of
    some bytes, then read it back through a differently-named file with the
    same content.
    """
    import hashlib

    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setattr(identify, "STORE", store)
    content = b"the very same image bytes"
    name = hashlib.sha1(content).hexdigest()[:20] + ".npy"
    np.save(store / name, np.array([1.0, 2.0, 3.0], np.float16))

    first, second = tmp_path / "one.jpg", tmp_path / "two.jpg"
    first.write_bytes(content)
    second.write_bytes(content)

    X = stored([first, second])

    assert X.shape == (2, 3)
    assert X.dtype == np.float32           # widened from the float16 on disk
    np.testing.assert_allclose(X[0], X[1])


# ---------------------------------------------------------------- identify_pages()
def test_identify_pages_on_an_empty_list_does_not_load_the_model():
    # dont load model when we dont have to!
    assert identify_pages([]) == []

def test_identify_pages_returns_plain_python_types(monkeypatch):

    class FakeModel:
        def predict(self, X):
            return (np.array(["main", REVIEW]), np.float32([0.9, 0.2]), np.float32([0.1, 0.8]))

    monkeypatch.setattr(identify, "model", lambda: FakeModel())
    monkeypatch.setattr(identify, "fingerprint", lambda paths: np.zeros((len(paths), 4), np.float32))

    results = identify_pages(["a.jpg", "b.jpg"])

    assert [r["label"] for r in results] == ["main", REVIEW]
    assert all(type(r["label"]) is str for r in results)
    assert all(type(r["confidence"]) is float and type(r["distance"]) is float for r in results)
    assert [r["path"] for r in results] == [Path("a.jpg"), Path("b.jpg")]

    import json
    json.dumps([{k: v for k, v in r.items() if k != "path"} for r in results])   # must not raise


def test_min_coverage_is_the_documented_threshold():
    # raise an error if these constants have changed/ can remove if unnecessary
    assert MIN_COVERAGE == 0.5
    assert set(LABELS) == {"blank", "coded", "main", "notes"}

