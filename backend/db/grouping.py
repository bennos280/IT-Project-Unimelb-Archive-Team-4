"""How a collection's pages group into records: its levels of record (models.RecordLevel), each with the page types that start
or join one and the field holding its number, as the pipeline's group step and the template checks read them."""
import json

from backend.db import models


#a collection's levels, the top one first
def levels(db, collection_id):
    return db.query(models.RecordLevel).filter_by(collection_id=collection_id).order_by(models.RecordLevel.position).all()


#a level as the Setup tab shows and saves it
def level_json(level):
    return {"name": level.name, "starts": json.loads(level.starts), "matched": json.loads(level.matched), "key": level.record_key}


#what one record of a collection is called on screen: its level's name (a record's level is how deep it sits; no record: the
#bottom level's, the one a reviewer checks), else (no levels: each item one record) record
def record_name(db, collection_id, survey_id=None):
    found = levels(db, collection_id)
    depth = len(found) - 1
    if survey_id is not None:
        depth, parent = 0, db.get(models.Survey, survey_id).parent_id
        while parent is not None:
            depth, parent = depth + 1, db.get(models.Survey, parent).parent_id
    return found[min(depth, len(found) - 1)].name if found else "record"


#a record name with its article; ponytail: "an" before a vowel letter, so "an hour" and "a unit" come out wrong
def a_record(name):
    return f"{'an' if name[:1] in 'aeiou' else 'a'} {name}"


#the rule pipeline.Run.grouping takes: the collection's levels, top first (none: each item is one record), each with its name,
#the page types that start one and those that join the one whose number they show, and the field holding that number (None:
#page order only); and every type's label, for the review flags
def rule(db, collection_id):
    return {"levels": [level_json(level) for level in levels(db, collection_id)],
            "labels": {t.name: t.label for t in db.query(models.PageType).filter_by(collection_id=collection_id)}}


#whether a collection's pages group into records: a page type starts one of its top level, so a page can be in none or move
def grouped(db, collection_id):
    found = levels(db, collection_id)
    return bool(found and json.loads(found[0].starts))


#page type -> the fields its templates must have, as grouping reads them (a type can group in more than one level)
def required_fields(db):
    found = {}
    for level in db.query(models.RecordLevel):
        for t in json.loads(level.starts) + json.loads(level.matched) if level.record_key else []:
            found.setdefault(t, set()).add(level.record_key)
    return found
