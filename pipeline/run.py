"""The `survey` command: split -> identify -> transcribe on each PDF. A step is one function on run.pages."""
import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.common import ROOT, find_images, settings
from pipeline.identify.model import REVIEW


@dataclass
class Run:
    input: Path                                          # the PDF, or a folder of page images
    out: Path
    images: Path | None = None                           # where the page images are, once split
    pages: list[dict] = field(default_factory=list)      # one record per page, in scan order
    review: list[dict] = field(default_factory=list)     # pages a human must check
    log: list[dict] = field(default_factory=list)

    def flag(self, page: dict, step: str, reason: str) -> None:
        self.review.append({"file": page["file"], "step": step, "reason": reason})

    def save(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        write(self.out / "manifest.json", {"input": str(self.input), "steps": self.log, "pages": self.pages})
        write(self.out / "review.json", self.review)


def write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- steps
def step_split(run: Run) -> None:
    """PDF -> one PNG per page under out/pages/. A folder of images is used as is."""
    if run.input.suffix.lower() != ".pdf":
        return
    import pymupdf
    folder = run.out / "pages"
    folder.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(run.input) as pdf:
        for i, page in enumerate(pdf, start=1):
            page.get_pixmap(dpi=200, alpha=False).save(folder / f"{run.input.stem}_{i:05d}.png")
    run.images = folder


def step_identify(run: Run) -> None:
    """Each page -> label main / notes / coded / blank, or review when the model isn't sure."""
    from pipeline.identify.identify import identify_pages
    images = find_images(run.images or run.input)
    run.pages = [{"file": p.name, "path": str(p)} for p in images]
    for page, r in zip(run.pages, identify_pages(images)):
        page.update(label=r["label"], confidence=r["confidence"], distance=r["distance"])
        if r["label"] == REVIEW:
            run.flag(page, "identify", "unlike any known page type; check highest distance first")


def step_transcribe(run: Run) -> None:
    """Each labelled page -> out/transcribe/<file>.json via the model in .env. Paid: only with --transcribe."""
    from pipeline.transcribe.run import transcribe
    folder = run.out / "transcribe"
    folder.mkdir(parents=True, exist_ok=True)
    for page in run.pages:
        if page.get("label") in ("main", "notes", "coded"):
            dest = folder / f"{Path(page['file']).stem}.json"
            write(dest, transcribe(Path(page["path"]), page["label"]))
            page["transcript"] = str(dest.relative_to(run.out))


STEPS = {"split": step_split, "identify": step_identify, "transcribe": step_transcribe}


def run_steps(run: Run, steps: list[str]) -> None:
    print(f"{run.input.name} -> {run.out}")
    for name in steps:
        started = time.perf_counter()
        STEPS[name](run)
        flagged = sum(r["step"] == name for r in run.review)
        run.log.append({"step": name, "seconds": round(time.perf_counter() - started, 1), "pages": len(run.pages), "flagged": flagged})
        run.save()
        print(f"  {name:10} {run.log[-1]['seconds']:7.1f}s  {len(run.pages)} pages, {flagged} for review")
    print(f"  {len(run.review)} page(s) for a human: {run.out / 'review.json'}")


# ---------------------------------------------------------------- the survey command
def unprocessed(folder: Path, output: Path) -> list[Path]:
    """PDFs (or folders of images) in DATA with no manifest under output yet."""
    if not folder.is_dir():
        sys.exit(f"DATA={folder} is not a folder; fix .env")
    candidates = sorted(p for p in folder.iterdir()
                        if p.resolve() != output.resolve()
                        and ((p.is_file() and p.suffix.lower() == ".pdf")
                             or (p.is_dir() and find_images(p))))
    if not candidates:
        sys.exit(f"{folder} is empty: put survey PDFs in it (https://archives.library.unimelb.edu.au/nodes/view/499420)")
    return [p for p in candidates if not (output / p.stem / "manifest.json").exists()]


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if args[:1] == ["train"]:
        from pipeline.identify.identify import train
        return train()
    if args[:1] == ["transcribe"]:
        from pipeline.transcribe.run import main as transcribe
        return transcribe(args[1:])
    if args[:1] == ["score"]:
        from pipeline.transcribe.score import main as score
        return score(show_pages="--pages" in args)

    parser = argparse.ArgumentParser(prog="survey", description=__doc__, epilog="or: survey train | transcribe <card> | score [--pages]")
    parser.add_argument("inputs", nargs="*", type=Path, help="PDFs or folders of page images; default: unprocessed PDFs in DATA")
    parser.add_argument("--transcribe", action="store_true", help="also transcribe (paid)")
    opts = parser.parse_args(args)

    config = settings()
    output = (ROOT / config["OUTPUT"]).resolve()
    inputs = opts.inputs or unprocessed(ROOT / config["DATA"], output)
    if missing := [p for p in inputs if not p.exists()]:
        sys.exit(f"not found: {missing[0]}")
    if not inputs:
        print(f"nothing to do: every PDF in DATA already has output under {output}")
        return 0
    steps = [s for s in STEPS if s != "transcribe" or opts.transcribe]
    print(f"{len(inputs)} to process -> {output}" + (f"   (MODEL={config['MODEL']})" if opts.transcribe else ""))
    for path in inputs:
        run_steps(Run(path.resolve(), output / path.stem), steps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
