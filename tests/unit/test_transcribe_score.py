"""Unit tests for backend/pipeline/transcribe/score.py -- how a transcription is graded. do wee reallllyy need this. :(("""


import json

import pytest

from backend.pipeline.transcribe import score as score_module
from backend.pipeline.transcribe.score import STAMPS, flatten, norm, score_page, scorable


# ---------------------------------------------------------------- flatten()
def test_flatten_turns_nested_objects_into_dotted_paths():
    """Nesting becomes "parent.child", so the key and answer compare field by field.

    Comparing whole nested objects would make one wrong character fail an
    entire section. Flattening first is what allows a per-field score.
    """
    assert flatten({"a": 1, "b": {"c": 2, "d": {"e": 3}}}) == \
        {"a": 1, "b.c": 2, "b.d.e": 3}

def test_flatten_indexes_list_items_by_position():
    """Lists become "name[0]", "name[1]" -- position matters.
    """
    assert flatten({"notes": ["first", "second"]}) == \
        {"notes[0]": "first", "notes[1]": "second"}

def test_flatten_handles_lists_of_objects():
    """The two rules combine, giving paths like "annotations[0].raw"."""
    flat = flatten({"annotations": [{"raw": "x", "location": "top"}]})

    assert flat == {"annotations[0].raw": "x", "annotations[0].location": "top"}

def test_flatten_keeps_none_and_empty_values():
    """Blank fields survive flattening -- they are needed to detect invented data.
    """
    assert flatten({"a": None, "b": ""}) == {"a": None, "b": ""}



def test_flatten_of_a_bare_value_uses_an_empty_key():
    """A scalar at the top level flattens to {"": value} -- an edge case, documented.
    """
    assert flatten("just text") == {"": "just text"}

# ---------------------------------------------------------------- norm()
@pytest.mark.parametrize("left,right", [
    ("Smith", "smith"),                    # case is ignored
    ("  Smith  ", "Smith"),                # surrounding space is ignored
    ("John  Smith", "John Smith"),         # runs of space collapse to one
    ("John\nSmith", "John Smith"),         # newlines are whitespace too
    (None, ""),                            # a missing value reads as empty
])
def test_norm_treats_these_as_the_same_answer(left, right):
    """Formatting differences must not be scored as transcription errors.
    """
    assert norm(left) == norm(right)


@pytest.mark.parametrize("left,right", [
    ("30/-", "30/"),        # pre-decimal currency: these are different amounts
    ("St.", "St"),          # abbreviation punctuation
    ("No 7", "No. 7"),
])
def test_norm_keeps_punctuation_because_it_carries_meaning(left, right):
    """Punctuation is deliberately *not* stripped, unlike case and whitespace."""
    assert norm(left) != norm(right)

def test_norm_converts_non_strings_before_comparing():
    """Numbers and booleans are stringified, so a model returning 7 matches "7".
    """
    assert norm(7) == norm("7")
    assert norm(True) == "true"


# ---------------------------------------------------------------- scorable()
@pytest.mark.parametrize("path", sorted(STAMPS))
def test_provenance_stamps_are_not_graded(path):
    """engine/model/effort/seconds are written by our code, not read off the card.
    """
    assert scorable(path) is False

def test_annotation_paths_are_excluded_from_grading():
    """Anything under `annotations[...]` is skipped.
    """
    assert scorable("annotations[0].raw") is False
    assert scorable("annotations[1].location") is False
    # A normal field that merely *contains* the word is still graded.
    assert scorable("annotation_summary") is True

def test_ordinary_card_fields_are_graded():
    assert scorable("address") is True
    assert scorable("household.members[0].name") is True

# ---------------------------------------------------------------- score_page()
def test_score_page_counts_exact_matches_as_hits():
    """A field is a hit when the normalised answer equals the normalised key."""
    key = {"address": "12 Smith St", "municipality": "Fitzroy"}
    answer = {"address": "12 smith st", "municipality": "Fitzroy"}

    result = score_page(key, answer)

    assert result["total"] == 2 and result["hits"] == 2
    assert result["missed"] == []

def test_score_page_lists_the_fields_that_were_missed():
    """Misses are reported by path, so `--pages` can show what went wrong."""
    key = {"address": "12 Smith St", "municipality": "Fitzroy"}
    answer = {"address": "12 Smith St", "municipality": "Carlton"}

    result = score_page(key, answer)

    assert result["hits"] == 1
    assert result["missed"] == ["municipality"]

def test_score_page_only_grades_fields_the_card_actually_has():
    """Fields blank in the truth are excluded from `total`.
    """
    key = {"address": "12 Smith St", "municipality": None, "number": ""}
    answer = {"address": "12 Smith St", "municipality": None, "number": ""}

    result = score_page(key, answer)

    assert result["total"] == 1          # only "address" was gradeable
    assert result["blanks"] == 2         # the other two are tracked separately

def test_score_page_reports_invented_values_for_blank_fields():
    """Filling in a box the card left empty is recorded as "invented".
    """
    key = {"address": "12 Smith St", "municipality": None, "number": ""}
    answer = {"address": "12 Smith St", "municipality": "Fitzroy", "number": ""}

    result = score_page(key, answer)

    assert result["invented"] == ["municipality"]
    assert result["hits"] == 1           # the invention does not affect the hit count

def test_score_page_does_not_count_a_blank_answer_as_invented():
    """Leaving a blank field blank -- as None or "" is correct, not an invention."""
    key = {"a": None, "b": ""}
    answer = {"a": None, "b": ""}

    assert score_page(key, answer)["invented"] == []

def test_score_page_treats_a_missing_field_as_a_miss_not_a_crash():
    """A model that omits a field entirely scores zero for it and does not error.
    """
    result = score_page({"address": "12 Smith St"}, {})

    assert result["hits"] == 0 and result["missed"] == ["address"]
    assert result["chars"] == [0.0]

def test_score_page_character_similarity_rewards_near_misses():
    """`chars` holds a 0-1 similarity per field, so near-misses are visible.
    """
    exact = score_page({"a": "Fitzroy"}, {"a": "Fitzroy"})["chars"][0]
    near = score_page({"a": "Fitzroy"}, {"a": "Fitzrov"})["chars"][0]
    far = score_page({"a": "Fitzroy"}, {"a": "zzzzzzz"})["chars"][0]

    assert exact == 1.0
    assert 0.5 < near < 1.0
    assert far < near

def test_score_page_ignores_stamps_and_annotations_end_to_end():
    """A realistic answer with stamps and annotations grades only the real fields.
    """
    key = {"address": "12 Smith St", "annotations": [{"raw": "in pencil"}]}
    answer = {"address": "12 Smith St", "annotations": [{"raw": "different wording"}],
              "engine": "claude", "model": "sonnet", "effort": "high", "seconds": 12.5}

    result = score_page(key, answer)

    assert result["total"] == 1 and result["hits"] == 1
    assert result["missed"] == [] and result["invented"] == []
    assert result["seconds"] == 12.5      # recorded for the timing column, not graded

def test_score_page_grades_nested_structures_field_by_field():
    """Nested objects are compared leaf by leaf, giving partial credit.

    """
    key = {"household": {"head": "Smith", "spouse": "Mary"}}
    answer = {"household": {"head": "Smith", "spouse": "Margaret"}}

    result = score_page(key, answer)

    assert result["total"] == 2 and result["hits"] == 1
    assert result["missed"] == ["household.spouse"]


def test_score_page_of_an_empty_key_is_zero_not_an_error():
    """A truth file with no filled fields yields total 0 without dividing by anything.
    """
    result = score_page({}, {"engine": "claude"})

    assert result["total"] == 0 and result["hits"] == 0 and result["chars"] == []

# ---------------------------------------------------------------- main()
def build_results(tmp_path, monkeypatch, truth, answers):
    """helper that lays out truth/<kind>/<page>.json and results/<model>/<page>.json in tmp_path.
    """
    truth_root, answers_root = tmp_path / "truth", tmp_path / "answers"
    for kind, pages in truth.items():
        (truth_root / kind).mkdir(parents=True)
        for page, data in pages.items():
            (truth_root / kind / f"{page}.json").write_text(json.dumps(data), encoding="utf-8")
    for model, pages in answers.items():
        (answers_root / model).mkdir(parents=True)
        for page, data in pages.items():
            (answers_root / model / f"{page}.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(score_module, "TRUTH", truth_root)
    monkeypatch.setattr(score_module, "ANSWERS", answers_root)


def test_main_exits_when_there_are_no_results_yet(tmp_path, monkeypatch):
    """With no results folder, the user is told which command produces one.
    """
    monkeypatch.setattr(score_module, "ANSWERS", tmp_path / "missing")

    with pytest.raises(SystemExit, match="No results yet"):
        score_module.main(show_pages=False)

def test_main_prints_a_row_per_model_and_page_kind(tmp_path, monkeypatch, capsys):
    """The table has one line per (model, kind) with the exact-match fraction.
    Here the model gets one of two fields right, so the row must read 50% (1/2).
    """
    build_results(
        tmp_path, monkeypatch,
        truth={"main": {"p1": {"address": "12 Smith St", "municipality": "Fitzroy"}}},
        answers={"sonnet-high": {"p1": {"address": "12 Smith St",
                                        "municipality": "Carlton", "seconds": 10}}})

    score_module.main(show_pages=False)

    out = capsys.readouterr().out
    assert "sonnet-high" in out
    assert "50% (1/2)" in out

def test_main_counts_pages_with_no_answer_as_missing(tmp_path, monkeypatch, capsys):
    """A page in the truth set with no matching answer is reported as missing.
    """
    build_results(
        tmp_path, monkeypatch,
        truth={"main": {"p1": {"address": "A"}, "p2": {"address": "B"}}},
        answers={"sonnet-high": {"p1": {"address": "A"}}})

    score_module.main(show_pages=False)

    lines = [line for line in capsys.readouterr().out.splitlines() if "sonnet-high" in line]
    assert lines and lines[0].split()[-2] == "1"      # one page missing

def test_main_skips_a_kind_with_no_answers_at_all(tmp_path, monkeypatch, capsys):
    """A page kind the model never attempted produces no row, rather than a zero row.
    """
    build_results(
        tmp_path, monkeypatch,
        truth={"main": {"p1": {"address": "A"}}, "notes": {"n1": {"text": "hello"}}},
        answers={"sonnet-high": {"p1": {"address": "A"}}})

    score_module.main(show_pages=False)

    out = capsys.readouterr().out
    assert "main" in out
    assert "notes" not in out

