"""Every labelled page under tests/identify/pages: zero wrong answers, at least MIN_COVERAGE answered."""
from pipeline.identify.identify import MIN_COVERAGE, held_out, labelled_pages, model, score, stored

PATHS, TRUTH = labelled_pages()
X = stored(PATHS)


def check(labels, name):
    result = score(labels, TRUTH, PATHS)
    print("\n" + result.summary(name))
    assert result.total > 1000, "page glob broke"
    assert result.passes(), f"{len(result.wrong)} wrong, {result.coverage:.1%} answered (need 0 and {MIN_COVERAGE:.0%})"


def test_shipped_weights():
    check(model().predict(X)[0], "shipped")


def test_held_out():
    """Train on 4/5, score the 1/5 never seen: the honest number."""
    check(held_out(X, TRUTH), "held-out")
