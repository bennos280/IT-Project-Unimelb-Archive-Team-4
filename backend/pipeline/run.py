"""The `survey` command: split -> identify -> preprocess -> transcribe -> group on each PDF. A step is one function on run.pages."""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import repeat
from pathlib import Path
from types import SimpleNamespace

from backend import scans
from backend.common import ROOT, find_images, settings
from backend.pipeline.identify.classifier import REVIEW
from backend.pipeline.preprocess.options import add_arguments, resolve_options

READERS = 16  # pages transcribed at once


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
    texts: dict[str, str] | None = None                  # the prompt and templates to read with (a job: the db's); None: the files
    sorting_model: Path | None = None                    # retrained page sorting's weights; None: the shipped model
    progress: Callable[[str, int, int], None] = lambda step, done, total: None  # told (step, pages done, pages to do)

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
    return isinstance(log, list) and all(name in [entry.get("step") for entry in log if isinstance(entry, dict)] for name in steps)


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- steps
def render(pdf_path: Path, numbers: range, folder: Path) -> None:
    """Draws these pages (counting from 0) of a PDF as PNGs in folder."""
    import pymupdf
    with pymupdf.open(pdf_path) as pdf:
        for n in numbers:
            pdf[n].get_pixmap(dpi=200, alpha=False).save(folder / f"{pdf_path.stem}_{n + 1:05d}.png")


def step_split(run: Run) -> None:
    """PDF -> one PNG per page under out/pages/; a PDF not on this computer is downloaded from the archive into its place
    (the bundle number is its folder). A folder of images is used as is."""
    if run.input.suffix.lower() != ".pdf":
        return
    import pymupdf
    if not run.input.exists():
        try:
            scans.fetch_pdf(run.input)
        except scans.ARCHIVE_ERRORS as error:
            raise SystemExit(f"bundle {run.input.parent.name}'s PDF isn't on this computer, and the archive couldn't send it ({error})")
    folder = run.out / "pages"
    run.out.mkdir(parents=True, exist_ok=True)
    work = tempfile.TemporaryDirectory(prefix=".split-", dir=run.out, delete=False)
    pending, previous = Path(work.name) / "pages", Path(work.name) / "previous"
    try:
        pending.mkdir()
        with pymupdf.open(run.input) as pdf:
            count = pdf.page_count
        chunks = [range(start, min(start + 16, count)) for start in range(0, count, 16)]
        if len(chunks) <= 1:  # not worth starting processes for
            render(run.input, range(count), pending)
        else:  # a chunk of 16 pages per process, on every core
            with ProcessPoolExecutor(min(len(chunks), os.cpu_count() or 1)) as pool:
                list(pool.map(render, repeat(run.input), chunks, repeat(pending)))
        # swap in the new pages; the old ones stay until this succeeds
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
        # a failed restore leaves the backup in place
        if not previous.exists() or folder.exists():
            work.cleanup()
    run.images = folder


def step_identify(run: Run) -> None:
    """Each page -> label main / notes / coded / blank (or a page type sorting was retrained on), or review when the
    model isn't sure."""
    from backend.pipeline.identify.identify import identify_pages
    images = find_images(run.images or run.input)
    run.pages = [{"file": p.name, "path": str(p)} for p in images]
    for page, r in zip(run.pages, identify_pages(images, run.sorting_model)):
        page.update(label=r["label"], confidence=r["confidence"], distance=r["distance"])
        if r["label"] == REVIEW:
            run.flag(page, "identify", "unlike any known page type; check highest distance first")

def step_preprocess(run: Run) -> None:
    """Prepare page images for transcription, keeping originals unchanged."""
    import cv2
    from backend.pipeline.preprocess.preprocess import process_image

    folder = run.out / "preprocessed"
    folder.mkdir(parents=True, exist_ok=True)

    options = run.preprocess_options
    if options is None:
        raise ValueError("Preprocessing options were not configured")

    from backend.pipeline.transcribe.transcribe import read_texts
    readable = (run.texts or read_texts()).keys() - {"prompt"} #the page types with a template
    for page in run.pages:
        if page.get("label") not in readable:
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
    """Each labelled page -> out/transcribe/<file>.json, READERS at a time, each saved as soon as it is read (paid: only
    with --transcribe). A failed page stops the step once the reads under way are saved."""
    from backend.pipeline.transcribe.transcribe import read_texts, transcribe
    config = settings()
    texts = run.texts or read_texts()
    folder = run.out / "transcribe"
    folder.mkdir(parents=True, exist_ok=True)
    pages = [page for page in run.pages if page.get("label") in texts.keys() - {"prompt"}]
    todo = []
    for page in pages:
        image, kind = Path(page["path"]), page["label"]
        dest = folder / f"{Path(page['file']).stem}.json"
        request = {"image": digest(image), "label": kind,
                   "model": config["MODEL"], "effort": config["EFFORT"],
                   "prompt": text_digest(texts["prompt"]),
                   "template": text_digest(texts[kind])}
        saved = run.transcripts.get(page["file"])
        if isinstance(saved, dict) and saved.get("request") == request and dest.is_file() and saved.get("result") == digest(dest):
            page["transcript"] = str(dest.relative_to(run.out))
        else:
            todo.append((page, image, kind, dest, request))
    run.save()
    done, failure = len(pages) - len(todo), None
    run.progress("transcribe", done, len(pages))
    with ThreadPoolExecutor(READERS) as pool:
        reads = {pool.submit(transcribe, image, kind, provider=config["PROVIDER"], model=config["MODEL"], effort=config["EFFORT"], texts=texts): (page, dest, request)
                 for page, image, kind, dest, request in todo}
        try:
            for read in as_completed(reads):
                page, dest, request = reads[read]
                try:
                    answer = read.result()
                except BaseException as error:  # a failed model call raises SystemExit
                    failure = failure or error
                    for other in reads:  # not pool.shutdown: its cancelled reads would leave as_completed waiting forever
                        other.cancel()
                    continue
                write(dest, answer)
                run.transcripts[page["file"]] = {"request": request, "result": digest(dest)}
                page["transcript"] = str(dest.relative_to(run.out))
                run.save()
                done += 1
                run.progress("transcribe", done, len(pages))
        except BaseException:  # stopped, or saving or reporting failed: don't pay for the reads still queued
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    if failure:
        raise failure


def step_group(run: Run) -> None:
    """Pages -> surveys. A main form starts a survey and the pages after it join it, except coded cards; a main form
    with no new dwelling number, not straight after a coded card, is a second sheet of the same survey. A flat
    letter is part of the number (24A is not 24B). A coded card joins the survey before or after it whose main form
    has its dwelling number, else the only survey anywhere with that number that no neighbouring card matched,
    else the neighbour no card matched, else the side most matched cards joined."""
    surveys, cards, last = [], [], None
    for i, page in enumerate(run.pages):
        page["survey"], found = None, set()
        if page.get("transcript"):
            answer = json.loads((run.out / page["transcript"]).read_text(encoding="utf-8"))
            text = str(answer.get("number_of_dwelling") or "")
            found = {n.lstrip("0") + flat.upper() for n, flat in re.findall(r"(\d+)\s*([A-Za-z]?)(?![A-Za-z])", text)} - {""}
        if page["label"] == "coded":
            cards.append((i, page, found))
        elif page["label"] == "main" and (not surveys or last == "coded" or not found <= surveys[-1]["main"]):
            surveys.append({"start": i, "pages": [page], "main": set(found), "card": set()})
        elif surveys:
            surveys[-1]["pages"].append(page)
            if page["label"] == "main":
                surveys[-1]["main"] |= found
        if page["label"] != "blank":
            last = page["label"]
    beside = {}  # card index -> (index of the first survey after it, index of the one neighbour matching it or None)
    for i, _, found in cards:
        k = sum(s["start"] < i for s in surveys)
        match = [j for j in (k - 1, k) if 0 <= j < len(surveys) and found & surveys[j]["main"]]
        beside[i] = (k, match[0] if len(match) == 1 else None)
    matched = [(k, j) for k, j in beside.values() if j is not None]
    after = sum(j == k for k, j in matched) * 2 > len(matched)
    claimed = {j for _, j in matched}
    for i, page, found in cards:
        k, j = beside[i]
        if j is None and surveys:
            far = [n for n, s in enumerate(surveys) if found & s["main"] and n not in claimed]
            free = [n for n in (k - 1, k) if 0 <= n < len(surveys) and n not in claimed]
            j = far[0] if len(far) == 1 else free[0] if len(free) == 1 else min(k, len(surveys) - 1) if after else max(k - 1, 0)
        if j is not None:
            surveys[j]["pages"].append(page)
            surveys[j]["card"] |= found
    taken = set()
    for s in surveys:
        coded = sum(p["label"] == "coded" for p in s["pages"])
        number = max(sorted(s["main"] & s["card"] or s["card"] or s["main"]), key=len, default="")
        name = f"{run.input.stem}-{number}"
        problems = [f"{coded} coded cards"] if coded != 1 else []
        if coded and number and not s["main"] & s["card"]:
            problems.append("its main form and coded card do not show the same dwelling number")
        if not number or name in taken:
            problems.append(f"dwelling number {number} is also used by an earlier survey in this bundle" if number
                            else "no dwelling number")
            name = Path(s["pages"][0]["file"]).stem
        taken.add(name)
        for p in s["pages"]:
            p["survey"] = name
        if problems:
            run.flag(s["pages"][0], "group", f"survey {name}: " + "; ".join(problems))
    loose = [p for p in run.pages if p["survey"] is None and p["label"] != "blank"]
    if loose:
        run.flag(loose[0], "group", f"{len(loose)} page(s) before the first main form belong to no survey")


STEPS = {"split": step_split, "identify": step_identify, "preprocess": step_preprocess, "transcribe": step_transcribe, "group": step_group}
FULL = [step for step in STEPS if step != "preprocess"]  # a full run: what a job does, and what a run needs before it is loaded


def run_steps(run: Run, steps: list[str]) -> None:
    print(f"{run.input.name} -> {run.out}")
    saved = read_manifest(run.out).get("transcripts", {})
    run.transcripts = saved if isinstance(saved, dict) else {}
    run.log.clear()
    run.pages.clear()
    run.review.clear()
    run.images = None
    run.save()  # the old run counts as unfinished until this one is
    for name in steps:
        started = time.perf_counter()
        run.progress(name, 0, 0)
        STEPS[name](run)
        flagged = sum(r["step"] == name for r in run.review)
        run.log.append({"step": name, "seconds": round(time.perf_counter() - started, 1), "pages": len(run.pages), "flagged": flagged})
        run.save()
        print(f"  {name:10} {run.log[-1]['seconds']:7.1f}s  {len(run.pages)} pages, {flagged} for review")
    print(f"  {len(run.review)} page(s) for a human: {run.out / 'review.json'}")


# ---------------------------------------------------------------- the survey command
def unprocessed(folder: Path, output: Path, steps: list[str] | None = None) -> list[Path]:
    """PDFs anywhere in DATA (as DATA/<bundle>/<pdf>), and folders of images in it, whose requested steps have not all
    finished."""
    if steps is None:
        steps = ["split", "identify"]
    if not folder.is_dir():
        sys.exit(f"DATA={folder} is not a folder; fix .env")
    out = output.resolve()
    candidates = sorted([p for p in folder.rglob("*.pdf") if out not in p.resolve().parents]
                        + [p for p in folder.iterdir() if p.is_dir() and p.resolve() != out and find_images(p)])
    if not candidates:
        sys.exit(f"{folder} is empty: put survey PDFs in it (https://archives.library.unimelb.edu.au/nodes/view/499420)")
    return [p for p in candidates if not completed(output / p.stem, steps)]


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if args[:1] == ["train"]:
        from backend.pipeline.identify.identify import train
        return train()
    if args[:1] == ["preprocess"]:
        from backend.pipeline.preprocess.preprocess import main as preprocess
        return preprocess(args[1:])
    if args[:1] == ["transcribe"]:
        from backend.pipeline.transcribe.transcribe import main as transcribe
        return transcribe(args[1:])
    if args[:1] == ["score"]:
        from backend.pipeline.transcribe.score import main as score
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
             and (s not in ("transcribe", "group") or opts.transcribe)]  # group reads the transcripts
    inputs = opts.inputs or unprocessed(ROOT / config["DATA"], output, steps)
    if missing := [p for p in inputs if not p.exists()]:
        sys.exit(f"not found: {missing[0]}")
    if not inputs:
        print(f"nothing to do: every input in DATA has completed the requested steps under {output}")
        return 0
    print(f"{len(inputs)} to process -> {output}" + (f"   ({config['PROVIDER']}: {config['MODEL']})" if opts.transcribe else ""))
    for path in inputs:
        run_steps(Run(path.resolve(), output / path.stem, preprocess_options=preprocess_options,),steps,)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
