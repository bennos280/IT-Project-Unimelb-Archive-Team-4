"""Capture content inside the same transaction that changes it."""
import json
from backend.db import models

def snapshot(db, page_id, reviewer_id, action):
    tables = (models.Page, models.Field, models.Flag, models.Annotation, models.Edit)
    content = {model.__tablename__: [{col.name: getattr(row, col.name) for col in model.__table__.columns}
              for row in db.query(model).filter(model.page_id == page_id)] for model in tables}
    db.add(models.PageVersion(page_id=page_id, reviewer_id=reviewer_id, action=action,
                             snapshot=json.dumps(content, default=str)))
    db.flush()
