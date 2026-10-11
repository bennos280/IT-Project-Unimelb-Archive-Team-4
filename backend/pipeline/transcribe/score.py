"""`survey score [--pages]`: every results/transcribe/<model>-<effort>/ against tests/transcribe/truth."""
import difflib
import json
import re
import sys

from backend.common import ROOT

TRUTH, ANSWERS = ROOT / "tests" / "integration" /"transcribe" / "truth", ROOT / "results" / "transcribe"
STAMPS = {"engine", "provider", "model", "effort", "seconds"}  # written by transcribe.py, not read off the card


def flatten(obj, prefix=""):
    """Nested dict/list -> {dotted.path: value}, so key and answer compare field by field."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def norm(v):
    """Collapse whitespace and case. Punctuation stays: `30/-` and `30/` differ on the cards."""
    return re.sub(r"\s+", " ", "" if v is None else str(v)).strip().casefold()


def scorable(path):
    return path not in STAMPS and not path.startswith("annotations[")


def score_page(key, answer):
    key, answer = flatten(key), flatten(answer)
    wanted = {p: v for p, v in key.items() if scorable(p) and v not in (None, "")}
    hits = {p for p, want in wanted.items() if norm(want) == norm(answer.get(p))}
    chars = [difflib.SequenceMatcher(None, norm(w), norm(answer.get(p))).ratio()
             for p, w in wanted.items()]
    blanks = [p for p, v in key.items() if scorable(p) and v in (None, "")]
    return {
        "total": len(wanted),
        "hits": len(hits),
        "missed": [p for p in wanted if p not in hits],
        "chars": chars,
        "blanks": len(blanks),
        "invented": [p for p in blanks if answer.get(p) not in (None, "")],
        "seconds": answer.get("seconds"),
    }


def main(show_pages):
    models = sorted(d.name for d in ANSWERS.iterdir() if d.is_dir()) if ANSWERS.exists() else []
    if not models:
        sys.exit("No results yet: survey transcribe <card> writes results/transcribe/<model>-<effort>/<page>.json")
    print(f"\n{'model':<16}{'kind':>7}{'exact':>16}{'chars':>7}{'invented':>10}"
          f"{'missing':>9}{'sec/page':>10}")
    for model in models:
        for kind_dir in sorted(TRUTH.iterdir()):
            pages = []
            for key_file in sorted(kind_dir.glob("*.json")):
                answer_file = ANSWERS / model / key_file.name
                if not answer_file.exists():
                    pages.append((key_file.stem, None))
                    continue
                key = json.loads(key_file.read_text(encoding="utf-8"))
                answer = json.loads(answer_file.read_text(encoding="utf-8"))
                pages.append((key_file.stem, score_page(key, answer)))
            done = [r for _, r in pages if r]
            if not done:
                continue
            total = sum(r["total"] for r in done)
            hits = sum(r["hits"] for r in done)
            chars = [c for r in done for c in r["chars"]]
            secs = [r["seconds"] for r in done if r["seconds"]]
            print(f"{model:<16}{kind_dir.name:>7}{f'{hits / total:.0%} ({hits}/{total})':>16}"
                  f"{sum(chars) / len(chars):>7.0%}"
                  f"{f'{sum(len(r['invented']) for r in done)}/{sum(r['blanks'] for r in done)}':>10}"
                  f"{len(pages) - len(done):>9}"
                  f"{f'{sum(secs) / len(secs):.0f}' if secs else '-':>10}")
            if show_pages:
                for page, r in pages:
                    if r is None:
                        print(f"    {page}  no answer")
                        continue
                    wrong = ", ".join(r["missed"] + [f"{p} (invented)" for p in r["invented"]])
                    print(f"    {page}  {r['hits']}/{r['total']}  {wrong}")
    print()


if __name__ == "__main__":
    main(show_pages="--pages" in sys.argv[1:])
