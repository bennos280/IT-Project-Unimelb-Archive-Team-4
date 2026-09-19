"""Retry unfinished work without skipping surveys or repeating saved transcription calls."""
import json
from pathlib import Path

import pytest
from PIL import Image

from pipeline import run
from pipeline.identify import identify
from pipeline.transcribe import run as transcription


def labels(images):
    return [{"label": "main", "confidence": 1.0, "distance": 0.0} for _ in images]


@pytest.fixture
def survey(tmp_path, monkeypatch):
    data, output = tmp_path / "data", tmp_path / "output"
    source = data / "survey"
    source.mkdir(parents=True)
    for i in (1, 2):
        Image.new("RGB", (8, 8), (i, i, i)).save(source / f"page{i}.png")
    config = {"DATA": str(data), "OUTPUT": str(output), "MODEL": "sonnet", "EFFORT": "high"}
    monkeypatch.setattr(run, "settings", lambda: config)
    monkeypatch.setattr(identify, "identify_pages", labels)

    def unexpected_call(*args, **kwargs):
        pytest.fail("Tests must never call a live transcription model")

    monkeypatch.setattr(transcription, "transcribe", unexpected_call)
    return source, output, config


def test_failed_identification_is_retried(survey, monkeypatch):
    source, output, _ = survey

    def fail(images):
        raise RuntimeError("identification failed")

    monkeypatch.setattr(identify, "identify_pages", fail)
    with pytest.raises(RuntimeError, match="identification failed"):
        run.main([])
    manifest = run.read_manifest(output / source.stem)
    assert [entry["step"] for entry in manifest["steps"]] == ["split"]
    assert run.unprocessed(source.parent, output) == [source]

    monkeypatch.setattr(identify, "identify_pages", labels)
    assert run.main([]) == 0
    assert len(run.read_manifest(output / source.stem)["pages"]) == 2
    assert run.unprocessed(source.parent, output) == []
    monkeypatch.setattr(identify, "identify_pages", fail)
    assert run.main([]) == 0  # A completed survey is skipped.


def test_transcription_is_selected_only_when_requested(survey, monkeypatch):
    source, output, _ = survey
    calls = []

    def transcribe(image, kind, **options):
        calls.append(image.name)
        return {"text": image.name}

    monkeypatch.setattr(transcription, "transcribe", transcribe)
    assert run.main([]) == 0
    assert calls == []
    assert run.unprocessed(source.parent, output) == []
    assert run.unprocessed(source.parent, output, list(run.STEPS)) == [source]
    assert run.main(["--transcribe"]) == 0
    assert calls == ["page1.png", "page2.png"]
    assert run.main(["--transcribe"]) == 0
    assert calls == ["page1.png", "page2.png"]


def test_failed_explicit_rerun_clears_old_completion(survey, monkeypatch):
    source, output, _ = survey
    assert run.main([]) == 0

    def fail(run_state):
        raise RuntimeError("splitting failed")

    monkeypatch.setitem(run.STEPS, "split", fail)
    with pytest.raises(RuntimeError, match="splitting failed"):
        run.main([str(source)])
    assert run.read_manifest(output / source.stem)["steps"] == []
    assert run.unprocessed(source.parent, output) == [source]


@pytest.mark.parametrize("contents", [b'{"steps":', b"null", b'{"steps": null}',
                                      b'{"steps": [null, "identify"]}', b"\xff"])
def test_invalid_manifest_does_not_hide_input(survey, contents):
    source, output, _ = survey
    dest = output / source.stem
    dest.mkdir(parents=True)
    (dest / "manifest.json").write_bytes(contents)
    assert run.unprocessed(source.parent, output) == [source]


def test_interrupted_transcription_reuses_saved_pages(survey, monkeypatch):
    source, output, _ = survey
    calls = []

    def transcribe(image, kind, **options):
        calls.append(image.name)
        if calls == ["page1.png", "page2.png"]:
            raise SystemExit("model timed out")
        return {"text": image.name}

    monkeypatch.setattr(transcription, "transcribe", transcribe)
    with pytest.raises(SystemExit, match="model timed out"):
        run.main(["--transcribe"])
    manifest = run.read_manifest(output / source.stem)
    assert manifest["pages"][0]["transcript"]
    assert [entry["step"] for entry in manifest["steps"]] == ["split", "identify"]
    saved = (output / source.stem / "transcribe" / "page1.json").read_bytes()
    assert run.main([]) == 0  # No paid retry without the flag.
    assert calls == ["page1.png", "page2.png"]
    assert run.main(["--transcribe"]) == 0
    assert calls == ["page1.png", "page2.png", "page2.png"]
    assert (output / source.stem / "transcribe" / "page1.json").read_bytes() == saved
    assert run.completed(output / source.stem, list(run.STEPS))


@pytest.mark.parametrize("changed", ["image", "label", "model", "effort", "prompt", "template",
                                    "missing_result", "changed_result"])
def test_transcription_reuse_requires_matching_inputs_and_result(survey, monkeypatch, tmp_path, changed):
    source, output, config = survey
    # Copy prompt/template data into the test directory so fixtures stay untouched.
    prompts = tmp_path / "prompts"
    (prompts / "templates").mkdir(parents=True)
    (prompts / "prompt.txt").write_text("Read the page.", encoding="utf-8")
    for kind in ("main", "notes"):
        (prompts / "templates" / f"{kind}.json").write_text('{"text": null}', encoding="utf-8")
    monkeypatch.setattr(transcription, "HERE", prompts)
    calls = []

    def transcribe(image, kind, **options):
        calls.append((image.name, kind, options))
        return {"text": image.name}

    monkeypatch.setattr(transcription, "transcribe", transcribe)
    run.main(["--transcribe"])
    assert len(calls) == 2
    if changed == "image":
        Image.new("RGB", (8, 8), "red").save(source / "page1.png")
    elif changed == "label":
        monkeypatch.setattr(identify, "identify_pages", lambda images: [
            {"label": "notes" if p.name == "page1.png" else "main", "confidence": 1.0, "distance": 0.0}
            for p in images])
    elif changed in ("model", "effort"):
        config[changed.upper()] = "haiku" if changed == "model" else "low"
    elif changed == "prompt":
        (prompts / "prompt.txt").write_text("Read all fields.", encoding="utf-8")
    elif changed == "template":
        (prompts / "templates" / "main.json").write_text('{"new_field": null}', encoding="utf-8")
    else:
        result = output / source.stem / "transcribe" / "page1.json"
        if changed == "missing_result":
            result.unlink()
        else:
            result.write_text('{"text": "changed"}', encoding="utf-8")
    # Explicit inputs request a rerun even when all previous stages completed.
    run.main([str(source), "--transcribe"])
    assert len(calls) == (4 if changed in ("model", "effort", "prompt", "template") else 3)


def test_legacy_completed_manifest_still_skips_input(survey):
    source, output, _ = survey
    dest = output / source.stem
    dest.mkdir(parents=True)
    (dest / "manifest.json").write_text(json.dumps({"steps": [{"step": "split"}, {"step": "identify"}]}),
                                        encoding="utf-8")
    assert run.unprocessed(source.parent, output) == []


def test_failed_json_publication_keeps_previous_progress(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    run.write(manifest, {"steps": [{"step": "split"}]})
    before = manifest.read_bytes()

    def fail(source, target):
        raise OSError("publication blocked")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="publication blocked"):
        run.write(manifest, {"steps": [{"step": "split"}, {"step": "identify"}]})
    assert manifest.read_bytes() == before
    assert list(tmp_path.iterdir()) == [manifest]
