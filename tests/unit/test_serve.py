"""`uv run app` sets up the tables, starts the API and the worker, and stops the worker when the API stops by itself;
`uv run api` sets up the tables and runs just the API with reload; every command in pyproject.toml points at a function."""
import importlib
import tomllib

import pytest

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
    assert set(scripts) == {"survey", "app", "api", "worker"}
    for target in scripts.values():
        module, function = target.split(":")
        assert callable(getattr(importlib.import_module(module), function)), target
