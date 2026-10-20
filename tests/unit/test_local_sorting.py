"""The PyTorch install endpoints, with uv faked: nothing real is run."""
import importlib
import threading
import time
from types import SimpleNamespace

import pytest

from backend.api import local_sorting
from backend.db import app_settings

URL = "/page-sorting/install"


class FakePopen:
    made = []
    code = 0
    lines = ["Resolved 80 packages\n"]
    release = None  #an Event the fake waits on before finishing

    def __init__(self, args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.stdout = self.output()
        FakePopen.made.append(self)

    def output(self):
        yield from self.lines
        if self.release:
            self.release.wait(5)

    def wait(self, timeout=None):
        return self.code


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    """uv found, PyTorch not installed, no install run yet."""
    FakePopen.made, FakePopen.code, FakePopen.lines, FakePopen.release = [], 0, ["Resolved 80 packages\n"], None
    monkeypatch.setattr(local_sorting.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(local_sorting, "find_uv", lambda: "/bin/uv")
    monkeypatch.setattr(local_sorting, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(app_settings, "local_sorting_available", lambda: False)
    monkeypatch.setitem(local_sorting._state, "running", False)
    local_sorting._state.update(ok=None, detail=None, seconds=None)


def finished(client):
    for _ in range(100):
        body = client.get(URL).json()
        if not body["running"]:
            return body
        time.sleep(0.02)
    raise AssertionError("the install didn't finish")


def test_installable(client):
    assert client.get(URL).json() == {"installable": True, "running": False, "ok": None, "detail": None, "seconds": None}


def test_not_installable_without_uv(client, monkeypatch):
    monkeypatch.setattr(local_sorting, "find_uv", lambda: None)
    body = client.get(URL).json()
    assert body["installable"] is False and body["detail"] == local_sorting.NO_UV
    response = client.post(URL, json={})
    assert response.status_code == 400 and response.json()["detail"] == local_sorting.NO_UV
    assert not FakePopen.made


def test_not_installable_on_intel_mac(client, monkeypatch):
    monkeypatch.setattr(local_sorting, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(local_sorting, "platform", SimpleNamespace(machine=lambda: "x86_64"))
    assert client.get(URL).json()["detail"] == local_sorting.INTEL_MAC
    assert client.post(URL, json={}).status_code == 400
    monkeypatch.setattr(local_sorting, "platform", SimpleNamespace(machine=lambda: "arm64"))
    assert client.get(URL).json()["installable"] is True


def test_post_runs_uv_then_reports_ok(client, monkeypatch):
    invalidated = []
    monkeypatch.setattr(importlib, "invalidate_caches", lambda: invalidated.append(True))
    FakePopen.release = threading.Event()
    response = client.post(URL, json={})
    assert response.status_code == 202 and response.json()["running"] is True
    assert client.get(URL).json()["running"] is True
    FakePopen.release.set()
    body = finished(client)
    assert body["ok"] is True and body["detail"] is None and body["seconds"] >= 0
    assert invalidated
    args = FakePopen.made[0].args
    assert args[0] == "/bin/uv" and args[1] == "sync" and ["--extra", "local-sorting"] == args[4:6] and "--inexact" in args


def test_an_install_that_cant_run_finishes_failed_and_can_be_tried_again(client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("no such file")
    monkeypatch.setattr(local_sorting.subprocess, "Popen", broken)
    client.post(URL, json={})
    body = finished(client)
    assert body["ok"] is False and "no such file" in body["detail"]
    assert client.post(URL, json={}).status_code == 202


def test_failure_detail_is_the_last_lines(client):
    FakePopen.code, FakePopen.lines = 1, [f"line {i}\n" for i in range(30)]
    client.post(URL, json={})
    body = finished(client)
    assert body["ok"] is False and body["detail"].splitlines() == [f"line {i}" for i in range(10, 30)]


def test_second_post_while_running_is_409(client):
    FakePopen.release = threading.Event()
    client.post(URL, json={})
    response = client.post(URL, json={})
    assert response.status_code == 409 and response.json()["detail"] == "PyTorch is already being installed."
    FakePopen.release.set()
    finished(client)
    assert len(FakePopen.made) == 1


def test_already_installed_runs_nothing(client, monkeypatch):
    monkeypatch.setattr(app_settings, "local_sorting_available", lambda: True)
    response = client.post(URL, json={})
    assert response.status_code == 202
    assert response.json()["ok"] is True and response.json()["running"] is False
    assert not FakePopen.made
