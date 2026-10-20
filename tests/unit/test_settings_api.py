"""What the home page's Save a PrestCribe file ask of the API: GET and POST /state, and the page sorting check."""
import sqlite3
import socket
from urllib.error import URLError
from urllib.parse import unquote

import pytest

from backend.api import main
from backend.db import models


@pytest.fixture
def root(tmp_path, monkeypatch):
    """This copy's folder, empty: no VERSION file, so not installed from a release."""
    monkeypatch.setattr(main, "ROOT", tmp_path)
    return tmp_path


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


def test_a_setup_only_file_opened_here_keeps_this_computers_own_choices(client, db, work, root, tmp_path, monkeypatch):
    monkeypatch.setattr(main.database, "migrate", lambda url: None)  # the file is as old as this database
    (root / "backend" / "db").mkdir(parents=True)
    file = tmp_path / "setup.db"
    file.write_bytes(client.get("/state", params={"content": "setup"}).content)
    with sqlite3.connect(file) as setup:
        assert setup.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0] == 0
        setup.execute("CREATE TABLE alembic_version (version_num TEXT)")  # which the test database, built from the models, hasn't
    setup.close()
    assert client.post("/state", content=file.read_bytes()).json() == {"opened": True}
    db.expire_all()
    assert [(row.key, row.value) for row in db.query(models.AppSetting)] == [("page_sorting", "model")]
    assert db.query(models.Page).count() == 0  # the rest is the file's


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
