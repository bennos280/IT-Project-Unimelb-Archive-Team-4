from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import time
import models
import database

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ReviewerCreate(BaseModel):
    name: str

class SaveReviewsRequest(BaseModel):
    pageId: str
    revision: int
    changes: Dict[str, Dict[str, Any]]

@app.get("/reviewers")
def get_reviewers(db: Session = Depends(get_db)):
    # Extract unique users from edits table, or return a list of known reviewers
    users = db.query(models.Edit.user).filter(models.Edit.user != None).distinct().all()
    reviewers = [{"id": idx + 1, "name": u[0]} for idx, u in enumerate(users)]
    return reviewers

@app.post("/reviewers")
def create_reviewer(payload: ReviewerCreate, db: Session = Depends(get_db)):
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Enter a reviewer name.")
    
    # Check if user already exists in edits
    existing = db.query(models.Edit).filter(models.Edit.user == clean_name).first()
    # We return a mock ID or handle user creation. Since users are stored inline in edits, 
    # we can assign a deterministic ID based on hash or index.
    return {"id": abs(hash(clean_name)) % 10000, "name": clean_name}

@app.get("/reviews/{survey_id}")
def get_reviews(survey_id: str, db: Session = Depends(get_db)):
    # Find all pages belonging to this survey
    pages = db.query(models.Page).filter(models.Page.survey_id == survey_id).all()
    page_ids = [p.page_id for p in pages]

    reviews_dict = {}
    revisions_dict = {}

    if page_ids:
        # Fetch edits for these pages to build the reviews state
        edits = db.query(models.Edit).filter(models.Edit.page_id.in_(page_ids)).all()
        
        for page_id in page_ids:
            page_edits = [e for e in edits if e.page_id == page_id]
            revisions_dict[page_id] = len(page_edits)
            
            reviews_dict[page_id] = {}
            for e in page_edits:
                if e.field_title:
                    reviews_dict[page_id][e.field_title] = {
                        "value": e.edit_text,
                        "original": None,
                        "reviewer": e.user or "Unknown",
                        "reviewerId": abs(hash(e.user)) % 10000 if e.user else 0,
                        "savedAt": str(e.time or "")
                    }

    return {
        "reviews": reviews_dict,
        "revisions": revisions_dict
    }

@app.post("/reviews/{survey_id}")
def save_reviews(survey_id: str, payload: SaveReviewsRequest, db: Session = Depends(get_db)):
    page_id = payload.pageId
    client_revision = payload.revision
    changes = payload.changes

    # Verify current revision count from edits table
    current_revisions = db.query(models.Edit).filter(models.Edit.page_id == page_id).count()
    if current_revisions != client_revision:
        raise HTTPException(
            status_code=409,
            detail="This page changed in another tab. Export your draft, then reload."
        )

    timestamp = time.time()
    
    for field_title, edit in changes.items():
        # Insert new edit row
        new_edit = models.Edit(
            edit_text=edit.get("value"),
            user=str(edit.get("reviewerId")), # or look up reviewer name if mapped
            time=timestamp,
            page_id=page_id,
            field_title=field_title
        )
        db.add(new_edit)

        # Update decoded_value in fields table if it exists
        field_row = db.query(models.Field).filter(
            models.Field.page_id == page_id,
            models.Field.field_title == field_title
        ).first()
        
        if field_row:
            field_row.decoded_value = edit.get("value")

    db.commit()
    new_revision = current_revisions + len(changes)
    return {"revision": new_revision, "savedAt": str(timestamp)}