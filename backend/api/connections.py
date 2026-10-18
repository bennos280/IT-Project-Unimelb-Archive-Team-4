"""Sign-in status of the CLIs transcription runs (claude, codex), starting and ending their own sign-in, and a test request.
Credentials, tokens and the CLIs' sign-in output are never read: status uses only the fields named below, a sign-in and a
sign-out run with their output discarded, and a test reads its output only for success or the start of its error."""
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db import app_settings
from backend.db.database import get_db

router = APIRouter()

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LOGIN_SECONDS = 600
LOGOUT_SECONDS = 15
TEST_SECONDS = 90
LOGIN_ARGS = {"claude": ["auth", "login", "--claudeai"], "codex": ["login"]}
LOGOUT_ARGS = {"claude": ["auth", "logout"], "codex": ["logout"]}
TEST_PROMPT = "Reply with the single word: ok"
TEST_MODEL = {"claude": "haiku", "codex": None}  #the cheapest sensible one; None: the CLI's own default
MIN_CLAUDE = (2, 1, 280)  #transcription needs --safe-mode
_logins = {}  #provider -> (Popen, Timer)
_testing = set()  #providers with a test running
_lock = threading.Lock()

class PostRequest(BaseModel):
    pass #a JSON body is required: it makes a browser send a CORS preflight first

#runs a CLI to completion with its output captured; stdin is closed, as codex exec and claude -p wait to read an open one
def run_cli(exe, *args, timeout=10, cwd=None):
    return subprocess.run([exe, *args], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=NO_WINDOW, cwd=cwd)

#the first x.y.z of --version's output
def cli_version(exe):
    try:
        found = re.search(r"\d+\.\d+\.\d+", run_cli(exe, "--version").stdout)
    except (subprocess.SubprocessError, OSError):
        return None
    return found.group() if found else None

#logged-out prints valid JSON too, but exits 1; only loggedIn, authMethod and subscriptionType are used
def claude_status(exe):
    info = json.loads(run_cli(exe, "auth", "status", "--json").stdout)
    method, plan = info.get("authMethod"), info.get("subscriptionType")
    method, plan = (v if isinstance(v, str) else None for v in (method, plan))
    signed_in = info["loggedIn"] is True
    warnings = []
    if signed_in and method != "claude.ai":
        warnings.append("Transcription is billed to this API key or token, not to your Claude plan.")
    if os.environ.get("ANTHROPIC_API_KEY"):
        warnings.append("ANTHROPIC_API_KEY is set, so Claude Code uses it instead of your Claude plan.")
    return {"signedIn": signed_in, "method": method if signed_in else None, "plan": plan if signed_in else None, "warnings": warnings}

#the status text is read only for these words and never returned (it can hold a masked key); codex has only two modes
def codex_status(exe):
    result = run_cli(exe, "login", "status")
    text = result.stderr + result.stdout
    signed_in = result.returncode == 0
    method = ("chatgpt" if "ChatGPT" in text and "API key" not in text else "api_key") if signed_in else None
    warnings = ["Transcription is billed to this API key, not to your ChatGPT plan."] if method == "api_key" else []
    return {"signedIn": signed_in, "method": method, "plan": None, "warnings": warnings}

CHECKS = {"claude": claude_status, "codex": codex_status}

#an exited sign-in keeps its exit code until the next start
def login_state(provider):
    with _lock:
        entry = _logins.get(provider)
    code = entry[0].poll() if entry else None
    return {"running": entry is not None and code is None, "exitCode": code}

#the sign-in state is read before the slow status check, so a sign-in that finishes meanwhile is never reported as done with a stale status
def provider_status(provider):
    login = login_state(provider)
    exe = shutil.which(provider)
    status = {"installed": exe is not None, "signedIn": False, "method": None, "plan": None, "version": None,
              "warnings": [], "error": None}
    if exe:
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            version = pool.submit(cli_version, exe)  #beside the status check
            try:
                status.update(CHECKS[provider](exe))
            except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError, AttributeError):
                status["error"] = "The sign-in status check failed."
            status["version"] = version.result()
        if provider == "claude" and status["version"] and tuple(map(int, status["version"].split("."))) < MIN_CLAUDE:
            status["warnings"].append(f"Claude Code {status['version']} is older than 2.1.280, which transcription needs. Update it with: claude update")
    status["login"] = login
    return status

#ends one sign-in process, killing it only if it ignores terminate
def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

#the official sign-in opens the user's browser itself; one per provider, ended by the timer if forgotten
def start_login(provider, exe):
    with _lock:
        entry = _logins.get(provider)
        if entry and entry[0].poll() is None:
            return
        try:
            proc = subprocess.Popen([exe, *LOGIN_ARGS[provider]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        except OSError:
            raise HTTPException(500, "Could not start the sign-in.")
        timer = threading.Timer(LOGIN_SECONDS, stop, (proc,))
        timer.daemon = True
        timer.start()
        if entry:
            entry[1].cancel()
        _logins[provider] = (proc, timer)

def check_provider(provider):
    if provider not in LOGIN_ARGS:
        raise HTTPException(404, "Unknown provider.")

#the program's path; 404 for an unknown provider, 409 if it isn't installed
def installed(provider):
    check_provider(provider)
    exe = shutil.which(provider)
    if not exe:
        raise HTTPException(409, "This program is not installed.")
    return exe

@router.get("/connections")
def get_connections():
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        return dict(zip(LOGIN_ARGS, pool.map(provider_status, LOGIN_ARGS)))

@router.post("/connections/{provider}/login", status_code=202)
def post_login(provider: str, body: PostRequest):
    start_login(provider, installed(provider))
    return login_state(provider)

#cancelling ends only that process; nothing running is fine
@router.delete("/connections/{provider}/login", status_code=204)
def delete_login(provider: str):
    check_provider(provider)
    with _lock:
        entry = _logins.pop(provider, None)
    if entry:
        entry[1].cancel()
        stop(entry[0])

#the CLI's own sign-out (output discarded), which also signs the user out in their terminal; returns the new status
@router.post("/connections/{provider}/logout")
def post_logout(provider: str, body: PostRequest):
    exe = installed(provider)
    try:
        run_cli(exe, *LOGOUT_ARGS[provider], timeout=LOGOUT_SECONDS)
    except (subprocess.SubprocessError, OSError):
        raise HTTPException(500, "Sign-out didn't finish.")
    status = provider_status(provider)
    if status["signedIn"]:
        raise HTTPException(500, "Sign-out didn't work. Run it in a terminal instead.")
    return status

def test_args(provider, model):
    if provider == "claude":
        return ["-p", TEST_PROMPT, "--model", model, "--effort", "low", "--output-format", "json",
                "--strict-mcp-config", "--safe-mode", "--tools", ""]
    return ["exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", *(["--model", model] if model else []), TEST_PROMPT]

#success, and on failure the first 200 characters of the CLI's error; nothing else of the output is kept
def test_outcome(provider, out):
    if provider == "claude":
        try:
            reply = json.loads(out.stdout)
        except ValueError:
            reply = None
        if isinstance(reply, dict):
            return not reply.get("is_error") and out.returncode == 0, str(reply.get("result") or "").strip()[:200]
        return False, (out.stderr or "").strip()[:200]
    return out.returncode == 0, (out.stderr or out.stdout).strip()[-200:]  #codex prints its banner first, the error last

#one tiny real request on the user's plan: with the transcription default's model if it is this provider's, else the cheapest one
@router.post("/connections/{provider}/test")
def post_test(provider: str, body: PostRequest, db: Session = Depends(get_db)):
    exe = installed(provider)
    defaults = app_settings.transcription_defaults(db)
    model = defaults["model"] if defaults and defaults["provider"] == provider else TEST_MODEL[provider]
    with _lock:
        if provider in _testing:
            raise HTTPException(409, "A test is already running.")
        _testing.add(provider)
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory() as work:  #nothing of the project for it to read
            out = run_cli(exe, *test_args(provider, model), timeout=TEST_SECONDS, cwd=work)
        ok, error = test_outcome(provider, out)
        message = error or f"{provider.capitalize()} gave no usable reply (exit {out.returncode})."
    except subprocess.TimeoutExpired:
        ok, message = False, f"No reply within {TEST_SECONDS} seconds."
    except OSError:
        ok, message = False, "Could not run the program."
    finally:
        with _lock:
            _testing.discard(provider)
    seconds = round(time.perf_counter() - started, 1)
    return {"ok": ok, "seconds": seconds, "model": model or "default", "message": f"Replied in {seconds} s" if ok else message}
