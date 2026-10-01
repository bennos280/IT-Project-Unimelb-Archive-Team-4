from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any
import models
import database
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
"""
class Field(BaseModel):
    id: str #field_title
    label: str #field title prettier
    group: str #???
    value: str #raw

class Page(BaseModel):
    id: str
    type: str
    imageUrl: str
    fields: list[Field]

class SurveyResponse(BaseModel):
    id: str
    title: str
    pages: list[Page]
"""

# (incoming JSON data looks like this)
class CreateReviewerRequest(BaseModel):
    id: int
    name: str

class Review(BaseModel):
    value: str
    original: str
    reviewer: str
    reviewerId: int
    savedAt: str

class SaveReviewsRequest(BaseModel):
    reviews: Dict[str, Dict[str, Review]] #(pageid, (field_id, review)
    revisions: Dict[str, int] #(pageid, revision_no)

#return a survey
@app.get("/survey/{survey_id}")
def get_survey(id: str, db: Session = Depends(get_db)):
    #check if survey exists
    survey = db.query(models.Survey).filter(models.Survey.survey_id == id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    #select pages belonging to survey
    pages = db.query(models.Page).filter(models.Page.survey_id == id).all()

    #list of pages to be returned
    pages_list = []
    for p in pages:
        #list of fields to be returned per page
        fields_list = []

        #fill in fields list
        fields = db.query(models.Field).filter(models.Field.page_id == p.page_id).all()
        for f in fields:
            f_split = f.field_title.rsplit('.',1)
            label = None
            group = None #right now this only works for 1 nested layer
            if len(f_split) > 1:
                label = f_split[1].replace('_', ' ').capitalize()
                group = f_split[0].replace('_', ' ').capitalize()
            else:
                label = f.field_title.replace('_', ' ').capitalize()
            fields_list.append({
                "id": f.field_title,
                "label": label,
                "group": group,
                "value": f.text_raw,
            })

        resident_fields = db.query(models.ResidentField).filter(models.ResidentField.page_id == p.page_id).all()
        for rf in resident_fields:
            # "residents.0.relationship"
            fields_list.append({
                "id": "residents." + f"{rf.resident_no}" + rf.resident_field_title,
                "label": rf.resident_field_title.replace('_', ' ').capitalize(),
                "group": "wip",
                "value": rf.text_raw,
            })

        children = db.query(models.OtherChild).filter(models.OtherChild.page_id == p.page_id).all()
        for c in children:
            # "other_children.died.0"
            fields_list.append({
                "id": "other_children." + c.residence + f"{c.child_no}",
                "label": "Other children: " + c.residence,
                "group": "wip",
                "value": c.text_raw,
            })
            
        annotations = db.query(models.Annotation).filter(models.Annotation.page_id == p.page_id).all()
        for a in annotations:
            # "annotation.0"
            fields_list.append({
                "id": "annotation." + f"{a.annotation_no}",
                "label": "Annotation",
                "group": "wip",
                "value": a.text_raw,
            })

        #give fields list to page, put page in page list
        pages_list.append({
            "id": p.page_id,
            "type": p.category,
            "imageUrl": p.import_path,
            "fields": fields_list,
        })

    #return everything together
    return {"id":id, "title":"Wilfred Prest Survey", "pages":pages_list}


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
    if db.query(models.Edit).filter(models.Reviewer.reviewer_id == id).first():
        raise HTTPException(status_code=400, detail="Reviewer id already exists.")

    if db.query(models.Edit).filter(models.Reviewer.name == clean_name).first():
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
        edits = db.query(models.Edit).filter(models.Edit.page_id.in_(page_ids)).all()
        
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

            # WIP HOW do i know this returns the llllllatest edit on a field???

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
                    raw = db.query(models.ResidentField.text_raw).filter(models.ResidentField.field_title == e.field_title, 
                                                                         models.ResidentField.page_id == e.page_id,
                                                                         models.ResidentField.resident_no == e.resident_no).scalar()
                    final_field_id = "residents." + f"{e.resident_no}" + e.field_title
                elif e.child_no:
                    child = db.query(models.OtherChild).filter(models.OtherChild.child_no == e.child_no, 
                                                                 models.OtherChild.page_id == e.page_id).first()
                    raw = child.text_raw
                    residence = child.residence
                    final_field_id = "other_children." + residence + f"{e.child_no}"
                elif e.annotation_no:
                    raw = db.query(models.Field.text_raw).filter(models.Annotation.annotation_no == e.annotation_no, 
                                                                 models.Annotation.page_id == e.page_id).scalar()
                    final_field_id = "annotations." + f"{e.annotation_no}"

                print(page_id + final_field_id)
                #fill in review entry
                if raw and final_field_id:
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
def save_reviews(survey_id: str, payload: SaveReviewsRequest, db: Session = Depends(get_db)):
    if not payload.reviews:
        raise HTTPException(status_code=400, detail="No reviews given.")

    #get page id
    page_id = list(payload.reviews.keys())[0]
    if not page_id:
        raise HTTPException(status_code=400, detail="Page does not exist.")
    #get page from db
    page = db.query(models.Page).filter(models.Page.page_id == page_id).first()

    #--UPDATE REVISION NO--#
    #get current revision no
    curr_rev = page.revision_no if page else None

    #get new revision no
    if payload.revisions:
        new_rev = payload.revisions[page_id]

    if curr_rev < new_rev:
        #update revision number in db
        page.revision_no = new_rev
    else:
        #if revision outdated, reject the save
        raise HTTPException(status_code=400, detail="Revision number is outdated.")

    
    #--INSERT EDITS AND REVIEWERS--#
    #get current time
    timestamp = datetime.now(timezone.utc)

    reviews = payload.reviews[page_id]

    for field_title, review in reviews.items():
        ft_split = field_title.split(".")

        #make a new edit row
        edit_to_insert = models.Edit()

        #make and fill in a reviewer row
        reviewer_to_insert = models.Reviewer()
        reviewer_to_insert.name = review.reviewer
        reviewer_to_insert.reviewer_id = review.reviewerId

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
        elif ft_split[0] == "annotations":
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

        #add reviewer if not already in there
        existing_reviewer = db.query(models.Reviewer).filter(models.Reviewer.reviewer_id == reviewer_to_insert.reviewer_id).first()
        if not (existing_reviewer):
            db.add(reviewer_to_insert)

        #add edit
        db.add(edit_to_insert)

    db.commit()

    return {"revision": new_rev, "savedAt": str(timestamp)}
