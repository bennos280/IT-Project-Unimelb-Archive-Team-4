"""Linear head over the fingerprint plus two abstention gates (confidence, distance to the training pages):
the model answers REVIEW rather than guess."""
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

LABELS = ("blank", "coded", "main", "notes")
REVIEW = "review"
WEIGHTS = Path(__file__).with_name("weights.npz")
KNN = 5
DIST_MARGIN = 0.10          # tighten the chosen distance gate by this much; foreign forms sit right at it
C = 0.5


@dataclass
class Model:
    mean: np.ndarray
    std: np.ndarray
    coef: np.ndarray
    intercept: np.ndarray
    classes: np.ndarray
    reference: np.ndarray           # (M, D) unit-norm training fingerprints
    prob_threshold: float = 1.0
    dist_threshold: float = 0.0

    @classmethod
    def fit(cls, X: np.ndarray, y) -> "Model":
        """Thresholds from cross-validation inside (X, y); the head on the rows whose truth is a LABEL."""
        y = np.asarray(y)
        prob_t, dist_t = choose_thresholds(*cross_validate(X, y), y)
        known = np.isin(y, LABELS)
        return cls._head(X[known], y[known], prob_t, dist_t)

    @classmethod
    def _head(cls, X, y, prob_threshold=1.0, dist_threshold=0.0) -> "Model":
        from sklearn.linear_model import LogisticRegression
        mean, std = X.mean(0), X.std(0) + 1e-6
        clf = LogisticRegression(max_iter=5000, C=C).fit((X - mean) / std, y)
        return cls(mean, std, clf.coef_, clf.intercept_, clf.classes_, unit(X), prob_threshold, dist_threshold)

    def scores(self, X):
        """Per row: best label, softmax confidence, mean cosine distance to the KNN nearest training rows."""
        z = ((X - self.mean) / self.std) @ self.coef.T + self.intercept
        p = np.exp(z - z.max(1, keepdims=True))
        p /= p.sum(1, keepdims=True)
        d = np.sort(1 - unit(X) @ self.reference.T, 1)[:, :KNN].mean(1)
        return self.classes[p.argmax(1)], p.max(1), d

    def predict(self, X):
        """Per row: (label or REVIEW, confidence, distance)."""
        label, conf, dist = self.scores(X)
        ok = (conf >= self.prob_threshold) & (dist <= self.dist_threshold)
        return np.where(ok, label, REVIEW), conf, dist

    def save(self, path: Path = WEIGHTS) -> Path:
        np.savez_compressed(path, **{**asdict(self), "reference": self.reference.astype(np.float16)})
        return path

    @classmethod
    def load(cls, path: Path = WEIGHTS) -> "Model":
        if not path.exists():
            raise FileNotFoundError(f"{path} missing: run `survey train`")
        w = dict(np.load(path))
        w["reference"] = w["reference"].astype(np.float32)
        w["prob_threshold"], w["dist_threshold"] = float(w["prob_threshold"]), float(w["dist_threshold"])
        return cls(**w)


def unit(X: np.ndarray) -> np.ndarray:
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def cross_validate(X, y, folds=5, seed=0):
    """Held-out (label, confidence, distance) for every row. Rows whose truth is not a LABEL (foreign forms)
    are never trained on; every fold scores them and the scores are averaged."""
    from sklearn.model_selection import StratifiedKFold
    y = np.asarray(y)
    known = np.isin(y, LABELS)
    ki, oi = np.where(known)[0], np.where(~known)[0]
    label, conf, dist = np.full(len(y), REVIEW, object), np.zeros(len(y)), np.zeros(len(y))
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=seed).split(ki, y[ki]):
        tr, te = ki[tr], ki[te]
        head = Model._head(X[tr], y[tr])
        label[te], conf[te], dist[te] = head.scores(X[te])
        if oi.size:
            _, c, d = head.scores(X[oi])
            conf[oi] += c / folds
            dist[oi] += d / folds
    return label, conf, dist


def choose_thresholds(label, conf, dist, truth) -> tuple[float, float]:
    """(prob_t, dist_t) with the largest coverage and no answered row wrong, distance then DIST_MARGIN tighter."""
    truth = np.asarray(truth)
    bad = (np.asarray(label) != truth) | ~np.isin(truth, LABELS)
    best = (0.0, 1.0, 0.0)
    for d in np.unique(dist):
        worst = conf[bad & (dist <= d)]
        t = float(worst.max()) + 1e-6 if worst.size else 0.0
        cov = float(((dist <= d) & (conf >= t)).mean())
        if cov > best[0]:
            best = (cov, t, float(d))
    _, t, d = best
    return t, d * (1 - DIST_MARGIN)
