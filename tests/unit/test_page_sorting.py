"""Pages are sorted into page types on this computer (PyTorch) or by the reading model, as chosen on the Settings page."""
import time
from pathlib import Path

import pytest

from backend.db import app_settings
from backend.pipeline import run as pipeline
from backend.pipeline.identify import by_model


def test_the_reading_model_names_each_pages_type_or_says_blank_and_anything_else_waits_for_review(monkeypatch):
    asked = []
    answers = iter([{"page_type": "Letter "}, {"page_type": "blank"}, {"page_type": "unsure"}, {"page_type": "envelope"}])
    monkeypatch.setattr(by_model, "ask", lambda image, prompt, template, **choice: asked.append((image, prompt, template, choice)) or next(answers))
    done = []
    sorted_pages = by_model.sort_pages(["a.png", "b.png", "c.png", "d.png"], {"letter": "Letter", "note": "Note"},
                                       {"provider": "openai", "model": "m", "effort": "default"}, lambda d, t: done.append((d, t)))
    assert [p["label"] for p in sorted_pages] == ["letter", "blank", "review", "review"]  # envelope isn't one of the series'
    assert [p["confidence"] for p in sorted_pages] == [1.0, 1.0, 0.0, 0.0]
    image, prompt, template, choice = asked[0]
    assert (image, template, choice) == ("a.png", {"page_type": None}, {"provider": "openai", "model": "m", "effort": "default"})
    assert "- letter: Letter\n- note: Note\n- blank:" in prompt and "- unsure:" in prompt
    assert done == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_pages_are_asked_of_the_reading_model_at_once_and_come_back_in_order(monkeypatch):
    import threading
    at_once, peak, lock = 0, 0, threading.Lock()
    def ask(image, prompt, template, **choice):
        nonlocal at_once, peak
        with lock:
            at_once += 1
            peak = max(peak, at_once)
        time.sleep(0.05)
        with lock:
            at_once -= 1
        return {"page_type": "letter" if image in ("a.png", "c.png") else "blank"}
    monkeypatch.setattr(by_model, "ask", ask)
    monkeypatch.setattr(by_model, "READERS", 3)
    done = []
    sorted_pages = by_model.sort_pages(["a.png", "b.png", "c.png", "d.png", "e.png"], {"letter": "Letter"}, {}, lambda d, t: done.append((d, t)))
    assert [p["path"] for p in sorted_pages] == ["a.png", "b.png", "c.png", "d.png", "e.png"]
    assert [p["label"] for p in sorted_pages] == ["letter", "blank", "letter", "blank", "blank"]
    assert 1 < peak <= 3
    assert done == [(n, 5) for n in range(1, 6)]


def test_a_page_whose_request_fails_waits_for_review_unless_every_request_fails(monkeypatch):
    def ask(image, prompt, template, **choice):
        if image != "b.png":
            return {"page_type": "letter"}
        raise SystemExit("rate limited")
    monkeypatch.setattr(by_model, "ask", ask)
    done = []
    sorted_pages = by_model.sort_pages(["a.png", "b.png", "c.png"], {"letter": "Letter"}, {}, lambda d, t: done.append(d))
    assert [(p["label"], p["confidence"]) for p in sorted_pages] == [("letter", 1.0), ("review", 0.0), ("letter", 1.0)]
    assert done == [1, 2, 3]

    def not_signed_in(image, prompt, template, **choice):
        raise SystemExit(f"not signed in ({image})")
    monkeypatch.setattr(by_model, "ask", not_signed_in)
    with pytest.raises(SystemExit, match=r"not signed in \(a.png\)"):
        by_model.sort_pages(["a.png", "b.png"], {"letter": "Letter"}, {})


def test_a_run_set_to_the_reading_model_sorts_with_it_and_flags_what_it_cant_place(tmp_path, monkeypatch):
    for n in (1, 2):
        (tmp_path / f"b_{n:05d}.png").write_bytes(b"")
    told = {}
    def sort_pages(paths, types, choice, progress):
        told.update(types=types, choice=choice)
        return [{"path": p, "label": label, "confidence": 1.0, "distance": 0.0} for p, label in zip(paths, ["letter", "review"])]
    monkeypatch.setattr(by_model, "sort_pages", sort_pages)
    run = pipeline.Run(tmp_path, tmp_path / "out", sorting="model", page_type_labels={"letter": "Letter"}, page_types={"letter", "blank"})
    run.transcription_config = {"PROVIDER": "claude", "MODEL": "sonnet", "EFFORT": "low"}
    pipeline.step_identify(run)
    assert [p["label"] for p in run.pages] == ["letter", "review"]
    assert [r["file"] for r in run.review] == ["b_00002.png"]
    assert told == {"types": {"letter": "Letter"}, "choice": {"provider": "claude", "model": "sonnet", "effort": "low"}}


def test_page_sorting_is_by_the_reading_model_until_this_computer_is_chosen(client, monkeypatch):
    assert client.get("/page-sorting").json() == {"method": "model", "unsure": "review", "sorter": None, "localAvailable": True,
                                                    "checked": None}  # unsaved, the reading model, as transcription
    assert client.put("/page-sorting", json={"method": "local"}).json()["method"] == "local"
    assert client.get("/page-sorting").json()["method"] == "local"
    assert client.put("/page-sorting", json={"method": "elsewhere"}).status_code == 422


def test_without_pytorch_pages_are_sorted_by_the_reading_model_and_this_computer_cant_be_chosen(client, monkeypatch):
    monkeypatch.setattr(app_settings, "local_sorting_available", lambda: False)
    assert client.get("/page-sorting").json()["method"] == "model" and not client.get("/page-sorting").json()["localAvailable"]
    refused = client.put("/page-sorting", json={"method": "local"})
    assert (refused.status_code, refused.json()["detail"]) == (400, "PyTorch isn't installed on this computer, so pages can't be sorted here.")


def test_a_cheaper_reading_model_can_sort_and_what_this_computer_isnt_sure_of_can_go_to_it(client):
    sorter = {"provider": "anthropic", "model": "claude-haiku-4-5", "effort": "default"}
    saved = client.put("/page-sorting", json={"sorter": sorter, "unsure": "model"}).json()
    assert (saved["method"], saved["sorter"], saved["unsure"]) == ("model", sorter, "model")  # the method left as it was
    assert client.put("/page-sorting", json={"sameAsTranscription": True}).json()["sorter"] is None
    assert client.put("/page-sorting", json={"sorter": {**sorter, "provider": "nobody"}}).status_code == 400


def test_pages_this_computer_isnt_sure_of_are_asked_of_the_reading_model_when_set(tmp_path, monkeypatch):
    from backend.pipeline.identify import identify
    for n in (1, 2, 3):
        (tmp_path / f"b_{n:05d}.png").write_bytes(b"")
    monkeypatch.setattr(identify, "identify_pages", lambda images, model=None: [
        {"path": p, "label": label, "confidence": 0.5, "distance": 0.0} for p, label in zip(images, ["main", "review", "docket"])])
    asked = []
    def sort_pages(paths, types, choice, progress):
        asked.append(([Path(p).name for p in paths], choice))
        return [{"path": p, "label": "notes", "confidence": 1.0, "distance": 0.0} for p in paths]
    monkeypatch.setattr(by_model, "sort_pages", sort_pages)
    run = pipeline.Run(tmp_path, tmp_path / "out", sorting="local", unsure_to_model=True, page_types={"main", "notes"},
                       sorter={"provider": "gemini", "model": "flash", "effort": "default"})
    pipeline.step_identify(run)
    assert [p["label"] for p in run.pages] == ["main", "notes", "notes"]  # unsure, and a type the series hasn't: asked
    assert asked == [(["b_00002.png", "b_00003.png"], {"provider": "gemini", "model": "flash", "effort": "default"})]


def test_checks_asked_for_at_once_load_the_sorting_model_once_and_its_pass_is_remembered(client, monkeypatch):
    import threading
    from backend.api import main
    from backend.pipeline.identify import identify
    monkeypatch.setattr(main, "_checked", {})
    monkeypatch.setattr(app_settings, "local_sorting_available", lambda: True)
    loads = []
    monkeypatch.setattr(identify, "identify_pages", lambda paths: loads.append(paths) or time.sleep(0.3))
    replies = []
    asks = [threading.Thread(target=lambda: replies.append(client.post("/page-sorting/check").json())) for _ in range(3)]
    for a in asks:
        a.start()
    for a in asks:
        a.join()
    assert len(loads) == 1 and all(r["ok"] for r in replies)
    assert client.get("/page-sorting").json()["checked"]["ok"] is True
