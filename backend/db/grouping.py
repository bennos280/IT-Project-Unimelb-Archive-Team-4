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


#what one record of a collection is called on screen: its bottom level's name, else (each item one record) record
def record_name(db, collection_id):
    found = levels(db, collection_id)
    return found[-1].name if found else "record"


#a record name with its article; ponytail: "an" before a vowel letter, so "an hour" and "a unit" come out wrong
def a_record(name):
    return f"{'an' if name[:1] in 'aeiou' else 'a'} {name}"


#the rule pipeline.Run.grouping takes: whether each item is one record (no levels), else the top level's page types that start
#a survey and those that join the survey whose number they show, the field holding that number (None: page order only), every
#type's label and what a record is called, for the review flags
def rule(db, collection_id):
    found = levels(db, collection_id)
    top = level_json(found[0]) if found else {"name": "record", "starts": [], "matched": [], "key": None}
    return {"one_per_item": not found, "starts": set(top["starts"]), "matched": set(top["matched"]), "key": top["key"],
            "labels": {t.name: t.label for t in db.query(models.PageType).filter_by(collection_id=collection_id)},
            "record": top["name"]}


#page type -> the field its templates must have, as grouping reads it
def required_fields(db):
    return {t: level.record_key for level in db.query(models.RecordLevel) if level.record_key
            for t in json.loads(level.starts) + json.loads(level.matched)}
