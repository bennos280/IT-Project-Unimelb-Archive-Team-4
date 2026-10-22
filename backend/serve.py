"""`uv run app`: the API and the worker, until Ctrl+C. `uv run api`: just the API, reloading on code changes. `uv run prestcribe`:
the installed app, the built frontend with the API and the worker: in a window of its own on Windows (closing it quits), in the
browser elsewhere."""
import ctypes
import json
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser

from filelock import FileLock, Timeout

from backend.common import ROOT, settings
from backend.db import database

ADDRESS = "http://127.0.0.1:8000"
NO_CONSOLE = 0x08000000  #subprocess.CREATE_NO_WINDOW, which only exists on Windows
WEBVIEW2 = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"  #the Edge WebView2 runtime's id in the registry
LOG_LIMIT = 1_000_000  #bytes: a longer prestcribe.log starts again at the next launch
ATTACH_WAIT = 60  #seconds a second launch waits for the first one's app to answer
KILL_ON_JOB_CLOSE = 0x2000  #JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
BREAKAWAY_OK = 0x800  #JOB_OBJECT_LIMIT_BREAKAWAY_OK: a process started with CREATE_BREAKAWAY_FROM_JOB (the updater) outlives the app
EXTENDED_LIMITS = 9  #JobObjectExtendedLimitInformation
_job = None  #kept open for as long as this process lives


class Limits(ctypes.Structure):  #JOBOBJECT_BASIC_LIMIT_INFORMATION
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class ExtendedLimits(ctypes.Structure):  #JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    _fields_ = [("BasicLimitInformation", Limits), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def main(app="backend.api.main:app", open_browser=False):
    database.migrate()
    #no reloading: on Windows, uvicorn reloads by sending Ctrl+C to the whole terminal, which would stop the worker too
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", app])
    worker = subprocess.Popen([sys.executable, "-m", "backend.worker"])
    if open_browser:
        threading.Timer(3, webbrowser.open, [ADDRESS]).start()  #once the API is listening
    try:
        api.wait()
    except KeyboardInterrupt:  #both got the Ctrl+C: let each stop itself
        api.wait()
        worker.wait()
    else:  #the API stopped by itself
        worker.terminate()


def installed():
    if sys.platform == "win32":
        windowed()
    else:
        print(f"PrestCribe is running at {ADDRESS}. Close this window to stop it.")
        main("backend.site:site", open_browser=True)


def get(path, timeout):
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f"{ADDRESS}{path}", timeout=timeout)  #never via a proxy: it is this computer


def answering():
    try:
        with get("/api/jobs", 1):  #not just the port: a dev API on it has no /api/jobs
            return True
    except Exception:
        return False


def webview2_installed():
    import winreg
    for hive, path in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"),
                       (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients"),
                       (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients")):
        try:
            with winreg.OpenKey(hive, rf"{path}\{WEBVIEW2}") as key:
                version = winreg.QueryValueEx(key, "pv")[0]
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return True
    return False


def running_jobs():
    try:
        with get("/api/jobs", 2) as reply:
            return [job["label"] for job in json.load(reply) if job["status"] == "running"]
    except Exception:
        return []  #the API is gone: nothing to ask about


def start(args, log):
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_CONSOLE)


def stop(program):
    program.terminate()
    try:
        program.wait(5)
    except subprocess.TimeoutExpired:
        program.kill()


def die_with_us(log):
    """This process in a job that kills everything in it when its handle closes, which Windows does when the process ends
    however it ends: programs started after this are in it too."""
    global _job
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes, kernel32.CreateJobObjectW.restype = [ctypes.c_void_p, ctypes.c_wchar_p], ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE | BREAKAWAY_OK
    job = kernel32.CreateJobObjectW(None, None)
    if not (job and kernel32.SetInformationJobObject(job, EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits))
            and kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())):  #e.g. already in a job that forbids nesting
        print(f"Couldn't tie the API and worker to this process (Windows error {ctypes.get_last_error()}): "
              "if it is killed they keep running.", file=log)
        return
    _job = job


def alert(text):
    ctypes.windll.user32.MessageBoxW(None, text, "PrestCribe", 0x10)  #MB_ICONERROR


def show(api=None, log=None):
    """PrestCribe in a window of its own until it is closed, which stops the API when it is ours. False if the window never
    opened (no WebView2 or pywebview, or either failed): nothing is shown."""
    opened = threading.Event()
    try:
        import webview
        if not webview2_installed():  #pywebview would quietly use the old Internet Explorer engine, which can't run the frontend
            raise ImportError("WebView2 isn't installed")
        storage = ROOT / settings()["OUTPUT"] / "webview"  #the app keeps the chosen reviewer in localStorage
        storage.mkdir(parents=True, exist_ok=True)
        webview.settings["ALLOW_DOWNLOADS"] = True  #the exports
        #its own taskbar button and icon, not Python's
        if sys.platform == "win32":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PrestCribe")
        window = webview.create_window("PrestCribe", ADDRESS, width=1400, height=900, maximized=True)
        quitting = threading.Event()

        def closing():
            jobs = running_jobs() if api and not quitting.is_set() else []
            if jobs and not window.create_confirmation_dialog(
                    "PrestCribe", f"A job is still running ({jobs[0]}{f' and {len(jobs) - 1} more' if len(jobs) > 1 else ''}). "
                                  "Quit anyway? It stops and can be run again later."):
                return False  #stays open

        def watch():  #the API stopped by itself, as an update does: the installer starts PrestCribe again
            api.wait()
            quitting.set()
            try:
                window.destroy()
            except Exception:
                pass  #already closed

        window.events.closing += closing
        window.events.shown += lambda: opened.set()
        if api:
            threading.Thread(target=watch, daemon=True).start()
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(storage),  #blocks until the window is gone
                      icon=str(ROOT / "frontend" / "dist" / "favicon.ico"))
    except Exception as error:
        traceback.print_exc(file=log)
        if opened.is_set():
            return True  #it was shown and then failed: it is gone
        print(f"No window ({error}): opening the browser instead.", file=log)
        return False
    return True


def windowed():
    output = ROOT / settings()["OUTPUT"]
    output.mkdir(parents=True, exist_ok=True)
    path = output / "prestcribe.log"
    with open(path, "w" if path.exists() and path.stat().st_size > LOG_LIMIT else "a", encoding="utf-8", buffering=1) as log:  #no console to show the API's output in
        lock = FileLock(output / "prestcribe.lock")
        try:
            try:
                lock.acquire(timeout=0)
                patience = 0
            except Timeout:  #another launch is starting the app or running it
                patience = ATTACH_WAIT
            if patience or answering():
                lock.release()  #a window on an app that is someone else's must not keep the next launch waiting
                for _ in range(patience):
                    if answering():
                        break
                    time.sleep(1)
                if not answering():
                    raise RuntimeError("the PrestCribe already running doesn't answer")
                #ponytail: a window on the app already running, which closing it leaves running; not told apart from a copy of another folder
                if not show(log=log):
                    webbrowser.open(ADDRESS)
                return
            serve(log)
        except Exception:
            traceback.print_exc(file=log)
            alert(f"PrestCribe couldn't start.\n\nWhat went wrong is in {path}")
        finally:
            lock.release()


def serve(log):
    database.migrate()
    die_with_us(log)  #before the API and the worker, so they are in the job too
    api = start([sys.executable, "-m", "uvicorn", "backend.site:site"], log)
    worker = start([sys.executable, "-m", "backend.worker"], log)
    try:
        for _ in range(150):  #up to 30 s for the API to start
            if api.poll() is not None or answering():
                break
            time.sleep(0.2)
        if api.poll() is not None or not answering():
            raise RuntimeError("the API didn't start (is port 8000 taken?)")
        if not show(api, log):
            webbrowser.open(ADDRESS)  #ponytail: with no window, nothing but Task Manager stops it; add a tray icon if that matters
            api.wait()
    finally:
        stop(worker)
        stop(api)


def api():
    import uvicorn
    database.migrate()
    uvicorn.run("backend.api.main:app", reload=True, reload_dirs=[str(ROOT / "backend")])
