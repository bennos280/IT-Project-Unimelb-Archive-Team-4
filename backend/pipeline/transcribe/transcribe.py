"""Transcribe one page image to JSON with a vision LLM. Prompt = the prompt + the page type's template: a job's come
from the db's newest versions, otherwise prompt.txt and templates/<kind>.json."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from backend.common import settings

HERE = Path(__file__).resolve().parent
TIMEOUT = 1800  # seconds one page may take before we give up on it


def schema_for(shape):
    """Template -> JSON schema: same keys, every value a string or null, nothing extra."""
    if isinstance(shape, dict):
        return {"type": "object", "required": list(shape), "additionalProperties": False,
                "properties": {k: schema_for(v) for k, v in shape.items()}}
    if isinstance(shape, list):
        return {"type": "array", "items": schema_for(shape[0]) if shape else {"type": ["string", "null"]}}
    return {"type": ["string", "null"]}


def run_cli(command, label, **kwargs):
    """subprocess.run for a transcription CLI. A hang exits with a message, not a traceback."""
    try:
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
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
    return reply["structured_output"], "+".join(reply.get("modelUsage", {}))


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
        return json.loads(raw[raw.find("{"):raw.rfind("}") + 1]), model
    except ValueError:
        sys.exit(f"codex gave no JSON back:\n{raw[:500]}")


#the prompt and each template as in the files, byte for byte: {"prompt": ..., "main": ..., ...}
def read_texts():
    return {"prompt": (HERE / "prompt.txt").read_bytes().decode("utf-8"),
            **{path.stem: path.read_bytes().decode("utf-8") for path in sorted((HERE / "templates").glob("*.json"))}}


#what the model is told: the prompt, then the page type's blank template
def full_prompt(prompt, template):
    return f"{prompt.replace('\r\n', '\n').strip()}\n\n{json.dumps(template, indent=2)}"


def transcribe(image, kind, provider=None, model=None, effort=None, texts=None):
    """One card image of the given kind (main / notes / coded) -> the filled template as a dict,
    stamped with provider, model, effort and seconds. Defaults come from .env; texts default to the files."""
    provider = provider or settings()["PROVIDER"]
    if provider not in ("claude", "codex"):
        sys.exit(f"PROVIDER must be claude or codex, not {provider!r}")
    model = model or settings()["MODEL"]
    effort = effort or settings()["EFFORT"]
    texts = texts or read_texts()
    template = json.loads(texts[kind])
    prompt = full_prompt(texts["prompt"], template)

    started = time.perf_counter()
    if provider == "codex":
        answer, version = run_codex(image, prompt, template, model, effort)
    else:
        answer, version = run_claude(image, prompt, template, model, effort)
    seconds = round(time.perf_counter() - started, 1)

    # Notes pages: a model sometimes returns the whole structure as a string inside "text".
    if isinstance(answer.get("text"), str) and answer["text"].lstrip().startswith("{"):
        try:
            inner = json.loads(answer["text"])
            if isinstance(inner, dict) and "text" in inner:
                answer = inner
        except ValueError:
            pass

    answer["provider"] = provider
    answer["model"] = version or model
    answer["effort"] = effort
    answer["seconds"] = seconds
    return answer

