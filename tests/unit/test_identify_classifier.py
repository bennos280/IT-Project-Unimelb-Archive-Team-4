"""Unit tests for backend/pipeline/identify/classifier.py"""

import numpy as np
import pytest

from backend.pipeline.identify.classifier import (C, DIST_MARGIN, KNN, LABELS, REVIEW, Model,
                                     choose_thresholds, cross_validate, unit)


def simple_model(prob_threshold=0.5, dist_threshold=0.5):
    """fake model place holder to avoid calling an actual model, makes unit tests more focused
    """
    return Model(
        mean=np.zeros(2, np.float32),
        std=np.ones(2, np.float32),
        coef=np.array([[1.0, 0.0], [0.0, 1.0]]),
        intercept=np.zeros(2),
        classes=np.array(["blank", "main"]),
        reference=unit(np.array([[1.0, 0.0], [0.0, 1.0]], np.float32)),
        prob_threshold=prob_threshold,
        dist_threshold=dist_threshold,
    )

# ---------------------------------------------------------------- unit()
def test_unit_scales_every_row_to_length_one():

    # assert that unit() actually properly scales vectors to length to 1
    X = np.array([[3.0, 4.0], [100.0, 0.0]])

    result = unit(X)

    np.testing.assert_allclose(np.linalg.norm(result, axis=1), [1.0, 1.0], atol=1e-6)
    np.testing.assert_allclose(result[0], [0.6, 0.8], atol=1e-6)

def test_unit_does_not_divide_by_zero_on_an_all_zero_row():

    result = unit(np.zeros((1, 4), np.float32))

    assert not np.isnan(result).any()
    np.testing.assert_array_equal(result, np.zeros((1, 4)))


# ---------------------------------------------------------------- Model.scores()
def test_scores_returns_a_label_a_probability_and_a_distance_per_row():
    """ assert that scores() actually returns what is expected
    """
    model = simple_model()
    X = np.array([[5.0, 0.0], [0.0, 5.0]])

    labels, conf, dist = model.scores(X)

    assert list(labels) == ["blank", "main"]
    assert np.all((conf > 0.5) & (conf <= 1.0))
    np.testing.assert_allclose(dist, [0.5, 0.5], atol=1e-6)   # mean of 0 and 1 over KNN=2 refs

def test_scores_distance_grows_as_a_page_moves_away_from_the_training_set():
    """
        A fingerprint pointing away from every reference gets a larger distance.
    """
    model = simple_model()
    near = np.array([[1.0, 0.0]])          # exactly a reference direction
    far = np.array([[-1.0, -1.0]])         # opposite side of the space

    assert model.scores(near)[2][0] < model.scores(far)[2][0]


def test_scores_uses_at_most_knn_neighbours():

    close = np.tile([1.0, 0.0], (KNN, 1))
    model = simple_model()
    model.reference = unit(np.array(close, np.float32))
    baseline = model.scores(np.array([[1.0, 0.0]]))[2][0]

    model.reference = unit(np.vstack([close, np.tile([-1.0, 0.0], (20, 1))]).astype(np.float32))
    assert model.scores(np.array([[1.0, 0.0]]))[2][0] == pytest.approx(baseline, abs=1e-6)

# ---------------------------------------------------------------- Model.predict(): the gates
def test_predict_answers_only_when_both_gates_pass():

    # confident if > 0.8 and close if <0.3
    model = simple_model(prob_threshold=0.8, dist_threshold=0.3)
    model.scores = lambda X: (np.array(["main", "main", "main", "main"]),
                              np.array([0.9, 0.9, 0.7, 0.7]),      # confident? yes yes no  no
                              np.array([0.1, 0.5, 0.1, 0.5]))      # close?     yes no yes no

    labels, conf, dist = model.predict(np.zeros((4, 2)))

    assert list(labels) == ["main", REVIEW, REVIEW, REVIEW]
    # The raw numbers are returned unchanged even when the answer is REVIEW,
    # so review.json can tell a human *why* (and sort by "highest distance").
    np.testing.assert_allclose(conf, [0.9, 0.9, 0.7, 0.7])
    np.testing.assert_allclose(dist, [0.1, 0.5, 0.1, 0.5])

def test_predict_treats_the_thresholds_as_inclusive_boundaries():
    """Exactly at the threshold counts as passing (>= and <=).

    """
    model = simple_model(prob_threshold=0.8, dist_threshold=0.3)
    model.scores = lambda X: (np.array(["main"]), np.array([0.8]), np.array([0.3]))

    assert model.predict(np.zeros((1, 2)))[0][0] == "main"

def test_predict_with_impossible_thresholds_abstains_on_everything():
    """The defaults (prob 1.0, dist 0.0) make an untuned head answer nothing.
    """
    model = simple_model(prob_threshold=1.0, dist_threshold=0.0)

    labels, fuck, this = model.predict(np.array([[5.0, 0.0], [0.0, 5.0]]))

    assert list(labels) == [REVIEW, REVIEW]

# ---------------------------------------------------------------- save / load
def test_save_and_load_round_trip_preserves_predictions(tmp_path):
    """Weights survive a trip through .npz with identical behaviour.
    basically make sure nothin is lost after save/load
    """
    original = simple_model(prob_threshold=0.75, dist_threshold=0.25)
    path = tmp_path / "weights.npz"

    original.save(path)
    loaded = Model.load(path)

    assert loaded.reference.dtype == np.float32
    assert isinstance(loaded.prob_threshold, float) and loaded.prob_threshold == 0.75
    assert isinstance(loaded.dist_threshold, float) and loaded.dist_threshold == 0.25
    assert list(loaded.classes) == list(original.classes)
    X = np.array([[5.0, 0.0], [0.0, 5.0], [-1.0, -1.0]])
    np.testing.assert_array_equal(loaded.predict(X)[0], original.predict(X)[0])

def test_save_returns_the_path_it_wrote(tmp_path):
    """`save` returns its destination, which `train()` uses to report the file size."""
    path = tmp_path / "weights.npz"

    assert simple_model().save(path) == path
    assert path.exists()

def test_load_missing_weights_names_the_fix(tmp_path):
    """A fresh clone without weights.npz is told to run `survey train`.
    """
    with pytest.raises(FileNotFoundError, match="run `survey train`"):
        Model.load(tmp_path / "absent.npz")


# ---------------------------------------------------------------- choose_thresholds()
def test_choose_thresholds_excludes_every_wrong_answer():
    """Thresholds are set so that no row that *would* be wrong gets answered.
        Makes sure the model never answers incorrectly by choosing the wrong thresh
    """
    label = np.array(["main", "main", "blank", "blank"])
    truth = np.array(["main", "blank", "blank", "blank"])   # index 1 is wrong
    conf = np.array([0.95, 0.60, 0.90, 0.85])
    dist = np.array([0.05, 0.05, 0.10, 0.20])

    prob_t, dist_t = choose_thresholds(label, conf, dist, truth)

    assert prob_t > 0.60                         # the wrong row's confidence is shut out
    answered = (conf >= prob_t) & (dist <= dist_t)
    assert not answered[1]                       # the wrong row is never answered
    assert answered[0] and answered[2]           # confident, nearby, correct rows still are

def test_choose_thresholds_treats_others_as_never_answerable():
    """A row whose truth is outside LABELS counts as "bad" even if the label matches.

    basically cards in other(`tests/integration/identify/pages/other/`) have no correct answer, so
    answering at all is an error.
    """
    label = np.array(["main", "main", "blank", "main"])
    truth = np.array(["main", "main", "blank", "other"])   # "other" is not in LABELS
    conf = np.array([0.99, 0.95, 0.90, 0.70])
    dist = np.array([0.05, 0.06, 0.20, 0.50])

    prob_t, dist_t = choose_thresholds(label, conf, dist, truth)

    answered = (conf >= prob_t) & (dist <= dist_t)
    assert not answered[3]               # the other card is kept out by distance
    assert answered[0] and answered[1]   # genuine pages close to the training set answer


def test_choose_thresholds_applies_the_distance_safety_margin():
    """The chosen distance is tightened by DIST_MARGIN before being returned.

    """
    label = np.array(["main", "blank"])
    truth = np.array(["main", "blank"])
    conf = np.array([0.9, 0.8])
    dist = np.array([0.2, 0.2])

    _, dist_t = choose_thresholds(label, conf, dist, truth)

    assert dist_t == pytest.approx(0.2 * (1 - DIST_MARGIN))

def test_choose_thresholds_with_no_correct_rows_answers_nothing():
    """If every row is wrong, coverage never improves on the initial best, so the
    gates stay at their opening values (prob 1.0, dist 0.0) -- abstain always."""
    label = np.array(["main", "main"])
    truth = np.array(["blank", "blank"])
    conf = np.array([0.9, 0.8])
    dist = np.array([0.1, 0.2])

    prob_t, dist_t = choose_thresholds(label, conf, dist, truth)

    assert prob_t == 1.0 and dist_t == 0.0

# ---------------------------------------------------------------- fit / cross_validate
def make_separable_dataset(per_class=6, dims=8, seed=0):
    """Four well-separated clusters, one per LABEL -- an easy, deterministic dataset.
        helper function
    """
    rng = np.random.default_rng(seed)
    X = np.concatenate([rng.normal(index * 10, 0.1, (per_class, dims))
                        for index in range(len(LABELS))]).astype(np.float32)
    y = np.array([label for label in LABELS for _ in range(per_class)])
    return X, y


def test_fit_learns_separable_classes_and_stores_the_training_set():
    """On obviously separable data the fitted model labels its own training rows correctly.
    """
    X, y = make_separable_dataset()

    model = Model.fit(X, y)

    assert list(model.classes) == list(LABELS)      # sklearn sorts them alphabetically
    assert model.reference.shape == X.shape
    np.testing.assert_allclose(np.linalg.norm(model.reference, axis=1), 1.0, atol=1e-5)
    assert (model.scores(X)[0] == y).all()

def test_fit_trains_the_head_only_on_known_labels():
    """other cards' rows tune the thresholds but never become a predictable class.
    """
    X, y = make_separable_dataset()
    rng = np.random.default_rng(1)
    X = np.vstack([X, rng.normal(-40, 0.1, (4, X.shape[1])).astype(np.float32)])
    y = np.concatenate([y, ["other"] * 4])

    model = Model.fit(X, y)

    assert "other" not in set(model.classes)
    assert set(model.predict(X[-4:])[0]) == {REVIEW}

def test_cross_validate_scores_every_row_including_others():
    """Cross-validation returns a held-out score for all rows
    """
    X, y = make_separable_dataset(per_class=10)
    rng = np.random.default_rng(2)
    X = np.vstack([X, rng.normal(-40, 0.1, (5, X.shape[1])).astype(np.float32)])
    y = np.concatenate([y, ["other"] * 5])

    label, conf, dist = cross_validate(X, y, folds=5)

    assert len(label) == len(conf) == len(dist) == len(y)
    assert (conf > 0).all()                      # every row really was scored
    assert (label[:40] == y[:40]).all()          # separable known rows are labelled correctly
    # other rows keep the REVIEW placeholder: `cross_validate` accumulates a
    # confidence and a distance for them (that is what the thresholds are tuned
    # against) but never records a class for them. Their *scores* are what
    # matters; giving them a label would imply the model can recognise them.
    assert set(label[40:]) == {REVIEW}

def test_regularisation_constant_is_the_documented_value():
    """ensure that a change in these constants raise an error to ensure there are no problems!
    """
    assert C == 0.5
    assert KNN == 5
    assert DIST_MARGIN == 0.10
    assert LABELS == ("blank", "coded", "main", "notes")
    assert REVIEW == "review"
