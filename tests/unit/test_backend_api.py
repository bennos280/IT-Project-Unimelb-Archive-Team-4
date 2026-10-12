from backend.db import models


def add_in_order(db, *rows):
    """Adds the test rows one at a time after the bundle they belong to: the db checks foreign keys,
    and the models have no relationships to tell SQLAlchemy which to insert first."""
    for row in [models.Bundle(bundle_id="6789", source_pdf="6789.pdf"), *rows]:
        db.add(row)
        db.flush()

# ----------------------------------------------- get_survey()

#CHANGED - get_survey parameter name from 'id' TO 'survey_id'
def test_get_survey_not_found(client):
    response = client.get("/survey/nonexistent_survey")
    assert response.status_code == 404
    assert response.json() == {"detail": "Survey not found"}

# CHANGED - lookup with dict key TO groupings_coded.get(f.field_title, "Miscellaneous")
def test_get_survey_success(client, db):
    # insert fake survey rows
    survey = models.Survey(survey_id="12345", bundle_id="6789")
    page = models.Page(page_id="12345_00001", survey_id="12345", category="main", import_path="img.png", revision_no=0, bundle_id="6789")
    field = models.Field(field_title="field", page_id="12345_00001", text_raw="raw")
    resident = models.Resident(page_id="12345_00001", resident_no=20)
    resident_field = models.ResidentField(page_id="12345_00001", resident_no=20, resident_field_title="relationship", text_raw="Head")
    
    add_in_order(db, survey, page, field, resident, resident_field)
    db.commit()

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
    assert data["pages"][0]["imageUrl"] == "http://testserver/pages/12345_00001/image"
    assert data["pages"][0]["flags"] == []

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
    assert data["id"] == 101
    assert data["name"] == "Alice"

def test_create_reviewer_empty_name(client):
    payload = {"id": 102, "name": "   "}
    response = client.post("/reviewers", json=payload)
    
    assert response.status_code == 400
    assert response.json() == {"detail": "Enter a reviewer name."}

def test_create_reviewer_gives_the_next_id_and_a_known_name_its_reviewer(client):
    assert client.post("/reviewers", json={"name": "Alice"}).json() == {"id": 1, "name": "Alice"}
    assert client.post("/reviewers", json={"name": " Alice "}).json() == {"id": 1, "name": "Alice"}  # the same reviewer
    assert client.post("/reviewers", json={"id": 1, "name": "Bob"}).json() == {"detail": "Reviewer id already exists."}
    assert client.get("/reviewers").json() == [{"id": 1, "name": "Alice"}]


#------------------------------------------------- get_reviews()
def test_get_reviews_empty_survey(client):
    response = client.get("/reviews/survey_999")
    assert response.status_code == 200
    assert response.json() == {"reviews": {}, "revisions": {}}

#------------------------------------------------- save_reviews()

#the revision sent is the page's next one (the one the edits were made on, plus 1)
def test_save_reviews_outdated_revision(client, db):
    survey = models.Survey(survey_id="12345", bundle_id="6789")
    #revision no is 5
    page = models.Page(page_id="12345_00001", survey_id="12345", category="main", import_path="img.png", revision_no=5, bundle_id="6789")
    add_in_order(db, survey, page)
    db.commit()

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

    response = client.post("/reviews/12345", json=payload)
    assert response.status_code == 409
    assert response.json() == {"detail": "Revision number is outdated."}
    payload["revisions"]["12345_00001"] = 7  #more than one ahead of revision_no=5
    assert client.post("/reviews/12345", json=payload).status_code == 409

def test_save_reviews_success(client, db):
    survey = models.Survey(survey_id="12345", bundle_id="6789")
    page = models.Page(page_id="12345_00001", survey_id="12345", category="main", import_path="img.png", revision_no=0, bundle_id="6789")
    field = models.Field(page_id="12345_00001", field_title="kitchen.food_storage", text_raw="Bread")  # the field being corrected
    add_in_order(db, survey, page, field)
    db.commit()

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
            "12345_00001": 1  #the page's revision after this save
        }
    }

    response = client.post("/reviews/12345", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["revision"] == 1
    assert "savedAt" in data
    assert client.post("/reviews/12345", json=payload).json() == {"detail": "Revision number is outdated."}  # stale copy


def review(value, reviewer_id=1, reviewer="Alice"):
    return {"value": value, "reviewer": reviewer, "reviewerId": reviewer_id}


def a_survey_with_one_of_each(db):
    """A survey of one page with a field, a resident's field, a child and an annotation, numbered from 0 as loaded."""
    add_in_order(db, models.Survey(survey_id="12345", bundle_id="6789"),
                 models.Page(page_id="p", survey_id="12345", category="main", import_path="p.png", bundle_id="6789"),
                 models.Field(page_id="p", field_title="address", text_raw="5 Peel St."),
                 models.Field(page_id="p", field_title="tenure", text_raw=None),
                 models.Resident(page_id="p", resident_no=0),
                 models.ResidentField(page_id="p", resident_no=0, resident_field_title="age", text_raw="43"),
                 models.OtherChild(page_id="p", residence="living_elsewhere", child_no=0, text_raw="son 20"),
                 models.Annotation(page_id="p", annotation_no=0, text_raw="*"))
    db.commit()


def test_saved_edits_come_back_with_what_they_replaced(client, db):
    a_survey_with_one_of_each(db)
    ids = [f["id"] for f in client.get("/survey/12345").json()["pages"][0]["fields"]]
    assert ids == ["address", "tenure", "residents.0.age", "other_children.living_elsewhere.0", "annotations.0"]
    edits = {"address": review("6 Peel St."), "tenure": review("Owner"), "residents.0.age": review("44"),
             "other_children.living_elsewhere.0": review(None), "annotations.0": review("x")}
    first = client.post("/reviews/12345", json={"reviews": {"p": edits}, "revisions": {"p": 1}}).json()
    # a later save of the same field replaces the earlier edit; a known reviewer needs only their id
    assert client.post("/reviews/12345", json={"reviews": {"p": {"address": {"value": "7 Peel St.", "reviewerId": 1}}},
                                               "revisions": {"p": first["revision"] + 1}}).json()["revision"] == 2

    saved = client.get("/reviews/12345").json()
    assert saved["revisions"] == {"p": 2}
    assert saved["reviews"]["p"]["tenure"]["savedAt"] == first["savedAt"]  # the same time, in the same form
    assert {field: (r["value"], r["original"], r["reviewer"]) for field, r in saved["reviews"]["p"].items()} == {
        "address": ("7 Peel St.", "5 Peel St.", "Alice"), "tenure": ("Owner", None, "Alice"),
        "residents.0.age": ("44", "43", "Alice"), "other_children.living_elsewhere.0": (None, "son 20", "Alice"),
        "annotations.0": ("x", "*", "Alice")}


def test_save_refuses_pages_and_fields_that_are_not_there(client, db):
    a_survey_with_one_of_each(db)
    edit = {"address": review("6 Peel St.")}
    def save(reviews, revisions={"p": 1}, survey="12345"):
        return client.post(f"/reviews/{survey}", json={"reviews": reviews, "revisions": revisions})

    assert save({"p": edit}, survey="other").status_code == 404
    assert save({"p": edit}, revisions={}).json() == {"detail": "Page not in revisions."}
    assert save({"p": edit, "q": edit}).json() == {"detail": "Save one page at a time."}
    assert save({"p": {"address": review("1", reviewer_id=7, reviewer=None)}}).json() == {"detail": "Unknown reviewer 7."}
    for bad in ({"residents.3.age": review("1")}, {"annotations.\u00b2": review("1")},  # a superscript 2: a digit to isdigit, not to int
                {"residents.3.age": review("1"), "address": review("1", reviewer_id=2, reviewer="Bo")}):
        assert save({"p": bad}).json() == {"detail": "An edit is on a field that isn't on its page."}
    assert client.get("/reviews/12345").json() == {"reviews": {"p": {}}, "revisions": {"p": 0}}  # nothing was saved


def test_an_edited_code_comes_back_with_its_own_meaning(client, db):
    add_in_order(db, models.Survey(survey_id="12345", bundle_id="6789"),
                 models.Page(page_id="q", survey_id="12345", category="coded", import_path="q.png", bundle_id="6789"),
                 models.Field(page_id="q", field_title="washouse", text_raw="1", decoded_value="In separate laundry"))
    db.commit()
    client.post("/reviews/12345", json={"reviews": {"q": {"washouse": review("2")}}, "revisions": {"q": 1}})
    assert client.get("/reviews/12345").json()["reviews"]["q"]["washouse"]["decoded"] == "In kitchen"


#------------------------------------------------- page_image(), and what the reviewer is asked to check
def test_a_page_scan_is_served_by_its_page_id(client, db, tmp_path):
    (tmp_path / "scan.png").write_bytes(b"png")
    add_in_order(db, models.Page(page_id="p", category="main", import_path=str(tmp_path / "scan.png"), bundle_id="6789"))
    db.commit()
    assert client.get("/pages/p/image").content == b"png"
    assert client.get("/pages/nope/image").status_code == 404


def test_a_page_scan_not_on_this_computer_comes_from_the_archive_and_is_kept(client, db, tmp_path, monkeypatch, archive):
    from backend import scans
    archive.add("216441", {4: ("44", b"jpeg of page 4")})
    monkeypatch.setattr(scans, "settings", lambda: {"OUTPUT": str(tmp_path / "output")})
    add_in_order(db, models.Bundle(bundle_id="x", source_pdf="data/raw/Surveys/216441/x.pdf"),
                 *[models.Page(page_id=f"x_0000{n}", category="main", import_path=f"output/x/pages/x_0000{n}.png",
                               bundle_id="x") for n in (4, 9)])
    db.commit()

    assert client.get("/pages/x_00004/image").content == b"jpeg of page 4"
    assert client.get("/pages/x_00004/image").content == b"jpeg of page 4"
    assert archive.requests == ["/nodes/download/216441", "/assets/downloadwiz/44"]  # downloaded once
    assert client.get("/pages/x_00009/image").status_code == 404  # not on the archive


def test_a_page_the_archive_breaks_off_is_not_kept_and_its_bundle_is_not_asked_again_for_a_while(client, db, tmp_path,
                                                                                                   monkeypatch, archive):
    from backend import scans
    archive.add("216441", {4: ("44", b"jpeg of page 4")})
    archive.cut_short.add("44")
    monkeypatch.setattr(scans, "settings", lambda: {"OUTPUT": str(tmp_path / "output")})
    add_in_order(db, models.Bundle(bundle_id="x", source_pdf="data/raw/Surveys/216441/x.pdf"),
                 models.Page(page_id="x_00004", category="main", import_path="output/x/pages/x_00004.png", bundle_id="x"))
    db.commit()

    assert client.get("/pages/x_00004/image").status_code == 404
    assert not (tmp_path / "output" / "scans" / "216441").exists() or not any((tmp_path / "output" / "scans" / "216441").iterdir())
    asked = len(archive.requests)
    assert client.get("/pages/x_00004/image").status_code == 404
    assert len(archive.requests) == asked  # not asked again for RETRY seconds
    archive.cut_short.clear()
    scans.failed.clear()  # RETRY seconds later
    assert client.get("/pages/x_00004/image").content == b"jpeg of page 4"


def test_survey_flags_grouping_problems_unreadable_text_and_other_pages(client, db):
    add_in_order(db, models.Survey(survey_id="12345", bundle_id="6789"),
                 models.Page(page_id="p1", survey_id="12345", category="main", import_path="p1.png", bundle_id="6789"),
                 models.Field(page_id="p1", field_title="number_of_dwelling", text_raw="13"),
                 models.Field(page_id="p1", field_title="address", text_raw="26 Ral[?] St."),
                 models.Flag(page_id="p1", field_title="number_of_dwelling", kind="inconsistency", reason="Grouping: 2 coded cards"),
                 models.Page(page_id="p2", survey_id="12345", category="other", import_path="p2.png", bundle_id="6789"),
                 models.Field(page_id="p2", field_title="text", text_raw=None))
    db.commit()
    main, other = client.get("/survey/12345").json()["pages"]
    assert [(f["fieldId"], f["kind"]) for f in main["flags"]] == [("number_of_dwelling", "inconsistency"), ("address", "uncertain")]
    assert other["type"] == "notes"  # the review screen has no other type
    assert [(f["fieldId"], f["kind"]) for f in other["flags"]] == [("text", "uncertain")]
    assert "wasn't read" in other["flags"][0]["reason"]
