"""Transcribe one page image to JSON with a vision LLM. Prompt = the prompt + the page type's template: a job's come
from the db's newest versions, otherwise prompt.txt and templates/<kind>.json."""
import functools
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from backend.db import database, models
from backend.pipeline.transcribe.providers import PROVIDERS, run_api

HERE = Path(__file__).resolve().parent
_asking = {}  # model name -> the lock held while claude is asked which model it runs (model_of)
TIMEOUT = 1800  # seconds one page may take before we give up on it
MODEL_SECONDS = 60  # for claude to say which model a name runs
ALL_PROVIDERS = ("claude", "codex", *PROVIDERS)  # the two programs signed in on this computer, then the APIs (providers.py)


def schema_for(shape):
    """Template -> JSON schema: same keys, every value a string or null, nothing extra; a field given as text is described by it."""
    if isinstance(shape, dict):
        return {"type": "object", "required": list(shape), "additionalProperties": False,
                "properties": {k: schema_for(v) for k, v in shape.items()}}
    if isinstance(shape, list):
        return {"type": "array", "items": schema_for(shape[0]) if shape else {"type": ["string", "null"]}}
    return {"type": ["string", "null"], **({"description": shape} if isinstance(shape, str) else {})}


def described(shape):
    """whether any of a template's fields is given as its description"""
    if isinstance(shape, dict):
        return any(described(v) for v in shape.values())
    if isinstance(shape, list):
        return any(described(v) for v in shape)
    return isinstance(shape, str)


def run_cli(command, label, **kwargs):
    """subprocess.run for a transcription CLI. A hang exits with a message, not a traceback. stdin is closed: codex exec
    and claude -p wait to read an open one."""
    try:
        return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=TIMEOUT, **kwargs)
    except subprocess.TimeoutExpired:
        sys.exit(f"{label} timed out after {TIMEOUT}s; no answer written")
    except FileNotFoundError:
        sys.exit(f"{label} CLI not found: install it and sign in")


def claude_args(image, prompt, template, model, effort):
    """Only the Read tool, and none of the user's own setup: CLAUDE.md, plugins, hooks, skills, MCP servers, memory."""
    return ["claude", "-p", f"{prompt}\n\nThe image is at: {image}", "--model", model, "--effort", effort,
            "--tools", "Read", "--strict-mcp-config", "--safe-mode", "--allowedTools", "Read", "--output-format", "json",
            "--json-schema", json.dumps(schema_for(template))]


def run_claude(image, prompt, template, model, effort):
    out = run_cli(claude_args(image, prompt, template, model, effort), "claude")
    try:
        reply = json.loads(out.stdout)
    except ValueError:
        sys.exit(f"claude gave no JSON back (exit {out.returncode}):\n{(out.stderr or out.stdout)[:500]}")
    if reply.get("is_error") or "structured_output" not in reply:
        sys.exit(f"claude failed: {str(reply.get('result') or out.stderr)[:500]}")
    return reply["structured_output"]


def run_codex(image, prompt, template, model, effort):
    """codex exec on the ChatGPT subscription; the image goes in as an attachment."""
    env = os.environ.copy()
    env.setdefault("CODEX_HOME", str(Path.home() / ".codex"))
    with tempfile.TemporaryDirectory() as work:
        schema, last = Path(work) / "schema.json", Path(work) / "last.txt"
        schema.write_text(json.dumps(schema_for(template)), encoding="utf-8")
        out = run_cli(
            ["codex", "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
             "--sandbox", "read-only", "--model", model, "--config", f'model_reasoning_effort="{effort}"',
             "--image", str(image), "--output-schema", str(schema), "--output-last-message", str(last), prompt],
            "codex", cwd=work, env=env)
        if out.returncode != 0 or not last.exists():
            sys.exit(f"codex failed (exit {out.returncode}):\n{(out.stderr or out.stdout)[-600:]}")
        raw = last.read_text(encoding="utf-8").strip()
    try:
        return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    except ValueError:
        sys.exit(f"codex gave no JSON back:\n{raw[:500]}")


#the model a claude model name runs, as the first event of a one-word claude session names it: an alias like "haiku" is
#whatever this claude program maps it to; a full name (claude-...) runs itself, so saved answers need no claude. LookupError
#when claude can't say. Asked once per name and per claude program file, which an update replaces; reads at once wait for
#the first one's asking
def model_of(name):
    if name.startswith("claude-"):
        return name
    exe = shutil.which("claude")
    try:
        with _asking.setdefault(name, threading.Lock()):
            return _claude_model(name, exe, os.stat(exe).st_mtime_ns)
    except (TypeError, OSError, subprocess.SubprocessError, ValueError, AttributeError) as error:
        raise LookupError(f"couldn't ask Claude Code which model {name} runs ({error})") from error


#model_of, or the name itself when claude can't say
def claude_model(name):
    try:
        return model_of(name)
    except LookupError:
        return name


@functools.cache  #a failure raises, so it isn't kept
def _claude_model(name, exe, stamp):
    out = subprocess.run([exe, "-p", "Reply with the single word: ok", "--model", name, "--tools", "", "--strict-mcp-config",
                          "--safe-mode", "--output-format", "stream-json", "--verbose"],
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=MODEL_SECONDS, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    event = json.loads(out.stdout.partition("\n")[0])
    if event.get("type") != "system" or not isinstance(event.get("model"), str) or not event["model"]:
        raise LookupError(f"claude didn't say which model {name} runs")
    return event["model"]


#one image and a prompt -> template filled in, by provider's model. An answer to the same page image, prompt, template,
#provider, model (the one an alias runs) and effort is saved in the db, with the seconds it took, and given again instead
#of asking, unless fresh (then it is replaced); nothing is saved or given while the model an alias runs isn't known
def ask(image, prompt, template, provider, model, effort, fresh=False):
    try:
        runs = model_of(model) if provider == "claude" else model
        key = hashlib.sha256(Path(image).read_bytes())
    except (LookupError, OSError):
        return asked(image, prompt, template, provider, model, effort)
    key.update(json.dumps([prompt, template, provider, runs, effort]).encode("utf-8"))
    key = key.hexdigest()
    saved = None if fresh else saved_answer(key)
    if saved is not None:
        return saved
    started = time.perf_counter()
    answer = {**asked(image, prompt, template, provider, model, effort), "seconds": round(time.perf_counter() - started, 1)}
    save_answer(key, answer)
    return dict(answer)


#the answer saved under key; None without one, or when the db can't say (then it is asked again)
def saved_answer(key):
    try:
        with database.SessionLocal() as db:
            row = db.get(models.SavedAnswer, key)
            return json.loads(row.answer) if row else None
    except (SQLAlchemyError, ValueError):
        return None


#keeps an answer under key; one the db can't take isn't kept, which costs only a later read
def save_answer(key, answer):
    try:
        with database.SessionLocal() as db:
            db.merge(models.SavedAnswer(key=key, answer=json.dumps(answer)))
            db.commit()
    except SQLAlchemyError:
        pass


def asked(image, prompt, template, provider, model, effort):
    if provider in PROVIDERS:
        return run_api(provider, image, prompt, schema_for(template), model)
    if provider == "codex":
        return run_codex(image, prompt, template, model, effort)
    if provider == "claude":
        return run_claude(image, prompt, template, model, effort)
    sys.exit(f"PROVIDER must be one of {', '.join(ALL_PROVIDERS)}, not {provider!r}")


#the prompt and each template as in the files, byte for byte: {"prompt": ..., "main": ..., ...}
def read_texts():
    return {"prompt": (HERE / "prompt.txt").read_bytes().decode("utf-8"),
            **{path.stem: path.read_bytes().decode("utf-8") for path in sorted((HERE / "templates").glob("*.json"))}}


#the prompt a new series starts with, as in the file
def read_starter_prompt():
    return (HERE / "starter_prompt.txt").read_bytes().decode("utf-8")


#what the model is told: the prompt, then the page type's blank template (and what a field given as text means)
def full_prompt(prompt, template):
    note = ("\n\nWhere a field above is text instead of null, the text describes the field: answer with what the page shows,"
            " not the description." if described(template) else "")
    return f"{prompt.replace('\r\n', '\n').strip()}\n\n{json.dumps(template, indent=2)}{note}"


def transcribe(image, kind, provider=None, model=None, effort=None, texts=None, fresh=False):
    """One card image of the given kind (main / notes / coded) -> the filled template as a dict,
    stamped with provider, model, effort and seconds. A choice left out comes from the choice saved on the Settings page, and with none
    saved it exits; texts default to the files. fresh: the model is asked even with an answer saved (ask)."""
    if not (provider and model and effort):
        from backend.db.app_settings import saved_choice_or_exit
        chosen = saved_choice_or_exit()
        provider, model, effort = provider or chosen["provider"], model or chosen["model"], effort or chosen["effort"]
    if provider not in ALL_PROVIDERS:
        sys.exit(f"PROVIDER must be one of {', '.join(ALL_PROVIDERS)}, not {provider!r}")
    texts = texts or read_texts()
    template = json.loads(texts[kind])
    prompt = full_prompt(texts["prompt"], template)

    started = time.perf_counter()
    answer = ask(image, prompt, template, provider, model, effort, fresh)
    seconds = answer.pop("seconds") if "seconds" in answer else round(time.perf_counter() - started, 1)  #the model's own time, from ask

    # Notes pages: a model sometimes returns the whole structure as a string inside "text".
    if isinstance(answer.get("text"), str) and answer["text"].lstrip().startswith("{"):
        try:
            inner = json.loads(answer["text"])
            if isinstance(inner, dict) and "text" in inner:
                answer = inner
        except ValueError:
            pass

    answer["provider"] = provider
    answer["model"] = model
    answer["effort"] = effort
    answer["seconds"] = seconds
    return answer

