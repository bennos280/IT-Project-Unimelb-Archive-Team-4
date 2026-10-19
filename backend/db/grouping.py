"""How a collection's pages group into surveys (whether its items hold several, its page types' starts_record and
matched_by_key, and its record_key), as the pipeline's group step and the template checks read it."""
from backend.db import models


#what one record of a collection is called on screen
def record_name(collection):
    return collection.record_name or "record"


#a record name with its article; ponytail: "an" before a vowel letter, so "an hour" and "a unit" come out wrong
def a_record(name):
    return f"{'an' if name[:1] in 'aeiou' else 'a'} {name}"


#the rule pipeline.Run.grouping takes: whether each item is one record, else the page types that start a survey and those
#that join the survey whose number they show, the field holding that number (None: page order only), every type's label and
#what a record is called, for the review flags
def rule(db, collection_id):
    types = db.query(models.PageType).filter_by(collection_id=collection_id).all()
    collection = db.get(models.Collection, collection_id)
    several = collection.group_pages
    return {"one_per_item": not several, "starts": {t.name for t in types if several and t.starts_record},
            "matched": {t.name for t in types if several and t.matched_by_key}, "key": collection.record_key,
            "labels": {t.name: t.label for t in types}, "record": record_name(collection)}


#page type -> the field its templates must have, as grouping reads it
def required_fields(db):
    return {t.name: key for t, key, several in db.query(models.PageType, models.Collection.record_key, models.Collection.group_pages)
            .join(models.Collection) if key and several and (t.starts_record or t.matched_by_key)}
