"""How a collection's pages group into surveys (its page types' starts_record and matched_by_key, and its record_key), as
the pipeline's group step and the template checks read it."""
from backend.db import models


#the rule pipeline.Run.grouping takes: the page types that start a survey, those that join the survey whose number they show,
#the field holding that number (None: page order only), and every type's label for the review flags
def rule(db, collection_id):
    types = db.query(models.PageType).filter_by(collection_id=collection_id).all()
    return {"starts": {t.name for t in types if t.starts_record}, "matched": {t.name for t in types if t.matched_by_key},
            "key": db.get(models.Collection, collection_id).record_key, "labels": {t.name: t.label for t in types}}


#page type -> the field its templates must have, as grouping reads it
def required_fields(db):
    return {t.name: key for t, key in db.query(models.PageType, models.Collection.record_key).join(models.Collection)
            if key and (t.starts_record or t.matched_by_key)}
