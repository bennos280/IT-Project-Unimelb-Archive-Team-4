import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone, timedelta

from backend import database
from backend import models
from backend.main import app, get_db

# Setup an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Fixture to create tables before and drop tables after tests
@pytest.fixture(autouse=True)
def setup_database():
    models.Base.metadata.create_all(bind=engine)
    yield
    models.Base.metadata.drop_all(bind=engine)

# Override the get_db dependency to use the test database session
@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

# ----------------------------------------------- get_survey()

#CHANGED - get_survey parameter name from 'id' TO 'survey_id'
def test_get_survey_not_found(client):
    response = client.get("/survey/nonexistent_survey")
    assert response.status_code == 404
    assert response.json() == {"detail": "Survey not found"}

# CHANGED - lookup with dict key TO groupings_coded.get(f.field_title, "Miscellaneous")
def test_get_survey_success(client, db_session):
    # insert fake survey rows
    survey = models.Survey(survey_id="12345", bundle_id="6789")
    page = models.Page(page_id="12345_00001", survey_id="12345", category="main", import_path="img.png", revision_no=0, bundle_id="6789")
    field = models.Field(field_title="field", page_id="12345_00001", text_raw="raw")
    resident = models.Resident(page_id="12345_00001", resident_no=20)
    resident_field = models.ResidentField(page_id="12345_00001", resident_no=20, resident_field_title="relationship", text_raw="Head")
    db_session.add_all([survey, page, field, resident, resident_field])
    db_session.commit()

    response = client.get("/survey/12345")
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == "12345"
    assert data["title"] == "Wilfred Prest Survey"
    assert len(data["pages"]) == 1
    assert data["pages"][0]["id"] == "12345_00001"
    assert data["pages"][0]["fields"][0]["id"] == "field"
    assert data["pages"][0]["fields"][0]["value"] == "raw"
    assert data["pages"][0]["fields"][1]["id"] == "residents.20.relationship"
    assert data["pages"][0]["fields"][1]["value"] == "Head"

#------------------------------------------------- get_reviewers()
def test_get_reviewers_empty(client):
    response = client.get("/reviewers")
    assert response.status_code == 200
    assert response.json() == []

#------------------------------------------------ create_reviewer()
def test_create_reviewer_success(client):
    payload = {"id": 101, "name": "Alice"}
    response = client.post("/reviewers", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["reviewer_id"] == 101
    assert data["name"] == "Alice"

def test_create_reviewer_empty_name(client):
    payload = {"id": 102, "name": "   "}
    response = client.post("/reviewers", json=payload)
    
    assert response.status_code == 400
    assert response.json() == {"detail": "Enter a reviewer name."}


#------------------------------------------------- get_reviews()
def test_get_reviews_empty_survey(client):
    response = client.get("/reviews/survey_999")
    assert response.status_code == 200
    assert response.json() == {"reviews": {}, "revisions": {}}

def test_get_reviews_latest(client, db_session):
    # insert 3 edits at different times on same field
    survey = models.Survey(survey_id="12345", bundle_id="6789")
    page = models.Page(page_id="12345_00001", survey_id="12345", category="main", import_path="img.png", revision_no=0, bundle_id="6789")
    field = models.Field(field_title="field", page_id="12345_00001", text_raw="raw")
    edit1 = models.Edit(edit_id=0, edit_text="old", page_id="12345_00001", 
                        field_title="field", time=datetime.now(timezone.utc))
    edit2 = models.Edit(edit_id=1, edit_text="newer", page_id="12345_00001", 
                        field_title="field", time=datetime.now(timezone.utc)+timedelta(days=1))
    edit2 = models.Edit(edit_id=2, edit_text="newest", page_id="12345_00001", 
                            field_title="field", time=datetime.now(timezone.utc)+timedelta(days=2))
    db_session.add_all([survey, page, field, edit1, edit2])
    db_session.commit()

    response = client.get("/reviews/12345")
    assert response.status_code == 200
    assert response.json()["reviews"]["12345_00001"]["field"]["value"] == "newest"


#------------------------------------------------- save_reviews()

#CHANGED - lookup by dict key to new_rev = payload.revisions.get(page_id), and check if new_rev is null after
def test_save_reviews_outdated_revision(client, db_session):
    survey = models.Survey(survey_id="12345", bundle_id="6789")
    #revision no is 5
    page = models.Page(page_id="12345_00001", survey_id="12345", category="main", 
                       import_path="img.png", revision_no=5, bundle_id="6789")
    db_session.add_all([survey, page])
    db_session.commit()

    payload = {
        "reviews": {
            "12345_00001": {
                "kitchen.food_storage": {
                    "value": "Updated value",
                    "original": "Bread",
                    "reviewer": "Alice",
                    "reviewerId": 1,
                    "savedAt": "2026-06-01T00:00:00Z"
                }
            }
        },
        "revisions": {
            "12345_00001": 3  #outdated compared to current revision_no=5
        }
    }

    response = client.post("/reviews/12345_00001", json=payload)
    assert response.status_code == 400
    assert response.json() == {"detail": "Revision number is outdated."}

def test_save_reviews_success(client, db_session):
    survey = models.Survey(survey_id="12345", bundle_id="6789")
    page = models.Page(page_id="12345_00001", survey_id="12345", category="main", 
                       import_path="img.png", revision_no=0, bundle_id="6789")
    db_session.add_all([survey, page])
    db_session.commit()

    payload = {
        "reviews": {
            "12345_00001": {
                "kitchen.food_storage": {
                    "value": "Updated value",
                    "original": "Bread",
                    "reviewer": "Alice",
                    "reviewerId": 1,
                    "savedAt": "2026-06-01T00:00:00Z"
                }
            }
        },
        "revisions": {
            "12345_00001": 1
        }
    }

    response = client.post("/reviews/12345_00001", json=payload)
    assert response.status_code == 250 or response.status_code == 200
    data = response.json()
    assert data["revision"] == 1
    assert "savedAt" in data