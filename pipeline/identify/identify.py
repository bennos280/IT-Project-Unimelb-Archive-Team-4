"""Which kind of page is an image? identify_pages() for the pipeline; the rest serves `survey train` and the tests."""
import hashlib
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from pipeline.common import IMAGES, ROOT
from pipeline.identify.fingerprint import CODE_HASH, fingerprint
from pipeline.identify.model import LABELS, REVIEW, WEIGHTS, Model

PAGES = ROOT / "tests" / "identify" / "pages"                       # labelled pages: pages/<label>/.../x.jpg
STORE = ROOT / "tests" / "identify" / "fingerprints" / CODE_HASH    # their fingerprints, committed, one file per image
MIN_COVERAGE = 0.5


@lru_cache(maxsize=1)
def model() -> Model:
    return Model.load()


def identify_pages(paths) -> list[dict]:
    """Per page: {"path", "label" (a LABEL or REVIEW), "confidence", "distance"}."""
    paths = [Path(p) for p in paths]
    labels, conf, dist = model().predict(fingerprint(paths)) if paths else ([], [], [])
    return [{"path": p, "label": str(l), "confidence": float(c), "distance": float(d)}
            for p, l, c, d in zip(paths, labels, conf, dist)]


# ---------------------------------------------------------------- training and scoring
def labelled_pages() -> tuple[list[Path], np.ndarray]:
    """Every image under PAGES with its truth = top folder (coded/layout_a/x.jpg -> coded)."""
    paths = [p for p in sorted(PAGES.rglob("*")) if p.suffix.lower() in IMAGES]
    return paths, np.array([p.relative_to(PAGES).parts[0] for p in paths])


def stored(paths, compute=False) -> np.ndarray:
    """Fingerprints of labelled pages from STORE, named by image bytes. compute=True fills the gaps (survey train)."""
    files = [STORE / (hashlib.sha1(p.read_bytes()).hexdigest()[:20] + ".npy") for p in paths]
    missing = [i for i, f in enumerate(files) if not f.exists()]
    if missing and not compute:
        raise FileNotFoundError(f"{len(missing)} pages have no fingerprint in {STORE.relative_to(ROOT)}: run `survey train`")
    if compute:
        STORE.mkdir(parents=True, exist_ok=True)
        for i, row in zip(missing, fingerprint([paths[i] for i in missing])):
            np.save(files[i], row.astype(np.float16))
        for stale in set(STORE.glob("*.npy")) - set(files):              # pages since removed
            stale.unlink()
        for old in STORE.parent.iterdir():                                 # fingerprints of older code
            if old != STORE and old.is_dir():
                shutil.rmtree(old)
    return np.stack([np.load(f).astype(np.float32) for f in files])


def held_out(X, truth, folds=5, seed=0) -> list[str]:
    """Train on 4/5, label the other 1/5, five times round: every page labelled by a model that never saw it."""
    from sklearn.model_selection import StratifiedKFold
    truth = np.asarray(truth)
    out = [REVIEW] * len(truth)
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=seed).split(X, truth):
        for i, label in zip(te, Model.fit(X[tr], truth[tr]).predict(X[te])[0]):
            out[i] = str(label)
    return out


@dataclass
class Score:
    total: int
    answered: int
    wrong: list                 # (page, said, truth)
    review: list                # (page, truth)
    per_class: dict             # truth -> (answered, total)

    @property
    def coverage(self) -> float:
        return self.answered / self.total if self.total else 0.0

    def passes(self) -> bool:
        return not self.wrong and self.coverage >= MIN_COVERAGE

    def summary(self, name: str = "") -> str:
        lines = [f"{name}: {self.answered}/{self.total} answered = {self.coverage:.1%}, {len(self.wrong)} wrong"]
        lines += [f"  {kind:6} {a:4d}/{n:4d} answered" for kind, (a, n) in self.per_class.items()]
        lines += [f"  REVIEW {p.name} (truth {t})" for p, t in self.review if t in LABELS]
        lines += [f"  WRONG  {p.name}: said {a}, truth {t}" for p, a, t in self.wrong]
        return "\n".join(lines)


def score(labels, truth, paths) -> Score:
    """Abstaining is never wrong. Answering a page whose truth is outside LABELS always is."""
    wrong, review, per_class = [], [], {}
    for path, label, t in zip(paths, labels, truth):
        a, n = per_class.get(t, (0, 0))
        if label == REVIEW:
            review.append((path, t))
        else:
            a += 1
            if label != t:
                wrong.append((path, label, t))
        per_class[t] = (a, n + 1)
    return Score(len(truth), len(truth) - len(review), wrong, review, dict(sorted(per_class.items())))


def train() -> int:
    """`survey train`: fingerprint new labelled pages, print the held-out score, fit on every page, save the weights."""
    paths, truth = labelled_pages()
    X = stored(paths, compute=True)
    result = score(held_out(X, truth), truth, paths)
    print(result.summary("held-out"))
    Model.fit(X, truth).save()
    print(f"wrote {WEIGHTS.relative_to(ROOT)} ({WEIGHTS.stat().st_size >> 20} MB)")
    return 0 if result.passes() else 1
