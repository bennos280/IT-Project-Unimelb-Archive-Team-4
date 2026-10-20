"""What the Settings page's Updates card, its Open folder buttons and the home page's Save a PrestCribe file ask of the API: GET
/version, POST /update, POST /folders/{which}/open and GET and POST /state, and the page sorting check. Nothing is fetched from GitHub, no installer is started, no
folder is opened and this process is never told to stop."""
import json
import os
import platform
import shlex
import sqlite3
import socket
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.parse import unquote

import pytest

from backend.api import main
from backend.db import models


class Reply:
    """A response to urlopen: a context manager that reads its body."""

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


@pytest.fixture
def root(tmp_path, monkeypatch):
    """This copy's folder, empty: no VERSION file, so not installed from a release."""
    monkeypatch.setattr(main, "ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def github(monkeypatch):
    """GitHub's latest release is v0.2.0; the requests made to it are listed (address, timeout)."""
    asked = []

    def urlopen(request, timeout=None):
        asked.append((request.full_url, timeout))
        return Reply(json.dumps({"tag_name": "v0.2.0"}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return asked


def version(client):
    """GET /version without the time it was checked and the computer it runs on, which have tests of their own."""
    reply = client.get("/version").json()
    del reply["checkedAt"], reply["system"]
    return reply


def test_a_copy_not_installed_from_a_release_has_no_version_and_isnt_updatable(client, root, github):
    assert version(client) == {"current": None, "latest": "v0.2.0", "releases": main.RELEASES, "error": None, "updatable": False}
    assert github == [(main.LATEST, 10)]


def test_an_installed_copy_is_updatable_only_when_the_latest_release_is_another_version(client, root, github):
    (root / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    assert version(client) == {"current": "v0.1.0", "latest": "v0.2.0", "releases": main.RELEASES, "error": None, "updatable": True}
    (root / "VERSION").write_text("v0.2.0\n", encoding="utf-8")
    assert client.get("/version").json()["updatable"] is False


@pytest.mark.parametrize("github_does", [URLError("offline"), "no tag", "not json"])
def test_when_github_cant_be_reached_or_understood_the_error_is_said_and_nothing_is_updatable(client, root, monkeypatch, github_does):
    (root / "VERSION").write_text("v0.1.0", encoding="utf-8")

    def urlopen(request, timeout=None):
        if isinstance(github_does, Exception):
            raise github_does
        return Reply(b"{}" if github_does == "no tag" else b"<html>")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert version(client) == {"current": "v0.1.0", "latest": None, "releases": main.RELEASES,
                               "error": "Couldn't reach GitHub to check for updates.", "updatable": False}


def test_the_time_it_was_checked_is_now_in_utc(client, root, github):
    before = datetime.now(timezone.utc)
    checked = datetime.fromisoformat(client.get("/version").json()["checkedAt"])
    assert checked.utcoffset() == timedelta(0) and before <= checked <= datetime.now(timezone.utc)


@pytest.mark.parametrize("pytorch", [True, False])
def test_the_computer_it_runs_on_is_given_with_whether_pages_can_be_sorted_on_it(client, root, github, monkeypatch, pytorch):
    monkeypatch.setattr(main.app_settings, "local_sorting_available", lambda: pytorch)
    system = client.get("/version").json()["system"]
    assert system == {"os": system["os"], "python": platform.python_version(), "pytorch": pytorch}
    assert system["os"] and system["os"].endswith(f"({platform.machine()})")


@pytest.mark.parametrize("on, system, release, machine, mac, named", [
    ("win32", "Windows", "11", "AMD64", "", "Windows 11 (AMD64)"),
    ("darwin", "Darwin", "23.5.0", "arm64", "14.5", "macOS 14.5 (arm64)"),  # the macOS version, not the kernel's
    ("linux", "Linux", "6.8.0-45-generic", "x86_64", "", "Linux 6.8.0-45-generic (x86_64)")])
def test_the_system_is_named_with_its_version_and_chip(monkeypatch, on, system, release, machine, mac, named):
    monkeypatch.setattr(main.sys, "platform", on)
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "release", lambda: release)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    monkeypatch.setattr(platform, "mac_ver", lambda: (mac, ("", "", ""), machine))
    monkeypatch.setattr(platform, "python_version", lambda: "3.12.4")
    monkeypatch.setattr(main.app_settings, "local_sorting_available", lambda: True)
    assert main.system_info() == {"os": named, "python": "3.12.4", "pytorch": True}


@pytest.fixture
def stops(monkeypatch):
    """What an update would start and stop, only recorded: the installer's process, and the timer that ends this one. A real
    threading.Timer(1, os._exit) would end the test run, so os._exit refuses too, should it ever be reached."""
    did = {"processes": [], "timers": [], "started": 0}

    def exit_(code):
        raise AssertionError("the test run was told to exit")

    class Timer:
        def __init__(self, interval, function, args=None, kwargs=None):
            did["timers"].append((interval, function, args))

        def start(self):
            did["started"] += 1

    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: did["processes"].append((args, kwargs)))
    monkeypatch.setattr(threading, "Timer", Timer)
    monkeypatch.setattr(os, "_exit", exit_)
    did["exit"] = exit_
    return did


def test_a_copy_not_installed_from_a_release_cant_be_updated_and_is_told_to_use_git(client, root, stops):
    refused = client.post("/update")
    assert (refused.status_code, refused.json()["detail"]) == (400, "This copy wasn't installed from a release: update it with git pull.")
    assert stops["processes"] == [] and stops["timers"] == []


def test_updating_starts_the_installer_in_its_own_process_for_this_folder_then_stops_this_copy(client, root, stops, github):
    (root / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    accepted = client.post("/update")
    assert (accepted.status_code, accepted.json()) == (202, {"updating": True})
    [(args, kwargs)] = stops["processes"]
    installer = "install.ps1" if sys.platform == "win32" else "install.sh"
    assert f"{main.RELEASES}/latest/download/{installer}" in args[-1] and str(root) in args[-1]
    assert (kwargs["creationflags"] == subprocess.CREATE_NEW_CONSOLE) if sys.platform == "win32" else kwargs["start_new_session"] is True
    assert stops["timers"] == [(1, stops["exit"], [0])] and stops["started"] == 1  # stops itself a second later, so its files can be replaced
    assert github == [(f"{main.RELEASES}/latest/download/{installer}", 10)]  # the installer was fetched once before anything started


def test_tasks_waiting_or_running_hold_an_update_back_and_nothing_is_started(client, db, root, stops, github):
    (root / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    db.add(models.Job(kind="check", status="running"))
    db.commit()
    refused = client.post("/update")
    assert (refused.status_code, refused.json()["detail"]) == (409, "Wait for the tasks to finish before updating.")
    assert github == [] and stops["processes"] == [] and stops["timers"] == []


def test_an_installer_that_cant_be_downloaded_is_a_502_and_nothing_is_started(client, root, stops, monkeypatch):
    (root / "VERSION").write_text("v0.1.0\n", encoding="utf-8")

    def urlopen(request, timeout=None):
        raise URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    refused = client.post("/update")
    assert (refused.status_code, refused.json()["detail"]) == (502, "Couldn't download the installer: <urlopen error offline>")
    assert stops["processes"] == [] and stops["timers"] == []


@pytest.mark.parametrize("quote", ["'", "‘", "’", "‚", "‛"])  # PowerShell ends a single-quoted string at each
def test_a_folder_with_an_apostrophe_is_escaped_in_the_windows_installer_command_which_waits_for_enter_if_it_fails(client, root, stops, github, monkeypatch, quote):
    monkeypatch.setattr(main.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)  # only on Windows
    folder = root / f"Ben{quote}s copy"
    monkeypatch.setattr(main, "ROOT", folder)
    folder.mkdir()
    (folder / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    assert client.post("/update").status_code == 202
    [(args, kwargs)] = stops["processes"]
    assert f"-Folder '{str(folder).replace(quote, quote * 2)}'" in args[-1]
    assert args[-1].startswith("try {") and "catch {" in args[-1] and "Read-Host" in args[-1]


def test_a_folder_with_an_apostrophe_is_quoted_in_the_installer_command_on_a_mac_or_linux_which_runs_only_a_downloaded_script(client, root, stops, github, monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "linux")
    folder = root / "Ben's copy"
    monkeypatch.setattr(main, "ROOT", folder)
    folder.mkdir()
    (folder / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    assert client.post("/update").status_code == 202
    [(args, kwargs)] = stops["processes"]
    assert f"PRESTCRIBE_HOME={shlex.quote(str(folder))} sh" in args[-1] and kwargs["start_new_session"] is True
    assert " -o " in args[-1] and "| sh" not in args[-1]  # sh isn't fed the download as it arrives


@pytest.fixture
def work(db):
    """A page, read off a scan and with a field, a person and this computer's page sorting choice, besides the series and page types."""
    db.add(models.Bundle(bundle_id="b", source_pdf="b.pdf", collection_id=1))
    db.add(models.Reviewer(reviewer_id=1, name="Alex"))
    db.flush()
    db.add(models.Page(page_id="b/p1", bundle_id="b", category="main", import_path="scan.png"))
    db.flush()
    db.add(models.Field(page_id="b/p1", field_title="address", text_raw="1 High St"))
    db.add(models.AppSetting(key="page_sorting", value="model"))
    db.commit()


def saved(client, tmp_path, **params):
    """Saves a PrestCribe file as the API gives it, and how many rows each table of interest has in it."""
    reply = client.get("/state", params=params)
    assert reply.status_code == 200
    file = tmp_path / "saved.db"
    file.write_bytes(reply.content)
    with sqlite3.connect(file) as saved_db:
        tables = ("collections", "page_types", "record_levels", "reviewers", "bundles", "pages", "fields", "app_settings")
        counts = {table: saved_db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}
    saved_db.close()
    return unquote(reply.headers["content-disposition"]), counts


def test_a_saved_file_holds_everything_unless_only_the_setup_is_asked_for(client, db, work, tmp_path):
    name, counts = saved(client, tmp_path)
    assert counts == {"collections": 1, "page_types": 4, "record_levels": 1, "reviewers": 1, "bundles": 1, "pages": 1, "fields": 1, "app_settings": 1}
    assert ".prestcribe" in name and "setup" not in name
    assert saved(client, tmp_path, content="everything")[1] == counts


def test_a_setup_only_file_keeps_the_series_and_how_theyre_read_but_no_pages_or_this_computers_choices(client, db, work, tmp_path):
    name, counts = saved(client, tmp_path, content="setup")
    assert counts == {"collections": 1, "page_types": 4, "record_levels": 1, "reviewers": 1, "bundles": 0, "pages": 0, "fields": 0, "app_settings": 0}
    assert "PrestCribe setup " in name and ".prestcribe" in name
    assert db.query(models.Page).count() == 1 and db.query(models.AppSetting).count() == 1  # what's here is as it was


def test_a_file_can_be_saved_as_only_everything_or_the_setup(client):
    assert client.get("/state", params={"content": "pages"}).status_code == 422


@pytest.fixture
def opened(root, monkeypatch):
    """The scans' and the results' folders are inside this copy's (temporary) folder, a few levels down and not made yet. What
    would open them is only recorded, under the platform the test names: nothing on this computer is opened."""
    did = []
    monkeypatch.setattr(main, "settings", lambda: {"DATA": str(root / "no" / "scans"), "OUTPUT": str(root / "results")})
    monkeypatch.setattr(os, "startfile", lambda path: did.append(("startfile", str(path))), raising=False)  # only on Windows
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: did.append(("Popen", args)))
    return did


@pytest.mark.parametrize("which, where", [("data", "no/scans"), ("output", "results")])
@pytest.mark.parametrize("on, command", [("win32", None), ("darwin", "open"), ("linux", "xdg-open")])
def test_a_folder_is_made_and_opened_the_way_this_computer_opens_folders(client, root, opened, monkeypatch, on, command, which, where):
    monkeypatch.setattr(main.sys, "platform", on)
    folder = root / where
    assert not folder.exists()
    reply = client.post(f"/folders/{which}/open")
    assert (reply.status_code, reply.content) == (204, b"")
    assert folder.is_dir()
    assert opened == [("startfile", str(folder.resolve())) if command is None else ("Popen", [command, str(folder.resolve())])]


def test_a_folder_already_there_is_opened_as_it_is(client, root, opened, monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "linux")
    (root / "results").mkdir()
    (root / "results" / "run.txt").write_text("kept", encoding="utf-8")
    assert [client.post("/folders/output/open").status_code for _ in range(2)] == [204, 204]
    assert (root / "results" / "run.txt").read_text(encoding="utf-8") == "kept"
    assert opened == [("Popen", ["xdg-open", str((root / "results").resolve())])] * 2


@pytest.mark.parametrize("which", ["elsewhere", "DATA", "scans"])
def test_only_the_data_and_output_folders_can_be_opened(client, root, opened, which):
    assert client.post(f"/folders/{which}/open").status_code == 422
    assert opened == [] and not (root / "no").exists() and not (root / "results").exists()


@pytest.mark.parametrize("on, fails", [("win32", "startfile"), ("darwin", "Popen"), ("linux", "Popen")])
def test_a_folder_that_cant_be_opened_is_a_500_saying_why(client, root, opened, monkeypatch, on, fails):
    def refuse(*args, **kwargs):
        raise OSError("no program opens folders")

    monkeypatch.setattr(main.sys, "platform", on)
    monkeypatch.setattr(os if fails == "startfile" else subprocess, fails, refuse, raising=False)
    reply = client.post("/folders/output/open")
    assert (reply.status_code, reply.json()["detail"]) == (500, "The folder couldn't be opened: no program opens folders")
    assert opened == []


def test_a_folder_that_cant_be_made_is_a_500_and_nothing_is_opened(client, root, opened, monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "linux")
    (root / "results").write_text("a file where the folder should be", encoding="utf-8")
    reply = client.post("/folders/output/open")
    assert reply.status_code == 500 and reply.json()["detail"].startswith("The folder couldn't be opened: ")
    assert opened == []


def test_the_reason_a_folder_couldnt_be_opened_is_cut_to_300_characters(client, root, opened, monkeypatch):
    def refuse(args, **kwargs):
        raise OSError("x" * 500)

    monkeypatch.setattr(main.sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "Popen", refuse)
    detail = client.post("/folders/data/open").json()["detail"]
    assert detail == ("The folder couldn't be opened: " + "x" * 500)[:300]


def setup_file(client, tmp_path, version=None):
    """A setup-only PrestCribe file saved here, at the given migration (None: before the first)."""
    file = tmp_path / "setup.db"
    file.write_bytes(client.get("/state", params={"content": "setup"}).content)
    with sqlite3.connect(file) as setup:
        assert setup.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0] == 0
        setup.execute("CREATE TABLE alembic_version (version_num TEXT)")  # which the test database, built from the models, hasn't
        if version:
            setup.execute("INSERT INTO alembic_version VALUES (?)", (version,))
    setup.close()
    return file.read_bytes()


def backups(root):
    return sorted(path.name for path in (root / "backend" / "db").glob("prestcribe-backup-*.db"))


def test_a_setup_only_file_opened_here_keeps_this_computers_own_choices_and_what_was_here_is_backed_up(client, db, work, root, tmp_path):
    (root / "backend" / "db").mkdir(parents=True)
    assert client.post("/state", content=setup_file(client, tmp_path)).json() == {"opened": True}
    db.expire_all()
    assert [(row.key, row.value) for row in db.query(models.AppSetting)] == [("page_sorting", "model")]
    assert db.query(models.Page).count() == 0  # the rest is the file's
    [backup] = backups(root)
    with sqlite3.connect(root / "backend" / "db" / backup) as kept:
        assert kept.execute("SELECT page_id FROM pages").fetchall() == [("b/p1",)]
    kept.close()


@pytest.mark.parametrize("body, status, detail", [
    (b"not a database", 400, "That isn't a PrestCribe file."),
    ("newer", 409, "That file was saved by a newer PrestCribe. Update this one first (Settings, then About), then open it."),
])
def test_a_file_that_cant_be_opened_here_is_refused_and_nothing_here_changes(client, db, work, root, tmp_path, body, status, detail):
    (root / "backend" / "db").mkdir(parents=True)
    body = setup_file(client, tmp_path, version="zzz999") if body == "newer" else body
    refused = client.post("/state", content=body)
    assert (refused.status_code, refused.json()["detail"]) == (status, detail)
    db.expire_all()
    assert db.query(models.Page).count() == 1 and backups(root) == []


def test_tasks_waiting_or_running_hold_a_file_back_and_nothing_here_changes(client, db, work, root, tmp_path):
    (root / "backend" / "db").mkdir(parents=True)
    db.add(models.Job(kind="check", status="waiting"))
    db.commit()
    refused = client.post("/state", content=setup_file(client, tmp_path))
    assert (refused.status_code, refused.json()["detail"]) == (409, "Wait for the tasks waiting or running to finish (Tasks, top right), then open it.")
    db.expire_all()
    assert db.query(models.Page).count() == 1 and backups(root) == []


@pytest.fixture
def sorting(client, monkeypatch):
    """Page sorting is available here and its check fails with the error the test gives."""
    from backend.pipeline.identify import identify
    monkeypatch.setattr(main, "_checked", {})
    monkeypatch.setattr(main.app_settings, "local_sorting_available", lambda: True)

    def fails(error):
        def identify_pages(paths):
            raise error
        monkeypatch.setattr(identify, "identify_pages", identify_pages)
        return client.post("/page-sorting/check").json()

    return fails


class ConnectionError(OSError):  # as requests' is, which isn't Python's
    pass


def chained():
    try:
        raise URLError("offline")
    except URLError as error:
        try:
            raise RuntimeError("download failed") from error
        except RuntimeError as outer:
            return outer


@pytest.mark.parametrize("error", [URLError("offline"), ConnectionResetError("reset"), socket.gaierror("no name"), ConnectionError("no route"), chained()])
def test_a_check_that_cant_download_the_sorting_model_says_to_check_the_internet(sorting, error):
    reply = sorting(error)
    assert reply["ok"] is False and "check the internet" in reply["detail"]


@pytest.mark.parametrize("error", [OSError("DLL load failed while importing _C"), FileNotFoundError("model.safetensors"), ValueError("bad")])
def test_a_check_that_fails_any_other_way_doesnt_blame_the_internet(sorting, error):
    reply = sorting(error)
    assert reply["ok"] is False and "check the internet" not in reply["detail"] and reply["detail"].startswith("Page sorting on this computer failed: ")
