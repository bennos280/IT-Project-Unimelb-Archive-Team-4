"""The model and effort choices for the transcription defaults, read from the installed claude and codex programs.
Claude's come from its --help text and the models already used in the db; Codex's from `codex app-server`'s model/list
(https://developers.openai.com/codex/app-server). Neither program's output is returned raw, and no account or sign-in
information is requested."""
import json
import queue
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.connections import NO_WINDOW, run_cli, stop
from backend.db import models
from backend.db.database import get_db
from backend.pipeline.transcribe import providers, transcribe

router = APIRouter()

HELP_SECONDS = 10
CODEX_SECONDS = 20  #for the whole exchange
CODEX_PAGES = 20
CACHE_SECONDS, FAILED_CACHE_SECONDS = 600, 60
CLAUDE_EFFORTS = ["low", "medium", "high", "xhigh", "max"]  #when --help can't be read
CLAUDE_ALIASES = ["opus", "sonnet", "haiku"]
CODEX_ERROR = "Couldn't read Codex's model list."
CLAUDE_ERROR = "Couldn't read Claude Code's options."
_cache = {}  #provider -> (expires, exe, result)
_locks = {"claude": threading.Lock(), "codex": threading.Lock()}  #one read at a time per provider

#what check_transcription accepts as a model name or effort level
def usable(name, longest):
    return isinstance(name, str) and 0 < len(name) <= longest and not re.search(r"\s|\+", name) and not name.startswith("-")

#the text of one option in `claude --help`: its line and the more indented lines under it, joined
def option_text(help_text, flag):
    lines = help_text.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"\s+(?:-\w, )?{re.escape(flag)}(?![\w-])", line):
            indent = len(line) - len(line.lstrip())
            rest = []
            for more in lines[i + 1:]:
                if not more.strip() or len(more) - len(more.lstrip()) <= indent:
                    break
                rest.append(more.strip())
            return " ".join([line.strip(), *rest])
    return ""

#(efforts, aliases) from `claude --help`: --effort lists its choices in parentheses, --model says "(e.g. 'a', 'b', or 'c')"
def parse_claude_help(help_text):
    groups = [g for g in re.findall(r"\(([^()]*)\)", option_text(help_text, "--effort")) if "," in g]
    efforts = [e.strip() for e in groups[-1].split(",")] if groups else []
    if not efforts or not all(re.fullmatch(r"[a-z][a-z-]*", e) for e in efforts):
        efforts = CLAUDE_EFFORTS
    given = re.search(r"\(e\.g\.\s*([^)]*)\)", option_text(help_text, "--model"))
    aliases = re.findall(r"'([A-Za-z][\w.-]*)'", given.group(1)) if given else []
    aliases = list(dict.fromkeys(aliases or CLAUDE_ALIASES))
    return efforts, aliases + (["haiku"] if "haiku" not in aliases else [])

#(efforts, aliases, error) from the CLI, remembered; a failed read is remembered briefly so a broken program isn't run on every visit
def cached(provider, exe, read):
    with _locks[provider]:
        entry = _cache.get(provider)
        if entry and entry[0] > time.monotonic() and entry[1] == exe:
            return entry[2]
        result = read(exe)
        ttl = CACHE_SECONDS if result["error"] is None else FAILED_CACHE_SECONDS
        _cache[provider] = (time.monotonic() + ttl, exe, result)
        return result

def read_claude(exe):
    try:
        efforts, aliases = parse_claude_help(run_cli(exe, "--help", timeout=HELP_SECONDS).stdout)
    except (subprocess.SubprocessError, OSError):
        return {"efforts": CLAUDE_EFFORTS, "aliases": CLAUDE_ALIASES, "runs": {}, "error": CLAUDE_ERROR}
    with ThreadPoolExecutor(len(aliases)) as pool:  #the model each alias runs (transcribe.claude_model), all asked at once
        runs = dict(zip(aliases, pool.map(transcribe.claude_model, aliases)))
    return {"efforts": efforts, "aliases": aliases, "runs": runs, "error": None}

#"claude-haiku-4-5-20251001" -> "Haiku 4.5"; another name as it is
def model_title(model):
    match = re.fullmatch(r"claude-([a-z]+)-(\d+)(?:-(\d))?(?:-\d{8})?", model)
    return f"{match[1].title()} {match[2]}{'.' + match[3] if match[3] else ''}" if match else model

#model names already recorded on pages, most used first; "+" names are combined runs, which a default can't be
def used_claude_models(db):
    rows = (db.query(models.Page.model).filter(models.Page.provider == "claude", models.Page.model.is_not(None))
            .group_by(models.Page.model).order_by(func.count(models.Page.page_id).desc(), models.Page.model))
    return [name for (name,) in rows if usable(name, 200)]

def claude_options(db):
    exe = shutil.which("claude")
    if not exe:
        return {"available": False, "models": [], "efforts": [], "error": None}
    info = cached("claude", exe, read_claude)
    efforts = info["efforts"]
    used, runs = used_claude_models(db), info["runs"]
    #an alias with the model it runs now
    label = lambda name: f"{name} ({model_title(runs[name])})" if runs.get(name, name) != name else name
    choices = [(name, label(name), "used") for name in used] + [(a, label(a), "latest") for a in info["aliases"] if a not in used]
    return {"available": True, "error": info["error"], "efforts": efforts,
            "models": [{"value": value, "label": label, "group": group, "efforts": efforts, "defaultEffort": None}
                       for value, label, group in choices]}

#a JSON-RPC 2.0 style client for codex app-server: newline-delimited JSON, no "jsonrpc" field
#the protocol: https://github.com/openai/codex/tree/main/codex-rs/app-server-protocol
class AppServer:
    def __init__(self, exe):
        self.deadline = time.monotonic() + CODEX_SECONDS
        self.lines = queue.Queue()
        self.next_id = 0
        self.proc = subprocess.Popen([exe, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        try:
            for line in self.proc.stdout:
                self.lines.put(line)
        finally:
            self.lines.put(None)
            self.proc.stdout.close()

    def send(self, message):
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    #the result of one request; requests and notifications from the server, and lines that aren't JSON, are skipped
    def request(self, method, params):
        self.next_id += 1
        self.send({"id": self.next_id, "method": method, "params": params})
        while True:
            try:
                line = self.lines.get(timeout=max(0, self.deadline - time.monotonic()))
            except queue.Empty:
                raise TimeoutError
            if line is None:
                raise ValueError("The program ended early.")
            try:
                reply = json.loads(line)
            except ValueError:
                continue
            if isinstance(reply, dict) and "method" not in reply and reply.get("id") == self.next_id:
                if "error" in reply:
                    raise ValueError("The program refused the request.")
                return reply["result"]

    def close(self):
        try:
            self.proc.stdin.close()  #the server exits when its input ends
        except OSError:
            pass
        stop(self.proc)

#the models of one model/list reply as choices
def codex_choice(item):
    value = item.get("model") or item.get("id")
    if item.get("hidden") or not usable(value, 200):
        return None
    options = item.get("supportedReasoningEfforts")
    efforts = [o["reasoningEffort"] for o in options if isinstance(o, dict) and usable(o.get("reasoningEffort"), 40)] \
        if isinstance(options, list) else []
    default = item.get("defaultReasoningEffort")
    label = item.get("displayName")
    return {"value": value, "label": label if isinstance(label, str) and label else value, "group": "listed", "efforts": efforts,
            "defaultEffort": default if usable(default, 40) else None}

#initialize, initialized, then model/list page by page
def read_codex(exe):
    server = None
    try:
        server = AppServer(exe)
        server.request("initialize", {"clientInfo": {"name": "wilfred-prest-survey", "title": "Wilfred Prest Survey", "version": "1.0"}})
        server.send({"method": "initialized"})
        choices, cursor = [], None
        for _ in range(CODEX_PAGES):
            page = server.request("model/list", {"cursor": cursor} if cursor else {})
            choices += [c for c in map(codex_choice, page["data"]) if c]
            cursor = page.get("nextCursor")
            if not cursor:
                break
        efforts = list(dict.fromkeys(e for c in choices for e in c["efforts"]))
        return {"available": True, "models": choices, "efforts": efforts, "error": None}
    except Exception:  #a timeout, a failed start, or any reply that isn't what model/list should send
        return {"available": True, "models": [], "efforts": [], "error": CODEX_ERROR}
    finally:
        if server:
            server.close()

def codex_options():
    exe = shutil.which("codex")
    if not exe:
        return {"available": False, "models": [], "efforts": [], "error": None}
    return cached("codex", exe, read_codex)

#an API's models for its key (providers.py), remembered like a program's; not available without a key (Ollama: not running)
def read_api(provider):
    try:
        names = providers.models(provider)
        return {"available": True, "error": None if names else "No models that read images were listed.", "efforts": ["default"],
                "models": [{"value": n, "label": n, "group": "listed", "efforts": ["default"], "defaultEffort": "default"} for n in names]}
    except Exception:  #unreachable, refused, or an answer of another shape
        return {"available": provider != "ollama", "models": [], "efforts": ["default"],
                "error": "Couldn't list its models: check the key on this page." if provider != "ollama" else None}

def api_options(provider):
    if providers.key(provider) is None:
        return {"available": False, "models": [], "efforts": [], "error": None}
    with _locks.setdefault(provider, threading.Lock()):
        entry = _cache.get(provider)
        if entry and entry[0] > time.monotonic() and entry[1] == providers.key(provider):
            return entry[2]
        result = read_api(provider)
        _cache[provider] = (time.monotonic() + (CACHE_SECONDS if result["error"] is None else FAILED_CACHE_SECONDS),
                            providers.key(provider), result)
        return result

@router.get("/transcription-options")
def get_transcription_options(db: Session = Depends(get_db)):
    return {"claude": claude_options(db), "codex": codex_options(), **{p: api_options(p) for p in providers.PROVIDERS}}
