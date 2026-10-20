"""GET /transcription-options with claude and codex faked: --help text is canned, and codex app-server is a small script that
speaks the protocol over pipes. The real programs are never run."""
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

import pytest

from backend.api import transcription_options as options
from backend.db import models

HELP = """\
Options:
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
  --environment <environment_id>        Create a new cloud session
  --model <model>                       Model for the current session. Provide
                                        an alias for the latest model (e.g.
                                        'fable', 'opus', or 'sonnet') or a
                                        model's full name.
  -n, --name <name>                     Set a display name
"""

# a codex app-server stand-in; argv[1] is the mode: ok (two pages, a notification before each reply), flood (ok, after 2 MB of output nobody asked for), noise (ok, plus replies and requests that aren't the answer, and
# each answer split over two writes), silent, garbage or refuse
FAKE = textwrap.dedent('''
    import json, sys, time
    mode = sys.argv[1]
    if mode == "silent":
        time.sleep(60)
    if mode == "garbage":
        print("not json at all", flush=True)
        sys.exit(0)
    if mode == "flood":
        for _ in range(20000):
            print("x" * 100)
        sys.stdout.flush()
    def model(name, efforts, default, **extra):
        return {"id": name, "model": name, "displayName": name.upper(), "hidden": False, "isDefault": False,
                "defaultReasoningEffort": default, "supportedReasoningEfforts": [{"reasoningEffort": e, "description": "d"} for e in efforts], **extra}
    pages = {None: {"data": [model("gpt-a", ["low", "high"], "low"), model("gpt-hidden", ["low"], "low", hidden=True)], "nextCursor": "p2"},
             "p2": {"data": [model("gpt-b", ["medium"], "medium")], "nextCursor": None}}
    def reply(message, result):
        if mode == "noise":
            print(json.dumps({"id": message["id"] + 100, "result": {"data": [model("gpt-wrong", ["low"], "low")], "nextCursor": None}}), flush=True)
            print(json.dumps({"id": message["id"], "method": "item/tool/call", "params": {}}), flush=True)
            text = json.dumps({"id": message["id"], "result": result})
            print("not json", flush=True)
            sys.stdout.write(text[:10]); sys.stdout.flush(); time.sleep(0.05)
            print(text[10:], flush=True)
        else:
            print(json.dumps({"id": message["id"], "result": result}), flush=True)
    seen = []
    for line in sys.stdin:
        message = json.loads(line)
        seen.append(message["method"])
        if "id" not in message:
            continue
        print(json.dumps({"method": "account/updated", "params": {"email": "someone@example.com"}}), flush=True)
        if mode == "refuse":
            print(json.dumps({"id": message["id"], "error": {"code": -32600, "message": "secret detail"}}), flush=True)
        elif message["method"] == "initialize":
            assert message["params"]["clientInfo"]["name"]
            reply(message, {"userAgent": "x"})
        elif message["method"] == "model/list":
            assert seen[:2] == ["initialize", "initialized"], seen
            reply(message, pages[message["params"].get("cursor")])
''')


@pytest.fixture(autouse=True)
def fakes(monkeypatch, tmp_path):
    """Both programs installed; codex app-server is the script above, started with the mode in fakes.mode[0]."""
    options._cache.clear()
    monkeypatch.setattr(options.shutil, "which", lambda name: f"/bin/{name}")
    script = tmp_path / "fake_app_server.py"
    script.write_text(FAKE)
    procs, mode = [], ["ok"]
    real_popen = subprocess.Popen

    def popen(args, **kwargs):
        assert args[1:] == ["app-server"] and kwargs["stderr"] == subprocess.DEVNULL and kwargs["creationflags"] == options.NO_WINDOW
        proc = real_popen([sys.executable, str(script), mode[0]], **{k: v for k, v in kwargs.items() if k != "creationflags"})
        procs.append(proc)
        return proc
    monkeypatch.setattr(options.subprocess, "Popen", popen)
    monkeypatch.setattr(options, "run_cli", lambda exe, *a, **k: SimpleNamespace(stdout=HELP))
    yield SimpleNamespace(mode=mode, procs=procs)
    for proc in procs:
        assert proc.poll() is not None  #always ended
    options._cache.clear()


def add_pages(db, rows):
    if not db.get(models.Bundle, "b"):
        db.add(models.Bundle(bundle_id="b", source_pdf="b.pdf", collection_id=1))
        db.flush()
    start = db.query(models.Page).count()
    for i, (provider, model) in enumerate(rows, start):
        db.add(models.Page(page_id=f"p{i}", import_path="x", bundle_id="b", category="main", provider=provider, model=model))
    db.commit()


# claude's help
def test_help_efforts_and_aliases():
    assert options.parse_claude_help(HELP) == (["low", "medium", "high", "xhigh", "max"], ["fable", "opus", "sonnet", "haiku"])


def test_help_efforts_on_one_line_and_haiku_not_added_twice():
    text = "  --effort <level>   Effort (min, max)\n  --model <m>   Use (e.g. 'haiku', 'opus')\n"
    assert options.parse_claude_help(text) == (["min", "max"], ["haiku", "opus"])


@pytest.mark.parametrize("text", ["", "  --effort <level>   Effort level\n", "  --effort <level>  (low, Me dium)\n", "nothing useful"])
def test_help_that_cannot_be_parsed_falls_back(text):
    assert options.parse_claude_help(text) == (options.CLAUDE_EFFORTS, ["opus", "sonnet", "haiku"])


def test_claude_options(client, db):
    add_pages(db, [("claude", "opus"), ("claude", "claude-x"), ("claude", "claude-x"), ("claude", "a+b"), ("codex", "gpt-z"), (None, "n"), ("claude", None)])
    body = client.get("/transcription-options").json()["claude"]
    efforts = ["low", "medium", "high", "xhigh", "max"]
    assert body["available"] is True and body["error"] is None and body["efforts"] == efforts
    assert [(m["value"], m["label"], m["group"]) for m in body["models"]] == [
        ("claude-x", "claude-x", "used"), ("opus", "opus", "used"),
        ("fable", "fable (latest)", "latest"), ("sonnet", "sonnet (latest)", "latest"), ("haiku", "haiku (latest)", "latest")]
    assert all(m["efforts"] == efforts and m["defaultEffort"] is None for m in body["models"])


def test_claude_help_that_cannot_run_still_gives_defaults(client, monkeypatch):
    def fail(*a, **k):
        raise subprocess.TimeoutExpired("claude", 10)
    monkeypatch.setattr(options, "run_cli", fail)
    body = client.get("/transcription-options").json()["claude"]
    assert body["available"] is True and body["error"] == options.CLAUDE_ERROR and body["efforts"] == options.CLAUDE_EFFORTS
    assert [m["value"] for m in body["models"]] == ["opus", "sonnet", "haiku"]


def test_not_installed(client, monkeypatch):
    monkeypatch.setattr(options.shutil, "which", lambda name: None)
    body = client.get("/transcription-options").json()
    assert body["claude"] == body["codex"] == {"available": False, "models": [], "efforts": [], "error": None}


# codex's model/list
def test_codex_models_across_pages(client, fakes):
    response = client.get("/transcription-options")
    assert response.json()["codex"] == {"available": True, "error": None, "efforts": ["low", "high", "medium"], "models": [
        {"value": "gpt-a", "label": "GPT-A", "group": "listed", "efforts": ["low", "high"], "defaultEffort": "low"},
        {"value": "gpt-b", "label": "GPT-B", "group": "listed", "efforts": ["medium"], "defaultEffort": "medium"}]}
    assert "someone@example.com" not in response.text
    assert len(fakes.procs) == 1


def test_codex_answers_are_matched_by_id_and_split_lines_are_joined(client, fakes):
    fakes.mode[0] = "noise"
    codex = client.get("/transcription-options").json()["codex"]
    assert codex["error"] is None and [m["value"] for m in codex["models"]] == ["gpt-a", "gpt-b"]


def test_codex_output_that_fills_the_pipe_does_not_block(client, fakes):
    fakes.mode[0] = "flood"
    assert [m["value"] for m in client.get("/transcription-options").json()["codex"]["models"]] == ["gpt-a", "gpt-b"]


def test_codex_stops_after_the_page_limit(client, fakes, monkeypatch):
    monkeypatch.setattr(options, "CODEX_PAGES", 1)
    assert [m["value"] for m in client.get("/transcription-options").json()["codex"]["models"]] == ["gpt-a"]


@pytest.mark.parametrize("mode", ["garbage", "refuse"])
def test_codex_failures_give_a_fixed_message(client, fakes, mode):
    fakes.mode[0] = mode
    response = client.get("/transcription-options")
    assert response.json()["codex"] == {"available": True, "models": [], "efforts": [], "error": options.CODEX_ERROR}
    assert "secret detail" not in response.text


def test_codex_that_never_answers_times_out_and_is_ended(client, fakes, monkeypatch):
    monkeypatch.setattr(options, "CODEX_SECONDS", 0.5)
    fakes.mode[0] = "silent"
    started = time.monotonic()
    assert client.get("/transcription-options").json()["codex"]["error"] == options.CODEX_ERROR
    assert time.monotonic() - started < 10  #the fake would sleep for 60 s
    assert fakes.procs[0].poll() is not None


def test_codex_that_cannot_start(client, monkeypatch):
    def fail(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(options.subprocess, "Popen", fail)
    assert client.get("/transcription-options").json()["codex"]["error"] == options.CODEX_ERROR


def test_codex_not_installed(client, monkeypatch):
    monkeypatch.setattr(options.shutil, "which", lambda name: None if name == "codex" else f"/bin/{name}")
    assert client.get("/transcription-options").json()["codex"] == {"available": False, "models": [], "efforts": [], "error": None}


# the cache
def test_results_are_cached_per_program_but_used_models_are_not(client, db, fakes, monkeypatch):
    helps = []
    monkeypatch.setattr(options, "run_cli", lambda exe, *a, **k: helps.append(a) or SimpleNamespace(stdout=HELP))
    first = client.get("/transcription-options").json()
    add_pages(db, [("claude", "new-model")])
    second = client.get("/transcription-options").json()
    assert len(helps) == 1 and len(fakes.procs) == 1 and first["codex"] == second["codex"]
    assert "new-model" not in [m["value"] for m in first["claude"]["models"]]
    assert second["claude"]["models"][0]["value"] == "new-model"


def test_cache_follows_the_program_path_and_expires(client, fakes, monkeypatch):
    client.get("/transcription-options")
    monkeypatch.setattr(options.shutil, "which", lambda name: f"/other/{name}")
    client.get("/transcription-options")
    assert len(fakes.procs) == 2
    clock = [0.0]
    monkeypatch.setattr(options.time, "monotonic", lambda: clock[0])
    options._cache.clear()
    client.get("/transcription-options")
    clock[0] = options.CACHE_SECONDS + 1
    client.get("/transcription-options")
    assert len(fakes.procs) == 4


def test_a_failure_is_cached_only_briefly(client, fakes, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(options.time, "monotonic", lambda: clock[0])
    fakes.mode[0] = "garbage"
    client.get("/transcription-options")
    client.get("/transcription-options")
    assert len(fakes.procs) == 1
    clock[0] = options.FAILED_CACHE_SECONDS + 1
    fakes.mode[0] = "ok"
    assert client.get("/transcription-options").json()["codex"]["error"] is None


# names the server would refuse are not offered
def test_codex_choice_drops_unusable_names_and_efforts():
    item = {"model": "gpt-a", "displayName": "A", "hidden": False, "defaultReasoningEffort": "bad effort",
            "supportedReasoningEfforts": [{"reasoningEffort": "low"}, {"reasoningEffort": "-x"}, {"reasoningEffort": "a b"}, {"reasoningEffort": 3}]}
    assert options.codex_choice(item) == {"value": "gpt-a", "label": "A", "group": "listed", "efforts": ["low"], "defaultEffort": None}
    for bad in ({"model": "a b"}, {"model": "a+b"}, {"model": "-m"}, {"model": "x" * 201}, {"model": "ok", "hidden": True}, {}):
        assert options.codex_choice(bad) is None


def test_used_models_the_server_would_refuse_are_not_offered(client, db):
    add_pages(db, [("claude", "good"), ("claude", "has space"), ("claude", "-flag")])
    assert [m["value"] for m in client.get("/transcription-options").json()["claude"]["models"] if m["group"] == "used"] == ["good"]


def test_help_flag_must_match_exactly():
    text = "  --effort-extra <x>   (a, b)\n  --effort <level>   Effort (low, high)\n"
    assert options.parse_claude_help(text)[0] == ["low", "high"]
