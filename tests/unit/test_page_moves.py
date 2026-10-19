"""Moving a page preserves its content and reviews, with same-bundle and stale-write guards."""
from backend.db import models


def seed(db):
    for row in [models.Bundle(bundle_id='b', source_pdf='b.pdf', collection_id=1), models.Bundle(bundle_id='x', source_pdf='x.pdf', collection_id=1),
                models.Survey(survey_id='s1',bundle_id='b'),models.Survey(survey_id='s2',bundle_id='b'),models.Survey(survey_id='outside',bundle_id='x'),
                models.Reviewer(reviewer_id=1,name='Alex'),
                models.Page(page_id='b/p4',bundle_id='b',survey_id='s1',category='main',import_path='image.png'),
                models.Page(page_id='b/p5',bundle_id='b',survey_id='s2',category='main',import_path='second.png'),
                models.Field(page_id='b/p4',field_title='address',text_raw='Original'),
                models.Edit(page_id='b/p4',field_title='address',edit_text='Correction')]:
        db.add(row); db.flush()
    db.commit()


def body(**changes):
    return dict(surveyId='s2',sourceSurveyId='s1',reviewerId=1,revision=0,reason='Wrong household',**changes)


def test_move_preserves_page_and_reviews_and_allows_two_main_pages(client,db):
    seed(db)
    context=client.get('/page-actions/b/p4').json()
    assert [s['id'] for s in context['surveys']]==['s1','s2']
    assert client.put('/page-moves/b/p4',json=body()).status_code==200
    db.expire_all()
    p=db.get(models.Page,'b/p4')
    assert (p.survey_id,p.import_path,p.category,p.revision_no)==('s2','image.png','main',1)
    assert db.query(models.Field).filter_by(page_id=p.page_id).one().text_raw=='Original'
    assert db.query(models.Edit).filter_by(page_id=p.page_id).one().edit_text=='Correction'
    assert db.query(models.Page).filter_by(survey_id='s2',category='main').count()==2
    audit=db.query(models.PageMove).one()
    assert (audit.from_survey,audit.to_survey,audit.reviewer_id,audit.reason)==('s1','s2',1,'Wrong household')
    assert len(client.get('/survey/s2').json()['pages'])==2
    assert client.put('/page-moves/b/p4',json={**body(),'surveyId':'s1'}).status_code==409


def test_move_rejects_cross_bundle_unknown_reviewer_and_same_survey(client,db):
    seed(db)
    for changes in ({'surveyId':'outside'},{'reviewerId':999},{'surveyId':'s1'}):
        assert client.put('/page-moves/b/p4',json={**body(),**changes}).status_code==400
    assert db.query(models.PageMove).count()==0


def test_move_rejects_changed_page_and_active_transcription(client,db):
    seed(db)
    assert client.put('/page-moves/b/p4',json={**body(),'revision':5}).status_code==409
    db.add(models.Job(kind='page',page_id='b/p4',page_type='notes',reviewer_id=1));db.commit()
    assert client.put('/page-moves/b/p4',json=body()).status_code==409
