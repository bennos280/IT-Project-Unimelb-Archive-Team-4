"""Shared by the backend tests: a fresh database file built from backend/db/models.py (foreign keys and other rules
checked, as in the real db) holding just the built-in page types, and the API on it."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.db import models
from backend.db.database import make_engine


@pytest.fixture
def sessions(tmp_path):
    """Opens sessions on the test database, each on its own connection: a second one sees only what another has
    committed."""
    engine = make_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    models.Base.metadata.create_all(engine)
    with engine.begin() as con:  #as migration 001 adds them
        con.execute(models.PageType.__table__.insert(), [{"name": name, "built_in": True} for name in ("main", "notes", "coded", "other")])
    yield sessionmaker(autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def db(sessions):
    with sessions() as session:
        yield session


@pytest.fixture
def client(db):
    """The API, using the test database."""
    from backend.api.main import app, get_db
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
