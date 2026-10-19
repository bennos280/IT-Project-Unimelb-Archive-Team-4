"""Classification never starts a job; explicit transcription archives reviewed content."""
import json
from pathlib import Path
from backend.db import models
from backend import worker
from backend.pipeline.transcribe import transcribe as transcription
from tests.unit.test_page_moves import seed


def setup_page(db, monkeypatch):
    seed(db)
    db.add(models.InstructionVersion(kind='prompt',body='Read',sha256='p'))
    db.add(models.InstructionVersion(kind='main',body='{"address":null}',sha256='m'))
    db.add(models.InstructionVersion(kind='coded',body='{"address":null}',sha256='c'))
    db.commit()
    monkeypatch.setattr(worker.scans,'page_scan',lambda *args:Path('sample.png'))
    monkeypatch.setattr(transcription,'transcribe',lambda *args,**kwargs:{'address':'New','model':kwargs['model']})


def queue(client, revision=0):
    return client.post('/page-transcription/b/p4',json={'revision':revision,'reviewerId':1,'model':'chosen-model','provider':'claude','effort':'low'})


def test_classification_is_immediate_preserves_reviews_and_does_not_queue(client,db):
    seed(db)
    response=client.put('/page-classification/b/p4',json={'pageType':'coded','revision':0,'reviewerId':1})
    assert response.status_code==200
    db.expire_all()
    page=db.get(models.Page,'b/p4')
    assert page.category=='coded' and page.needs_transcription
    assert db.query(models.Job).count()==0
    assert db.query(models.Edit).one().edit_text=='Correction'
    assert db.query(models.Field).one().text_raw=='Original'
    assert client.get('/survey/s1').json()['pages'][0]['needsTranscription']
    assert client.get('/progress').json()[0]['pages'][0]['status']=='Awaiting transcription'
    assert db.query(models.PageVersion).one().action=='change_type'


def test_same_type_transcription_preserves_old_reviews_in_history(client,db,monkeypatch):
    setup_page(db,monkeypatch)
    response=queue(client)
    assert response.status_code==200
    assert db.query(models.Edit).one().edit_text=='Correction'
    assert queue(client).status_code==409
    assert worker.work_once(db)
    db.expire_all()
    assert db.get(models.Job,response.json()['job']['id']).status=='done'
    assert db.query(models.Field).one().text_raw=='New'
    assert db.query(models.Edit).count()==0
    old=json.loads(db.query(models.PageVersion).one().snapshot)
    assert old['fields'][0]['text_raw']=='Original'
    assert old['edits'][0]['edit_text']=='Correction'
    assert not db.get(models.Page,'b/p4').needs_transcription


def test_failed_transcription_keeps_old_content(client,db,monkeypatch):
    setup_page(db,monkeypatch)
    def fail(*args,**kwargs):raise RuntimeError('model unavailable')
    monkeypatch.setattr(transcription,'transcribe',fail)
    job=queue(client).json()['job']
    worker.work_once(db);db.expire_all()
    assert db.get(models.Job,job['id']).status=='failed'
    assert db.query(models.Field).one().text_raw=='Original'
    assert db.query(models.Edit).one().edit_text=='Correction'


def test_concurrent_review_prevents_replacement(client,db,monkeypatch):
    setup_page(db,monkeypatch)
    job=queue(client).json()['job']
    db.get(models.Page,'b/p4').revision_no=1;db.commit()
    worker.work_once(db);db.expire_all()
    assert db.get(models.Job,job['id']).status=='failed'
    assert db.query(models.Field).one().text_raw=='Original'
    assert db.query(models.Edit).one().edit_text=='Correction'


def test_classification_rejects_invalid_type_reviewer_and_stale_revision(client,db):
    seed(db)
    payload={'pageType':'coded','revision':0,'reviewerId':1}
    for update,status in [({'pageType':'missing'},400),({'reviewerId':999},400),({'revision':99},409),({'pageType':'main'},400)]:
        assert client.put('/page-classification/b/p4',json={**payload,**update}).status_code==status
    db.expire_all()
    assert db.get(models.Page,'b/p4').category=='main'
    assert db.query(models.PageVersion).count()==0
    assert db.query(models.Job).count()==0


def test_transcription_requires_template_and_valid_model_details(client,db,monkeypatch):
    setup_page(db,monkeypatch)
    payload={'revision':0,'reviewerId':1,'model':'chosen-model','provider':'claude','effort':'low'}
    for update in ({'model':''},{'provider':'invalid'},{'effort':''}):
        assert client.post('/page-transcription/b/p4',json={**payload,**update}).status_code==400
    db.get(models.Page,'b/p4').category='other';db.commit()
    response=client.post('/page-transcription/b/p4',json=payload)
    assert response.status_code==400
    assert 'template' in response.json()['detail']
    assert db.query(models.Job).count()==0



def test_other_does_not_require_transcription_but_main_does(client, db):
    """Changing to Other removes the requirement; changing back to Main restores it."""
    seed(db)
    for revision, page_type, required in [(0, "other", False), (1, "main", True)]:
        response = client.put('/page-classification/b/p4', json={
            "pageType": page_type, "revision": revision, "reviewerId": 1,
        })
        assert response.status_code == 200
        assert response.json()["pageType"] == page_type
        assert response.json()["needsTranscription"] is required
        db.expire_all()
        page = db.get(models.Page, 'b/p4')
        assert page.category == page_type
        assert page.needs_transcription is required


def test_a_page_can_be_changed_to_any_type_of_its_collection_which_are_listed_by_label(client, db):
    seed(db)
    db.add(models.Collection(collection_id=2, name="Shipping manifests"))
    db.add(models.PageType(name="followup", label="Follow-up visit"))
    db.add(models.PageType(name="manifest", label="Manifest", collection_id=2))
    db.commit()
    assert client.get('/page-actions/b/p4').json()['pageTypes'] == [
        {"name": "coded", "label": "Coded page"}, {"name": "main", "label": "Main page"}, {"name": "notes", "label": "Notes page"},
        {"name": "other", "label": "Unknown"}, {"name": "followup", "label": "Follow-up visit"}]
    payload = {'revision': 0, 'reviewerId': 1}
    refused = client.put('/page-classification/b/p4', json={**payload, 'pageType': 'manifest'})  # another collection's type
    assert (refused.status_code, refused.json()['detail']) == (400, "No page type called manifest in this page's series.")
    assert client.put('/page-classification/b/p4', json={**payload, 'pageType': 'followup'}).json()['pageType'] == 'followup'
