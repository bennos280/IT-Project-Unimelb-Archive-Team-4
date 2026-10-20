"""Installing page sorting on this computer (PyTorch, the local-sorting extra) from the Settings page."""
import collections
import importlib
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.api.connections import NO_WINDOW, PostRequest
from backend.common import ROOT
from backend.db import app_settings

router = APIRouter()

TAIL_LINES = 20
NO_UV = "uv wasn't found: run PrestCribe's install line again."
INTEL_MAC = "PyTorch isn't available for Intel Macs: sort pages with the reading model."
_state = {"running": False, "ok": None, "detail": None, "seconds": None}  #the last install in this API run
_lock = threading.Lock()

#uv sets UV for "uv run"; else the PATH, else where its installer puts it
def find_uv():
    found = os.environ.get("UV") or shutil.which("uv")
    if found:
        return found
    home = Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv")
    return str(home) if home.exists() else None

#why PyTorch can't be installed here, or None
def install_problem():
    if sys.platform == "darwin" and platform.machine() != "arm64":
        return INTEL_MAC
    return None if find_uv() else NO_UV

def status():
    problem = install_problem()
    with _lock:
        state = dict(_state)
    installed = not state["running"] and app_settings.local_sorting_available()
    return {"installable": problem is None, "running": state["running"], "ok": True if installed else state["ok"],
            "detail": problem or state["detail"], "seconds": state["seconds"]}

#the install itself; the output is kept only as its last lines, for a failure
def run_install(uv):
    started = time.perf_counter()
    tail = collections.deque(maxlen=TAIL_LINES)
    try:
        proc = subprocess.Popen([uv, "sync", "--directory", str(ROOT), "--extra", "local-sorting", "--inexact", "--no-install-project"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        for line in proc.stdout:
            tail.append(line.rstrip())
        ok = proc.wait() == 0
        detail = None if ok else "\n".join(tail) or "uv failed."
    except OSError:
        ok, detail = False, "Could not run uv."
    if ok:
        importlib.invalidate_caches()  #so torch is found in this process without a restart
    with _lock:
        _state.update(running=False, ok=ok, detail=detail, seconds=round(time.perf_counter() - started, 1))

@router.get("/page-sorting/install")
def get_install():
    return status()

@router.post("/page-sorting/install", status_code=202)
def post_install(body: PostRequest):
    problem = install_problem()
    if problem:
        raise HTTPException(400, problem)
    with _lock:
        if _state["running"]:
            raise HTTPException(409, "PyTorch is already being installed.")
        if app_settings.local_sorting_available():
            started = False
        else:
            _state.update(running=True, ok=None, detail=None, seconds=None)
            started = True
    if started:
        threading.Thread(target=run_install, args=(find_uv(),), daemon=True).start()
    return status()
