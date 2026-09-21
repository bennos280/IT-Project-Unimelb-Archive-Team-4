"""The `survey` command: split -> preprocess -> identify -> transcribe on each PDF. A step is one function on run.pages."""
import argparse
import hashlib
import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from pipeline.common import ROOT, find_images, settings
from pipeline.identify.model import REVIEW
from pipeline.preprocess.options import add_arguments, resolve_options


@dataclass
class Run:
    input: Path                                          # the PDF, or a folder of page images
    out: Path
    images: Path | None = None                           # where the page images are, once split
    pages: list[dict] = field(default_factory=list)      # one record per page, in scan order
    review: list[dict] = field(default_factory=list)     # pages a human must check
    log: list[dict] = field(default_factory=list)
    transcripts: dict[str, dict] = field(default_factory=dict)  # reusable completed page results
    preprocess_options: SimpleNamespace | None = None    # Preprocessing settings, if provided.

    def flag(self, page: dict, step: str, reason: str) -> None:
        self.review.append({"file": page["file"], "step": step, "reason": reason})

    def save(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        write(self.out / "review.json", self.review)
        write(self.out / "manifest.json", {"input": str(self.input), "steps": self.log,
                                           "pages": self.pages, "transcripts": self.transcripts})


def write(path: Path, data) -> None:
    """Publish complete JSON so an interrupted write cannot truncate the previous file."""
    with tempfile.TemporaryDirectory(prefix=".write-", dir=path.parent) as work:
        pending = Path(work) / path.name
        pending.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        pending.replace(path)


def read_manifest(out: Path) -> dict:
    try:
        saved = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def completed(out: Path, steps: list[str]) -> bool:
    log = read_manifest(out).get("steps", [])
    return isinstance(log, list) and all(
        any(isinstance(entry, dict) and entry.get("step") == name for entry in log)
        for name in steps)


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


# ---------------------------------------------------------------- steps
def step_split(run: Run) -> None:
    """PDF -> one PNG per page under out/pages/. A folder of images is used as is."""
    if run.input.suffix.lower() != ".pdf":
        return
    import pymupdf
    folder = run.out / "pages"
    run.out.mkdir(parents=True, exist_ok=True)
    work = tempfile.TemporaryDirectory(prefix=".split-", dir=run.out, delete=False)
    pending, previous = Path(work.name) / "pages", Path(work.name) / "previous"
    try:
        pending.mkdir()
        with pymupdf.open(run.input) as pdf:
            for i, page in enumerate(pdf, start=1):
                page.get_pixmap(dpi=200, alpha=False).save(pending / f"{run.input.stem}_{i:05d}.png")
        # Both directories are under this run's output, on the same filesystem.
        # Keep the old images until rendering and publication have succeeded.
        try:
            if folder.exists():
                folder.rename(previous)
            pending.rename(folder)
        except BaseException as error:
            if previous.exists() and not folder.exists():
                try:
                    previous.rename(folder)
                except OSError as restore_error:
                    error.add_note(f"Previous page images kept at {previous}: {restore_error}")
            raise
    finally:
        # If restoration was blocked too, leave the backup available for recovery.
        if not previous.exists() or folder.exists():
            work.cleanup()
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

def step_preprocess(run: Run) -> None:
    """Prepare page images for transcription, keeping originals unchanged."""
    import cv2
    from pipeline.preprocess.preprocess import process_image

    folder = run.out / "preprocessed"
    folder.mkdir(parents=True, exist_ok=True)

    options = run.preprocess_options
    if options is None:
        raise ValueError("Preprocessing options were not configured")

    for page in run.pages:
        if page.get("label") not in ("main", "notes", "coded"):
            continue

        source = Path(page["path"])
        destination = folder / f"{Path(page['file']).stem}_preprocessed.png"

        try:
            with tempfile.TemporaryDirectory(
                prefix=".preprocess-", dir=run.out
            ) as work:
                pending = Path(work) / destination.name
                report = process_image(source, pending, options)
                pending.replace(destination)

        except (OSError, ValueError, cv2.error) as exc:
            run.flag(page, "preprocess", str(exc))
            run.save()
            raise RuntimeError(
                f"Preprocessing failed for {page['file']}: {exc}"
            ) from exc

        report["output"] = str(destination)
        page["original_path"] = str(source)
        page["path"] = str(destination)
        page["preprocessing"] = report

def step_transcribe(run: Run) -> None:
    """Each labelled page -> out/transcribe/<file>.json via the model in .env. Paid: only with --transcribe."""
    from pipeline.transcribe.run import HERE, transcribe
    config = settings()
    folder = run.out / "transcribe"
    folder.mkdir(parents=True, exist_ok=True)
    for page in run.pages:
        if page.get("label") in ("main", "notes", "coded"):
            image, kind = Path(page["path"]), page["label"]
            dest = folder / f"{Path(page['file']).stem}.json"
            request = {"image": digest(image), "label": kind,
                       "model": config["MODEL"], "effort": config["EFFORT"],
                       "prompt": digest(HERE / "prompt.txt"),
                       "template": digest(HERE / "templates" / f"{kind}.json")}
            saved = run.transcripts.get(page["file"])
            if not (isinstance(saved, dict) and saved.get("request") == request
                    and dest.is_file() and saved.get("result") == digest(dest)):
                write(dest, transcribe(image, kind, model=config["MODEL"], effort=config["EFFORT"]))
                run.transcripts[page["file"]] = {"request": request, "result": digest(dest)}
            page["transcript"] = str(dest.relative_to(run.out))
            run.save()


STEPS = {"split": step_split, "identify": step_identify, "preprocess": step_preprocess, "transcribe": step_transcribe}


def run_steps(run: Run, steps: list[str]) -> None:
    print(f"{run.input.name} -> {run.out}")
    saved = read_manifest(run.out).get("transcripts", {})
    run.transcripts = saved if isinstance(saved, dict) else {}
    run.log.clear()
    run.pages.clear()
    run.review.clear()
    run.images = None
    run.save()  # Invalidate old completion before any work, including PDF rendering.
    for name in steps:
        started = time.perf_counter()
        STEPS[name](run)
        flagged = sum(r["step"] == name for r in run.review)
        run.log.append({"step": name, "seconds": round(time.perf_counter() - started, 1), "pages": len(run.pages), "flagged": flagged})
        run.save()
        print(f"  {name:10} {run.log[-1]['seconds']:7.1f}s  {len(run.pages)} pages, {flagged} for review")
    print(f"  {len(run.review)} page(s) for a human: {run.out / 'review.json'}")


# ---------------------------------------------------------------- the survey command
def unprocessed(folder: Path, output: Path, steps: list[str] | None = None) -> list[Path]:
    """PDFs (or folders of images) in DATA whose requested steps have not all finished."""
    if steps is None:
        steps = ["split", "identify"]
        
    if not folder.is_dir():
        sys.exit(f"DATA={folder} is not a folder; fix .env")
    candidates = sorted(p for p in folder.iterdir()
                        if p.resolve() != output.resolve()
                        and ((p.is_file() and p.suffix.lower() == ".pdf")
                             or (p.is_dir() and find_images(p))))
    if not candidates:
        sys.exit(f"{folder} is empty: put survey PDFs in it (https://archives.library.unimelb.edu.au/nodes/view/499420)")
    return [p for p in candidates if not completed(output / p.stem, steps)]


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if args[:1] == ["train"]:
        from pipeline.identify.identify import train
        return train()
    if args[:1] == ["preprocess"]:
        from pipeline.preprocess.preprocess import main as preprocess
        return preprocess(args[1:])
    if args[:1] == ["transcribe"]:
        from pipeline.transcribe.run import main as transcribe
        return transcribe(args[1:])
    if args[:1] == ["score"]:
        from pipeline.transcribe.score import main as score
        return score(show_pages="--pages" in args)

    parser = argparse.ArgumentParser(prog="survey", description=__doc__, epilog="or: survey train | transcribe <card> | score [--pages]")
    parser.add_argument("inputs", nargs="*", type=Path, help="PDFs or folders of page images; default: unprocessed PDFs in DATA")
    parser.add_argument("--transcribe", action="store_true", help="also transcribe (paid)")
    parser.add_argument("--preprocess",action="store_true", help="Crop, straighten, and binarize images before transcription",)
    add_arguments(parser)
    opts = parser.parse_args(args)

    config = settings()

    if not opts.preprocess and any(
        value is not None
        for value in (
            opts.preprocess_mode,
            opts.no_deskew,
            opts.no_crop,
            opts.c,
        )
    ):
        parser.error("These image options require --preprocess")

    preprocess_options = None
    if opts.preprocess:
        try:
            preprocess_options = resolve_options(opts, config)
        except ValueError as exc:
            parser.error(str(exc))

    output = (ROOT / config["OUTPUT"]).resolve()
    steps = [s for s in STEPS if (s != "preprocess" or opts.preprocess) 
             and (s != "transcribe" or opts.transcribe)]
    inputs = opts.inputs or unprocessed(ROOT / config["DATA"], output, steps)
    if missing := [p for p in inputs if not p.exists()]:
        sys.exit(f"not found: {missing[0]}")
    if not inputs:
        print(f"nothing to do: every input in DATA has completed the requested steps under {output}")
        return 0
    print(f"{len(inputs)} to process -> {output}" + (f"   (MODEL={config['MODEL']})" if opts.transcribe else ""))
    for path in inputs:
        run_steps(Run(path.resolve(), output / path.stem, preprocess_options=preprocess_options,),steps,)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
