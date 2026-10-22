"""`uv run app` sets up the tables, starts the API and the worker, and stops the worker when the API stops by itself;
`uv run api` sets up the tables and runs just the API with reload; every command in pyproject.toml points at a function.
The installed app (`uv run prestcribe`) on Windows runs both with no console, logging to a file, and shows PrestCribe in a
pywebview window until it is closed, started once at a time."""
import http.server
import importlib
import subprocess
import sys
import threading
import tomllib
import types
from unittest import mock

import pytest
from filelock import FileLock, Timeout

from backend import serve
from backend.common import ROOT


class Program:
    def __init__(self, args, ctrl_c):
        self.args, self.ctrl_c, self.waited, self.terminated = args, ctrl_c, 0, False

    def wait(self):
        self.waited += 1
        if self.ctrl_c and self.waited == 1:
            raise KeyboardInterrupt

    def terminate(self):
        self.terminated = True


@pytest.fixture(autouse=True)
def migrated(monkeypatch):
    """migrate() faked, so the real database is never touched; each call is recorded."""
    calls = []
    monkeypatch.setattr(serve.database, "migrate", lambda: calls.append("migrate"))
    return calls


def start(monkeypatch, migrated, ctrl_c=False):
    programs = []

    def popen(args):
        assert migrated == ["migrate"]  # the tables are set up before anything starts
        programs.append(Program(args, ctrl_c and not programs))  # Ctrl+C arrives while waiting on the API
        return programs[-1]

    monkeypatch.setattr(serve.subprocess, "Popen", popen)
    serve.main()
    return programs


def test_the_api_stopping_by_itself_stops_the_worker(monkeypatch, migrated):
    api, worker = start(monkeypatch, migrated)
    assert api.args[1:] == ["-m", "uvicorn", "backend.api.main:app"] and worker.args[1:] == ["-m", "backend.worker"]
    assert worker.terminated


def test_ctrl_c_waits_for_both_to_stop_themselves(monkeypatch, migrated):
    api, worker = start(monkeypatch, migrated, ctrl_c=True)
    assert api.waited == 2 and worker.waited == 1 and not worker.terminated  # its job is marked failed, not killed


def test_api_runs_just_the_api_restarting_on_backend_code_changes(monkeypatch, migrated):
    import uvicorn
    runs = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: runs.append((app, options, list(migrated))))
    serve.api()
    assert runs == [("backend.api.main:app", {"reload": True, "reload_dirs": [str(ROOT / "backend")]}, ["migrate"])]


def test_every_command_points_at_a_function():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert set(scripts) == {"survey", "app", "api", "worker", "prestcribe"}
    for target in scripts.values():
        module, function = target.split(":")
        assert callable(getattr(importlib.import_module(module), function)), target


#--THE INSTALLED APP ON WINDOWS--#
class Process:
    """A started program that runs until it is stopped (or `exits()`)."""
    stubborn = False

    def __init__(self, args, options):
        self.args, self.options, self.stopped, self.killed = args, options, threading.Event(), False

    def poll(self):
        return 0 if self.stopped.is_set() else None

    def wait(self, timeout=None):
        if (self.stubborn and timeout is not None) or not self.stopped.wait(timeout):
            raise subprocess.TimeoutExpired(self.args, timeout)

    def terminate(self):
        self.stopped.set()

    def kill(self):
        self.killed = True
        self.stopped.set()

    exits = terminate


class Handlers(list):
    def __iadd__(self, handler):
        self.append(handler)
        return self


class Window:
    def __init__(self, title, url):
        self.title, self.url = title, url
        self.closing, self.shown, self.destroyed, self.questions, self.answer = Handlers(), Handlers(), threading.Event(), [], True
        self.events = types.SimpleNamespace(closing=self.closing, shown=self.shown)

    def create_confirmation_dialog(self, title, message):
        self.questions.append(message)
        return self.answer

    def destroy(self):
        self.destroyed.set()


class Desktop:
    """The installed app with its programs, API answers, WebView2 and pywebview faked; `act(window)` is what happens while the window is open."""
    def __init__(self, monkeypatch, tmp_path, jobs=(), answering=False, webview2=True, act=lambda window: None):
        self.processes, self.windows, self.started, self.opened, self.settings = [], [], [], [], {}
        self.jobs, self.is_answering, self.act, self.fails, self.alerts, self.events = list(jobs), answering, act, None, [], []
        self.start_options = {}
        monkeypatch.setattr(serve, "ROOT", tmp_path)
        monkeypatch.setattr(serve.database, "migrate", lambda: self.events.append("migrate"))
        monkeypatch.setattr(serve, "die_with_us", lambda log: self.events.append("job"))  # the real one would put the test run itself in a job
        monkeypatch.setattr(serve, "alert", self.alerts.append)
        monkeypatch.setattr(serve.time, "sleep", lambda seconds: None)
        monkeypatch.setattr(serve.webbrowser, "open", self.opened.append)
        monkeypatch.setattr(serve, "webview2_installed", lambda: webview2)
        monkeypatch.setattr(serve, "answering", lambda: self.is_answering or bool(self.processes))
        monkeypatch.setattr(serve, "running_jobs", lambda: self.jobs)
        monkeypatch.setattr(serve.subprocess, "Popen", self.popen)
        monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(
            settings=self.settings, create_window=self.create_window, start=self.start))

    def popen(self, args, **options):
        self.events.append("start")
        self.processes.append(Process(args, options))
        return self.processes[-1]

    def create_window(self, title, url, **options):
        self.windows.append(Window(title, url))
        self.window_options = options
        return self.windows[-1]

    def start(self, gui=None, **options):
        self.started.append((gui, len(self.processes)))
        self.start_options = options
        window = self.windows[-1]
        if self.fails == "before":  # e.g. pythonnet or WebView2 failing to load
            raise RuntimeError("WebView2 failed to initialise")
        for handler in window.shown:
            handler()
        if self.fails == "after":
            raise RuntimeError("the window crashed")
        self.act(window)
        window.destroyed.wait(0.05)  #only the API stopping destroys it


def close(window):
    """The user closing the window: False if a handler kept it open."""
    return all(handler() is not False for handler in window.closing)


def test_the_installed_app_starts_the_api_and_worker_with_no_console_logging_to_a_file(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path)
    serve.windowed()
    api, worker = desk.processes
    assert api.args[1:] == ["-m", "uvicorn", "backend.site:site"] and worker.args[1:] == ["-m", "backend.worker"]
    for program in desk.processes:
        assert program.options["creationflags"] == 0x08000000  # CREATE_NO_WINDOW
        assert program.options["stdout"].name == str(tmp_path / "output" / "prestcribe.log")
        assert program.options["stderr"] == subprocess.STDOUT and program.options["stdin"] == subprocess.DEVNULL


def test_the_window_opens_on_pywebview_edge_once_the_api_answers(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path)
    serve.windowed()
    assert desk.started == [("edgechromium", 2)] and desk.opened == []
    assert (desk.windows[0].title, desk.windows[0].url) == ("PrestCribe", serve.ADDRESS)
    assert desk.settings["ALLOW_DOWNLOADS"]  # the exports are downloads


def test_the_window_keeps_its_storage_between_launches_in_the_output_folder(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path)
    serve.windowed()
    assert desk.start_options == {"private_mode": False, "storage_path": str(tmp_path / "output" / "webview"),
                                  "icon": str(tmp_path / "frontend" / "dist" / "favicon.ico")}  # PrestCribe's icon, not Python's
    assert desk.window_options["maximized"] is True
    assert (tmp_path / "output" / "webview").is_dir()


@pytest.mark.parametrize("fails", ["before", "after"])
def test_a_window_that_fails_falls_back_to_the_browser_only_if_it_never_opened(monkeypatch, tmp_path, fails):
    desk = Desktop(monkeypatch, tmp_path)
    desk.fails = fails
    monkeypatch.setattr(Process, "wait", lambda self, timeout=None: self.stopped.set())  # the API stops at once
    serve.windowed()
    assert desk.opened == ([serve.ADDRESS] if fails == "before" else []) and desk.alerts == []
    assert "RuntimeError" in (tmp_path / "output" / "prestcribe.log").read_text(encoding="utf-8")  # logged with its traceback
    assert all(program.stopped.is_set() for program in desk.processes)


def test_pywebview_failing_to_import_falls_back_to_the_browser(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path)
    monkeypatch.setitem(sys.modules, "webview", None)  # import raises ImportError
    monkeypatch.setattr(Process, "wait", lambda self, timeout=None: self.stopped.set())
    serve.windowed()
    assert desk.opened == [serve.ADDRESS] and desk.windows == []


def test_closing_with_a_running_job_asks_and_no_keeps_the_window_open(monkeypatch, tmp_path):
    asked = []

    def act(window):
        window.answer = False
        asked.append(close(window))
        window.answer = True
        asked.append(close(window))

    desk = Desktop(monkeypatch, tmp_path, jobs=["Transcribing item 1", "Adding items to X"], act=act)
    serve.windowed()
    assert asked == [False, True]
    assert desk.windows[0].questions[0] == ("A job is still running (Transcribing item 1 and 1 more). "
                                            "Quit anyway? It stops and can be run again later.")


def test_closing_with_nothing_running_does_not_ask(monkeypatch, tmp_path):
    asked = []
    desk = Desktop(monkeypatch, tmp_path, act=lambda window: asked.append(close(window)))
    serve.windowed()
    assert asked == [True] and desk.windows[0].questions == []


def test_closing_the_window_stops_the_api_and_the_worker(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path)
    serve.windowed()
    assert all(program.stopped.is_set() and not program.killed for program in desk.processes)


def test_a_program_that_will_not_stop_is_killed(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path)
    monkeypatch.setattr(Process, "stubborn", True)  # still running after being asked to stop
    serve.windowed()
    assert all(program.killed for program in desk.processes)


def test_the_api_stopping_by_itself_closes_the_window_and_stops_the_worker(monkeypatch, tmp_path):
    waited = []

    def act(window):
        desk.processes[0].exits()  # an update
        waited.append(window.destroyed.wait(2))

    desk = Desktop(monkeypatch, tmp_path, jobs=["Transcribing item 1"], act=act)
    serve.windowed()
    assert waited == [True] and desk.processes[1].stopped.is_set()


def test_an_app_already_running_gets_a_window_but_no_second_server_and_is_left_running(monkeypatch, tmp_path):
    closed = []
    desk = Desktop(monkeypatch, tmp_path, answering=True, jobs=["Transcribing item 1"], act=lambda window: closed.append(close(window)))
    serve.windowed()
    assert desk.processes == [] and desk.started == [("edgechromium", 0)]
    assert closed == [True] and desk.windows[0].questions == []  # closing it doesn't ask: nothing is stopped
    assert desk.events == []  # no job, no migration


def test_without_webview2_the_browser_opens_and_the_app_runs_until_the_api_stops(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path, webview2=False)
    monkeypatch.setattr(Process, "wait", lambda self, timeout=None: self.stopped.set())  # the API stops at once
    serve.windowed()
    assert desk.windows == [] and desk.opened == [serve.ADDRESS]
    assert all(program.stopped.is_set() for program in desk.processes)
    assert "browser instead" in (tmp_path / "output" / "prestcribe.log").read_text(encoding="utf-8")


def test_an_api_that_never_starts_is_not_shown(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path)
    monkeypatch.setattr(serve, "answering", lambda: False)  # e.g. port 8000 is taken, so uvicorn exits
    monkeypatch.setattr(Process, "poll", lambda self: 1 if "uvicorn" in self.args else None)
    serve.windowed()
    assert desk.windows == [] and desk.opened == [] and desk.processes[1].stopped.is_set()
    assert len(desk.alerts) == 1  # the user is told


def test_the_log_is_opened_first_appended_to_and_started_again_only_when_over_a_megabyte(monkeypatch, tmp_path):
    log = tmp_path / "output" / "prestcribe.log"
    log.parent.mkdir()
    log.write_text("earlier launch\n", encoding="utf-8")
    Desktop(monkeypatch, tmp_path, answering=True)
    serve.windowed()
    assert log.read_text(encoding="utf-8").startswith("earlier launch\n")
    log.write_text("x" * (serve.LOG_LIMIT + 1), encoding="utf-8")
    serve.windowed()
    assert "x" not in log.read_text(encoding="utf-8")


def test_a_startup_failure_is_logged_with_its_traceback_and_tells_the_user_where_the_log_is(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path)

    def broken():
        raise RuntimeError("no such table")

    monkeypatch.setattr(serve.database, "migrate", broken)
    serve.windowed()
    log = tmp_path / "output" / "prestcribe.log"
    assert "RuntimeError: no such table" in log.read_text(encoding="utf-8")
    assert desk.processes == [] and desk.windows == [] and len(desk.alerts) == 1
    assert "couldn't start" in desk.alerts[0] and str(log) in desk.alerts[0]


def test_the_job_is_made_after_the_tables_and_before_the_programs(monkeypatch, tmp_path):
    desk = Desktop(monkeypatch, tmp_path)
    serve.windowed()
    assert desk.events == ["migrate", "job", "start", "start"]


def lock_is_free(tmp_path):
    other = FileLock(tmp_path / "output" / "prestcribe.lock")
    try:
        other.acquire(timeout=0)
    except Timeout:
        return False
    other.release()
    return True


def test_a_launch_holds_the_startup_lock_while_the_app_runs_and_gives_it_back(monkeypatch, tmp_path):
    held = []
    Desktop(monkeypatch, tmp_path, act=lambda window: held.append(lock_is_free(tmp_path)))
    serve.windowed()
    assert held == [False] and lock_is_free(tmp_path)


def test_a_second_launch_waits_for_the_first_ones_app_then_opens_a_window_on_it(monkeypatch, tmp_path):
    (tmp_path / "output").mkdir()
    desk = Desktop(monkeypatch, tmp_path)
    sleeps = []
    monkeypatch.setattr(serve.time, "sleep", lambda seconds: sleeps.append(seconds) or setattr(desk, "is_answering", len(sleeps) == 5))
    with FileLock(tmp_path / "output" / "prestcribe.lock"):
        serve.windowed()
    assert len(sleeps) == 5 and desk.processes == [] and desk.started == [("edgechromium", 0)] and desk.alerts == []
    assert desk.events == []  # nothing migrated or started


def test_a_second_launch_that_the_first_never_answers_for_gives_up_after_a_minute_with_a_message(monkeypatch, tmp_path):
    (tmp_path / "output").mkdir()
    desk = Desktop(monkeypatch, tmp_path)
    sleeps = []
    monkeypatch.setattr(serve.time, "sleep", sleeps.append)
    with FileLock(tmp_path / "output" / "prestcribe.lock"):
        serve.windowed()
    assert sum(sleeps) == 60 and desk.windows == [] and desk.processes == [] and len(desk.alerts) == 1


def test_the_app_is_asked_about_without_going_through_a_proxy(monkeypatch):
    class Jobs(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'[{"label": "Transcribing item 1", "status": "running"}, {"label": "Old", "status": "done"}]'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Jobs)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(serve, "ADDRESS", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")  # nothing listens there: a request sent through it fails
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    try:
        assert serve.answering() and serve.running_jobs() == ["Transcribing item 1"]
    finally:
        server.shutdown()


def kernel32(monkeypatch, results=(1, 1, 1)):
    """Windows' kernel32 faked: the job is handle 123 and each call answers as `results` says (create, set, assign)."""
    api = mock.MagicMock()
    api.CreateJobObjectW.return_value = 123 if results[0] else 0
    api.SetInformationJobObject.return_value, api.AssignProcessToJobObject.return_value = results[1], results[2]
    api.GetCurrentProcess.return_value = 42
    monkeypatch.setattr(serve.ctypes, "WinDLL", lambda name, use_last_error=False: api, raising=False)
    monkeypatch.setattr(serve, "_job", None)
    return api


def test_this_process_goes_in_a_job_that_kills_its_members_when_it_ends(monkeypatch):
    api = kernel32(monkeypatch)
    serve.die_with_us(None)
    assert [call[0] for call in api.method_calls] == [
        "CreateJobObjectW", "SetInformationJobObject", "GetCurrentProcess", "AssignProcessToJobObject"]
    job, kind, info, size = api.SetInformationJobObject.call_args.args
    assert (job, kind, size) == (123, 9, serve.ctypes.sizeof(serve.ExtendedLimits))
    assert info._obj.BasicLimitInformation.LimitFlags == 0x2000 | 0x800  # KILL_ON_JOB_CLOSE, and BREAKAWAY_OK for the updater
    assert api.AssignProcessToJobObject.call_args.args == (123, 42)  # this process, not a child
    assert serve._job == 123  # the handle is kept


@pytest.mark.parametrize("results", [(0, 1, 1), (1, 0, 1), (1, 1, 0)])
def test_a_job_that_cannot_be_made_or_joined_is_logged_and_the_app_carries_on(monkeypatch, tmp_path, results):
    kernel32(monkeypatch, results)
    monkeypatch.setattr(serve.ctypes, "get_last_error", lambda: 5)
    with open(tmp_path / "log.txt", "w", encoding="utf-8") as log:
        serve.die_with_us(log)
    assert "Couldn't tie" in (tmp_path / "log.txt").read_text(encoding="utf-8") and serve._job is None


def test_the_installed_command_opens_a_window_on_windows_and_the_terminal_app_elsewhere(monkeypatch):
    calls = []
    monkeypatch.setattr(serve, "windowed", lambda: calls.append("window"))
    monkeypatch.setattr(serve, "main", lambda app, open_browser: calls.append((app, open_browser)))
    monkeypatch.setattr(sys, "platform", "win32")
    serve.installed()
    monkeypatch.setattr(sys, "platform", "darwin")
    serve.installed()
    assert calls == ["window", ("backend.site:site", True)]


def test_the_installer_starts_the_app_with_uvw_and_checks_for_webview2():
    script = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "TargetPath = $uvw" in script and "Start-Process $uvw" in script
    assert "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" in script and "LinkId=2124703" in script and '"/silent", "/install"' in script
    assert "-Wait -PassThru" in script and "$setup.ExitCode" in script and script.count("Test-WebView2") == 3  # defined, checked before and after
    assert "will open in your browser instead" in script
    # pinning the window pins the shortcut: both carry the same app ID
    assert '[PrestCribeAppId]::Set($path, "PrestCribe")' in script
    assert 'SetCurrentProcessExplicitAppUserModelID("PrestCribe")' in (ROOT / "backend" / "serve.py").read_text(encoding="utf-8")
