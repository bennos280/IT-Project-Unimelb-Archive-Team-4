"""Every labelled page under tests/identify/pages: zero wrong answers, at least MIN_COVERAGE answered."""
from pipeline.identify.identify import MIN_COVERAGE, held_out, labelled_pages, model, score, stored

PATHS, TRUTH = labelled_pages()
X = stored(PATHS)


def check(labels, name):
    result = score(labels, TRUTH, PATHS)
    correct = result.answered - len(result.wrong)
    fraction_correct = correct / result.total if result.total else 0.0
    print(f"\n{name}\n"
          f"  {correct:,} correct ({fraction_correct:.1%}) · "
          f"{len(result.review):,} for review · {len(result.wrong):,} wrong")
    assert result.total > 1000, "page glob broke"
    assert result.passes(), (f"need 0 wrong and at least {MIN_COVERAGE:.0%} answered\n"
                             + result.summary("Details"))


def test_shipped_weights():
    check(model().predict(X)[0], "Known pages — saved model checked against familiar examples")


def test_held_out():
    """Train on 4/5, score the 1/5 never seen: the honest number."""
    check(held_out(X, TRUTH), "Unseen pages — each page tested by a model trained without it")
