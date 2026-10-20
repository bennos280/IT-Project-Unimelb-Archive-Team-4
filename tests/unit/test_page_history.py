"""History reads snapshots, moves and reviews without changing a page."""
from backend.db import models
from backend.db.page_history import snapshot


def test_page_history_is_scoped_and_read_only(client, db):
    db.add(models.Bundle(bundle_id='b', source_pdf='b.pdf', collection_id=1)); db.flush()
    db.add(models.Reviewer(reviewer_id=1, name='Alex'))
    for identity in ('b/p1', 'b/p2'):
        db.add(models.Page(page_id=identity, bundle_id='b', category='main', import_path='scan.png'))
    db.flush()
    db.add(models.Field(page_id='b/p1', field_title='address', text_raw='Original')); db.flush()
    db.add(models.Edit(page_id='b/p1', field_title='address', edit_text='Corrected', reviewer_id=1)); db.flush()
    snapshot(db, 'b/p1', 1, 'change_type')
    snapshot(db, 'b/p2', 1, 'transcribe')
    db.add(models.PageMove(page_id='b/p1', from_survey='s1', to_survey='s2', reviewer_id=1, reason='Wrong survey'))
    db.commit()
    response = client.get('/page-history/b/p1')
    assert response.status_code == 200
    body = response.json()
    assert body['revision'] == 0
    assert len(body['events']) == 3
    assert {e['title'] for e in body['events']} == {'Page type changed', 'Moved to another survey', 'Field review saved'}
    version = next(e for e in body['events'] if e['snapshot'])
    assert version['reviewer'] == 'Alex'
    assert version['snapshot']['edits'][0]['edit_text'] == 'Corrected'
    assert db.get(models.Page, 'b/p1').revision_no == 0
    assert client.get('/page-history/missing').status_code == 404


def test_history_empty(client, db):
    db.add(models.Bundle(bundle_id='b', source_pdf='b.pdf', collection_id=1)); db.flush()
    db.add(models.Page(page_id='p', bundle_id='b', category='notes', import_path='scan.png')); db.commit()
    assert client.get('/page-history/p').json()['events'] == []
