"""How a collection's pages group into records: its levels of record (models.RecordLevel), each with what one is made of and
the field holding its number, as the pipeline's group step and the template checks read them."""
import json

from backend.db import models


#a collection's levels, the top one first
def levels(db, collection_id):
    return db.query(models.RecordLevel).filter_by(collection_id=collection_id).order_by(models.RecordLevel.position).all()


#a level as the Setup tab shows and saves it, with the page types that start one and those matched by number, as grouping reads them
def level_json(level):
    parts = json.loads(level.parts)
    return {"name": level.name, "parts": parts, "key": level.record_key,
            "starts": [p["type"] for p in parts if p["how"] == "starts"], "matched": [p["type"] for p in parts if p["how"] == "matched"]}


#what one record of a collection is called on screen: its level's name, else (no levels: each item one record) record
def record_name(db, collection_id, survey_id=None):
    found = levels(db, collection_id)
    depth = len(found) - 1
    return found[min(depth, len(found) - 1)].name if found else "record"




#whether a collection's pages group into records: a page type starts one of its top level, so a page can be in none or move
def grouped(db, collection_id):
    found = levels(db, collection_id)
    return bool(found and level_json(found[0])["starts"])
