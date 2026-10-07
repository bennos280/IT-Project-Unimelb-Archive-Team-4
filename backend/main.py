from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any
from backend import models
from backend import database
from backend.UI_groupings import groupings_main, groupings_coded
from datetime import datetime, timezone

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#db session dependency generator
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

#Pydantic models
# (incoming JSON data looks like this)
class CreateReviewerRequest(BaseModel):
    id: int
    name: str

class Review(BaseModel):
    value: str | None
    original: str | None
    reviewer: str
    reviewerId: int
    savedAt: str

class SaveReviewsRequest(BaseModel):
    reviews: Dict[str, Dict[str, Review]] #(pageid, (field_id, review)
    revisions: Dict[str, int] #(pageid, revision_no)

#return a survey
@app.get("/survey/{survey_id}")
def get_survey(survey_id: str, db: Session = Depends(get_db)):
    #check if survey exists
    survey = db.query(models.Survey).filter(models.Survey.survey_id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    #select pages belonging to survey
    pages = db.query(models.Page).filter(models.Page.survey_id == survey_id).all()

    #list of pages to be returned
    pages_list = []
    for p in pages:
        #list of fields and flags to be returned per page
        fields_list = []
        flags_list = []

        #fill in fields list
        fields = db.query(models.Field).filter(models.Field.page_id == p.page_id).all()
        for f in fields:
            label = None #nice version of field id
            group = None #a purely UI thing
            #look up in groupings dict
            #OR superfield if nested (right now this only works for 1 nested layer)
            #OR if not a regular field, also grouped differently (not in this loop)

            f_split = f.field_title.rsplit('.',1)
            if len(f_split) > 1:
                #if field was nested
                label = f_split[1].replace('_', ' ').capitalize()
                group = f_split[0].replace('_', ' ').capitalize()
            else:
                #not nested
                label = f.field_title.replace('_', ' ').capitalize()
                if (p.category == "coded"):
                    group = groupings_coded.get(f.field_title, "Miscellaneous")
                else:
                    #technically groupings main contains like a single entry for the notes category
                    group = groupings_main.get(f.field_title, "Miscellaneous")

            fields_list.append({
                "id": f.field_title,
                "label": label,
                "group": group,
                "value": f.text_raw,
            })

            if f.flag_type:
                flags_list.append({
                    "fieldId": f.field_title,
                    "kind": f.flag_type
                })

        resident_fields = db.query(models.ResidentField).filter(models.ResidentField.page_id == p.page_id).all()
        for rf in resident_fields:
            # "residents.0.relationship"
            id = "residents." + f"{rf.resident_no}" + "." + rf.resident_field_title
            fields_list.append({
                "id": id,
                "label": rf.resident_field_title.replace('_', ' ').capitalize(),
                "group": "Resident " + f"{rf.resident_no}",
                "value": rf.text_raw,
            })

            if rf.flag_type:
                flags_list.append({
                    "fieldId": id,
                    "kind": rf.flag_type
                })

        children = db.query(models.OtherChild).filter(models.OtherChild.page_id == p.page_id).all()
        for c in children:
            # "other_children.died.0"
            id = "other_children." + c.residence + "." + f"{c.child_no}"
            fields_list.append({
                "id": id,
                "label": "Other children: " + c.residence,
                "group": "Other Children",
                "value": c.text_raw,
            })

            if c.flag_type:
                flags_list.append({
                    "fieldId": id,
                    "kind": c.flag_type
                })
            
        annotations = db.query(models.Annotation).filter(models.Annotation.page_id == p.page_id).all()
        for a in annotations:
            # "annotation.0"
            id = "annotation." + f"{a.annotation_no}"
            fields_list.append({
                "id": id,
                "label": "Annotations",
                "group": "Annotations",
                "value": a.text_raw,
            })
            if a.flag_type:
                flags_list.append({
                    "fieldId": id,
                    "kind": a.flag_type
                })

        #give fields list to page, put page in page list
        pages_list.append({
            "id": p.page_id,
            "type": p.category,
            "imageUrl": p.import_path,
            "fields": fields_list,
            "flags": flags_list,
        })

    #return everything together
    return {"id":survey_id, "title":"Wilfred Prest Survey", "pages":pages_list}


#returns list of (reviewer_id, name)
@app.get("/reviewers")
def get_reviewers(db: Session = Depends(get_db)):
    reviewers = db.query(models.Reviewer).all()
    return reviewers

#inserts reviewer into db
@app.post("/reviewers")
def create_reviewer(payload: CreateReviewerRequest, db: Session = Depends(get_db)):

    #get name and id from payload
    clean_name = payload.name.strip()
    if not clean_name: #if empty
        raise HTTPException(status_code=400, detail="Enter a reviewer name.")

    id = payload.id

    #check if reviewer already exists
    if db.query(models.Reviewer).filter(models.Reviewer.reviewer_id == id).first():
        raise HTTPException(status_code=400, detail="Reviewer id already exists.")

    if db.query(models.Reviewer).filter(models.Reviewer.name == clean_name).first():
        raise HTTPException(status_code=400, detail="Reviewer name not unique.")

    #insert into db
    new_reviewer = models.Reviewer(reviewer_id = id, name=clean_name)
    db.add(new_reviewer)
    db.commit()
    db.refresh(new_reviewer)
    
    return new_reviewer

#returns all edits on a given survey
@app.get("/reviews/{survey_id}")
def get_reviews(survey_id: str, db: Session = Depends(get_db)):
    #select page_ids of this survey
    pages = db.query(models.Page).filter(models.Page.survey_id == survey_id).all()
    page_ids = [p.page_id for p in pages]
    
    reviews_dict = {} #page_id, (field_title, (edit, raw, reviewer, reviewer_id, timestamp))
    revisions_dict = {} #page_id, revision_no

    if page_ids:
        #select all edits of these page_ids
        #order now so later when looping through page_edits 
        # will update reviews_dict entry with same field_title key to latest edit
        edits = (db.query(models.Edit)
                 .filter(models.Edit.page_id.in_(page_ids))
                 .order_by(models.Edit.time.asc())
                 .all()
        )
        
        for page_id in page_ids:
            #get edits that belong to this page
            page_edits = [e for e in edits if e.page_id == page_id]
            
            #add entry to revisions dict
            if len(page_edits) > 0:
                page = db.query(models.Page).filter(models.Page.page_id == page_id).first()
                rev_no = page.revision_no if page else None
                revisions_dict[page_id] = rev_no
            #setup empty entry to reviews dict
            reviews_dict[page_id] = {}

            for e in page_edits:
                #An edit can be on either:
                # 1. field title
                # 2. resident no + resident field title
                # 3. child no
                # 4. annotation no

                final_field_id = None #the field id to return
                #example formats:
                # 1. "kitchen.food_storage"
                # 2. "residents.0.relationship"
                # 3. "other_children.died.0"
                # 4. "annotation.0"

                raw = None #the original unedited text

                #get final field id and raw
                if e.field_title:
                    raw = db.query(models.Field.text_raw).filter(models.Field.field_title == e.field_title, 
                                                                 models.Field.page_id == e.page_id).scalar()
                    final_field_id = e.field_title
                elif e.resident_no and e.resident_field_title:
                    raw = db.query(models.ResidentField.text_raw).filter(models.ResidentField.resident_field_title == e.resident_field_title, 
                                                                         models.ResidentField.page_id == e.page_id,
                                                                         models.ResidentField.resident_no == e.resident_no).scalar()
                    final_field_id = "residents." + f"{e.resident_no}" + "." + e.resident_field_title
                elif e.child_no:
                    child = db.query(models.OtherChild).filter(models.OtherChild.child_no == e.child_no, 
                                                                 models.OtherChild.page_id == e.page_id).first()
                    raw = child.text_raw
                    residence = child.residence
                    final_field_id = "other_children." + residence + "." + f"{e.child_no}"
                elif e.annotation_no:
                    raw = db.query(models.Annotation.text_raw).filter(models.Annotation.annotation_no == e.annotation_no, 
                                                                 models.Annotation.page_id == e.page_id).scalar()
                    final_field_id = "annotation." + f"{e.annotation_no}"

                #fill in review entry
                if final_field_id:
                    reviews_dict[page_id][final_field_id] = {
                        "value": e.edit_text,
                        "original": raw,
                        "reviewer": db.query(models.Reviewer.name).filter(models.Reviewer.reviewer_id == e.reviewer_id).scalar(),
                        "reviewerId": e.reviewer_id,
                        "savedAt": str(e.time or "")
                    }
    
    #return dicts
    return {
        "reviews": reviews_dict,
        "revisions": revisions_dict
    }

    
#inserts edit into db
@app.post("/reviews/{survey_id}")
def save_reviews(payload: SaveReviewsRequest, db: Session = Depends(get_db)):
    if not payload.reviews:
        raise HTTPException(status_code=400, detail="No reviews given.")

    #get page id
    page_id = list(payload.reviews.keys())[0]
    if not page_id:
        raise HTTPException(status_code=400, detail="Page does not exist.")
    #get page from db
    page = db.query(models.Page).filter(models.Page.page_id == page_id).first()

    if not page:
        raise HTTPException(status_code=404, detail="Page not found in database, cannot save review.")

    #--UPDATE REVISION NO--#
    #get current revision no
    curr_rev = page.revision_no if page else None

    #get new revision no
    if payload.revisions:
        new_rev = payload.revisions.get(page_id)
        if not new_rev:
            raise HTTPException(status_code=400, detail="Page not in revisions.")

    if curr_rev + 1 == new_rev:
        #update revision number in db
        page.revision_no = new_rev
    else:
        if curr_rev >= new_rev:
            #if revision outdated, reject the save
            raise HTTPException(status_code=400, detail="Revision number is outdated.")
        else:
            raise HTTPException(status_code=400, detail="Revision number greater than 1+ previous revision.")
    
    #--INSERT EDITS AND REVIEWERS--#
    #get current time
    timestamp = datetime.now(timezone.utc)

    reviews = payload.reviews[page_id]

    for field_title, review in reviews.items():
        ft_split = field_title.split(".")

        #check if reviewer exists in db
        existing_reviewer = db.query(models.Reviewer).filter(models.Reviewer.reviewer_id == review.reviewerId).first()
        if not (existing_reviewer):
            raise HTTPException(status_code=400, detail="Reviewer does not exist in database.")

        #make a new edit row
        edit_to_insert = models.Edit()

        #fill in edit row
        if ft_split[0] == "residents":
            edit_to_insert.reviewer_id = review.reviewerId
            edit_to_insert.edit_text = review.value
            edit_to_insert.time = timestamp
            edit_to_insert.page_id = page_id

            # "residents.0.relationship"
            edit_to_insert.resident_no = ft_split[1]
            edit_to_insert.resident_field_title = ft_split[2]

        elif ft_split[0] == "other_children":
            edit_to_insert.reviewer_id = review.reviewerId
            edit_to_insert.edit_text = review.value
            edit_to_insert.time = timestamp
            edit_to_insert.page_id = page_id

            # "other_children.died.0"
            edit_to_insert.child_no = ft_split[2]
        elif ft_split[0] == "annotation":
            edit_to_insert.reviewer_id = review.reviewerId
            edit_to_insert.edit_text = review.value
            edit_to_insert.time = timestamp
            edit_to_insert.page_id = page_id

            # "annotation.0"
            edit_to_insert.annotation_no = ft_split[1]
        else:
            edit_to_insert.reviewer_id = review.reviewerId
            edit_to_insert.edit_text = review.value
            edit_to_insert.time = timestamp
            edit_to_insert.page_id = page_id
            edit_to_insert.field_title = field_title
        
        #add edit
        db.add(edit_to_insert)

    db.commit()

    return {"revision": new_rev, "savedAt": str(timestamp)}
