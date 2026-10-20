"""Page sorting by the reading model, in place of the page sorting model on this computer (PyTorch): each page is shown to
the transcription provider with its series' page types, and it names one, or says the page is blank, or that it can't tell
(the page then waits for review, as one the model on this computer can't place does)."""
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.pipeline.identify.classifier import REVIEW
from backend.pipeline.run import READERS
from backend.pipeline.transcribe.transcribe import ask

BLANK = "blank: nothing written or printed on it"


def prompt_for(types):
    """What the reading model is asked: the series' page types ({name: label}), blank, and unsure."""
    kinds = "\n".join(f"- {name}: {label}" for name, label in types.items())
    return ("This is one scanned page of an item from an archive. Which kind of page is it? Answer with just the name, "
            f"before the colon, in page_type:\n{kinds}\n- {BLANK}\n- unsure: none of these, or you can't tell")


def sort_pages(paths, types, choice, progress=lambda done, total: None):
    """Per page, in order, as identify_pages gives it: {"path", "label" (one of types' names, blank, or REVIEW), "confidence",
    "distance"}. choice: {"provider", "model", "effort"}; READERS pages are asked at once and progress is told each page done.
    A page whose request fails is REVIEW; when every request fails, the first one's error is raised."""
    prompt = prompt_for(types)
    def page(path, label):
        return {"path": path, "label": label, "confidence": 0.0 if label == REVIEW else 1.0, "distance": 0.0}
    def sort(path):
        said = str(ask(path, prompt, {"page_type": None}, **choice).get("page_type") or "").strip().lower()
        return page(path, said if said in types or said == "blank" else REVIEW)
    answers, failures = [None] * len(paths), {}
    with ThreadPoolExecutor(READERS) as pool:
        asked = {pool.submit(sort, path): i for i, path in enumerate(paths)}
        for done, request in enumerate(as_completed(asked), 1):
            i = asked[request]
            try:
                answers[i] = request.result()
            except BaseException as error:  # a failed model call raises SystemExit
                failures[i] = error
                answers[i] = page(paths[i], REVIEW)
            progress(done, len(paths))
    if paths and len(failures) == len(paths):
        raise failures[min(failures)]
    return answers
