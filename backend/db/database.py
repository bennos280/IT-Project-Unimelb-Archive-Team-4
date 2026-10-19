from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.common import ROOT

#the db file, wherever the server is started from
SQLALCHEMY_DATABASE_URL = f"sqlite:///{Path(__file__).parent / 'prestcribe.db'}"

#an engine for a SQLite db: foreign keys checked, and a 15 s wait so the API and the worker can use it at once
def make_engine(url):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})
    #not WAL: every saved change is in the db file itself
    event.listen(engine, "connect", lambda con, _: con.executescript("PRAGMA foreign_keys=ON; PRAGMA journal_mode=DELETE"))
    return engine

engine = make_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autoflush=False, bind=engine)
#named constraints, so migrations can find them again
Base = declarative_base(metadata=MetaData(naming_convention={
    "pk": "pk_%(table_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s", "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s"}))

def alembic_config(url=SQLALCHEMY_DATABASE_URL):
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config

#creates or updates the db's tables to match the migrations; existing rows are kept
def migrate(url=SQLALCHEMY_DATABASE_URL):
    command.upgrade(alembic_config(url), "head")

#db session dependency generator
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
