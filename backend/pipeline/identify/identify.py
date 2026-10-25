"""Which kind of page is an image? identify_pages() for the pipeline, train() for `survey train`, retrain() for retraining
from the review screen."""
import hashlib
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from backend.common import IMAGES, ROOT
from backend.pipeline.identify.fingerprint import CODE_HASH, fingerprint
from backend.pipeline.identify.classifier import LABELS, REVIEW, WEIGHTS, Model

PAGES = ROOT / "tests" / "integration" / "identify" / "pages"        # labelled pages: pages/<label>/.../x.jpg
STORE = ROOT / "tests" / "integration" / "identify" / "fingerprints" / CODE_HASH    # their fingerprints, committed, one file per image
MIN_COVERAGE = 0.5


@lru_cache(maxsize=4)
def model(weights=None) -> Model:
    return Model.load(weights or WEIGHTS)


def identify_pages(paths, weights=None) -> list[dict]:
    """Per page: {"path", "label" (a page type the model knows, or REVIEW), "confidence", "distance"}. weights: a
    retrained model's file; None: the shipped one."""
    paths = [Path(p) for p in paths]
    labels, conf, dist = model(weights).predict(fingerprint(paths)) if paths else ([], [], [])
    return [{"path": p, "label": str(label), "confidence": float(c), "distance": float(d)}
            for p, label, c, d in zip(paths, labels, conf, dist)]


# ---------------------------------------------------------------- training and scoring
def labelled_pages() -> tuple[list[Path], np.ndarray]:
    """Every image under PAGES with its truth = top folder (coded/layout_a/x.jpg -> coded)."""
    paths = [p for p in sorted(PAGES.rglob("*")) if p.suffix.lower() in IMAGES]
    return paths, np.array([p.relative_to(PAGES).parts[0] for p in paths])


def stored(paths, compute=False, store=None) -> np.ndarray:
    """Fingerprints of pages from store (default STORE), named by image bytes. compute=True fills the gaps (survey train,
    retraining)."""
    store = store or STORE
    files = [store / (hashlib.sha1(p.read_bytes()).hexdigest()[:20] + ".npy") for p in paths]
    missing = [i for i, f in enumerate(files) if not f.exists()]
    if missing and not compute:
        raise FileNotFoundError(f"{len(missing)} pages have no fingerprint in {store}: run `survey train`")
    if compute:
        store.mkdir(parents=True, exist_ok=True)
        for i, row in zip(missing, fingerprint([paths[i] for i in missing])):
            np.save(files[i], row.astype(np.float16))
        for stale in set(store.glob("*.npy")) - set(files):              # pages since removed
            stale.unlink()
        for old in store.parent.iterdir():                                 # fingerprints of older code
            if old != store and old.is_dir():
                shutil.rmtree(old)
    return np.stack([np.load(f).astype(np.float32) for f in files])


def held_out(X, truth, folds=5, seed=0, labels=LABELS) -> list[str]:
    """Train on 4/5, label the other 1/5, five times round: every page labelled by a model that never saw it."""
    from sklearn.model_selection import StratifiedKFold
    truth = np.asarray(truth)
    out = [REVIEW] * len(truth)
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=seed).split(X, truth):
        for i, label in zip(te, Model.fit(X[tr], truth[tr], labels).predict(X[te])[0]):
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


def retrain(confirmed, out: Path, store: Path) -> tuple[Score, tuple]:
    """Page sorting refitted on the labelled pages plus confirmed, (image, page type) pairs reviewers settled; it is
    written to out only if, page by page, a model that never saw the page answers no page wrong and at least
    MIN_COVERAGE of them. store: a folder of their fingerprints, apart from the committed STORE. -> the check's
    score and the page types the model sorts into."""
    paths, truth = labelled_pages()
    images = [Path(image) for image, _ in confirmed]
    X = np.vstack([stored(paths), stored(images, compute=True, store=store / CODE_HASH)]) if images else stored(paths)
    truth = np.concatenate([truth, [page_type for _, page_type in confirmed]]) if images else truth
    labels = tuple(sorted(set(LABELS) | {page_type for _, page_type in confirmed}))
    result = score(held_out(X, truth, labels=labels), truth, paths + images)
    if result.passes():
        out.parent.mkdir(parents=True, exist_ok=True)
        Model.fit(X, truth, labels).save(out)
    return result, labels
