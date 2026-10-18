"""Shared by the backend tests: a fresh database file built from backend/db/models.py (foreign keys and other rules
checked, as in the real db) holding just the first collection and the built-in page types, and the API on it."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.db import database, models
from backend.db.database import make_engine


@pytest.fixture
def sessions(tmp_path):
    """Opens sessions on the test database, each on its own connection: a second one sees only what another has
    committed."""
    engine = make_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    models.Base.metadata.create_all(engine)
    with engine.begin() as con:  #as migrations 001, 007 and 008 add them
        con.execute(models.Collection.__table__.insert(), [{"collection_id": 1, "name": "Wilfred Prest Survey"}])
        con.execute(models.PageType.__table__.insert(), [{"name": name, "label": label, "built_in": True} for name, label in (
            ("main", "Main page"), ("notes", "Notes page"), ("coded", "Coded page"), ("other", "Other page"))])
    yield sessionmaker(autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def db(sessions):
    with sessions() as session:
        yield session


@pytest.fixture
def cli_db(sessions, monkeypatch):
    """The test database as the one that command-line runs and transcribe() open for themselves."""
    monkeypatch.setattr(database, "SessionLocal", sessions)
    return sessions


@pytest.fixture
def client(db):
    """The API, using the test database."""
    from backend.api.main import app, get_db
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
