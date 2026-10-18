"""The transcription choice the team makes on the Settings page (saved in the db). There is no default."""
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

def save_transcription_defaults(db, provider, model, effort):
    for key, value in zip(KEYS.values(), (provider, model, effort)):
        db.merge(models.AppSetting(key=key, value=value))
    db.commit()
