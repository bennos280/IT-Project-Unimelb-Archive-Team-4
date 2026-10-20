"""The transcription choice the team makes on the Settings page (saved in the db; there is no default), and how pages are
sorted into page types."""
import importlib.util
import sys

from sqlalchemy.exc import SQLAlchemyError

from backend.db import database, models

FIELDS = ("provider", "model", "effort")
KEYS = {field: f"transcription.{field}" for field in FIELDS}
NOT_SET = "Choose a transcription model on the Settings page first."

#the saved choice, or None unless all three are saved
def transcription_defaults(db):
    rows = dict(db.query(models.AppSetting.key, models.AppSetting.value).filter(models.AppSetting.key.in_(KEYS.values())))
    return {field: rows[key] for field, key in KEYS.items()} if all(key in rows for key in KEYS.values()) else None

#for runs outside the API: through a session of its own; nothing saved, or a db without the app_settings table yet, exits with NOT_SET
def saved_choice_or_exit():
    try:
        with database.SessionLocal() as db:
            chosen = transcription_defaults(db)
    except SQLAlchemyError:
        chosen = None
    return chosen or sys.exit(NOT_SET)

#how a run sorts pages into page types: "local", the page sorting model on this computer (PyTorch), or "model", the reading
#model (the transcription choice); unsaved, the reading model, which works for any series on any computer
SORTING = "page_sorting"
SORTINGS = ("local", "model")

def local_sorting_available():
    return all(importlib.util.find_spec(name) for name in ("torch", "transformers"))

def page_sorting(db):
    saved = db.get(models.AppSetting, SORTING)
    return saved.value if saved else "model"

def save_page_sorting(db, method):
    db.merge(models.AppSetting(key=SORTING, value=method))
    db.commit()

#a page the model on this computer isn't sure of: "review" (it waits for a reviewer) or "model" (the reading model is asked)
UNSURE = "page_sorting.unsure"
#the reading model that sorts, when not the transcription choice: page_sorting.provider / .model / .effort
SORTER = {field: f"page_sorting.{field}" for field in FIELDS}

def sorting_settings(db):
    rows = dict(db.query(models.AppSetting.key, models.AppSetting.value).filter(models.AppSetting.key.in_([UNSURE, *SORTER.values()])))
    sorter = {field: rows[key] for field, key in SORTER.items()} if all(key in rows for key in SORTER.values()) else None
    return {"method": page_sorting(db), "unsure": rows.get(UNSURE, "review"), "sorter": sorter}

def save_sorting_settings(db, unsure=None, sorter=False):
    """sorter: {provider, model, effort}, None (the transcription choice again), or False (unchanged)."""
    if unsure is not None:
        db.merge(models.AppSetting(key=UNSURE, value=unsure))
    if sorter is not False:
        db.query(models.AppSetting).filter(models.AppSetting.key.in_(SORTER.values())).delete()
        for field, key in SORTER.items():
            if sorter:
                db.add(models.AppSetting(key=key, value=sorter[field]))
    db.commit()

def save_transcription_defaults(db, provider, model, effort):
    for key, value in zip(KEYS.values(), (provider, model, effort)):
        db.merge(models.AppSetting(key=key, value=value))
    db.commit()
