"""US6 after step_group, or rerun on an existing manifest without transcription."""
from __future__ import annotations
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
if __package__:
    from .run_validation import validate_survey, flags_only
else:
    from run_validation import validate_survey, flags_only


def _write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.us6-',dir=path.parent) as folder:
        pending=Path(folder)/path.name
        pending.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        pending.replace(path)


def step_validate(run):
    """Consume run.pages survey assignments and cached page transcript paths.

    Multiple main sheets are not silently merged: they require an agreed sheet
    consolidation contract. Blocked surveys are reported separately from flags.
    """
    run.review[:]=[item for item in run.review if item.get('step')!='validate']
    surveys={}
    loose=[]
    for page in run.pages:
        page.pop('validation',None)
        if page.get('label') not in ('main','coded','notes'):
            continue
        if page.get('survey') is None:
            loose.append(page)
        else:
            surveys.setdefault(page['survey'],[]).append(page)
    results=[]
    skipped=[]
    for page in loose:
        reason='US6 not run: page has no survey assignment; resolve grouping first'
        run.flag(page,'validate',reason)
        page['validation']={'status':'NotValidated','reason':reason}
        skipped.append({'survey_id':None,'files':[page.get('file')],'reason':reason})
    root=Path(run.out).resolve()
    for survey_id,pages in surveys.items():
        mains=[p for p in pages if p['label']=='main']
        cards=[p for p in pages if p['label']=='coded']
        reason=None
        if len(mains)!=1 or len(cards)!=1:
            reason=f'US6 not run: survey has {len(mains)} main sheets and {len(cards)} coded cards; exactly one of each is required by the current sheet adapter'
        def load(page):
            transcript=page.get('transcript')
            if not isinstance(transcript,str) or not transcript:
                raise ValueError(f"{page.get('file')}: no transcript path")
            path=(root/transcript).resolve()
            if not path.is_relative_to(root):
                raise ValueError(f"{page.get('file')}: transcript path is outside the run output")
            data=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data,dict):
                raise ValueError(f"{page.get('file')}: transcript must be a JSON object")
            return data
        if reason is None:
            try:
                main,coded=load(mains[0]),load(cards[0])
                notes=[{'file':p['file'],'data':load(p)} for p in pages if p['label']=='notes']
                result=validate_survey(main,coded,notes=notes,survey_id=survey_id)
            except (ValueError,OSError) as error:
                reason=f'US6 not run: {error}'
        if reason:
            skipped.append({'survey_id':survey_id,'files':[p.get('file') for p in pages],'reason':reason})
            for p in pages:
                p['validation']={'status':'NotValidated','reason':reason}
            run.flag(pages[0],'validate',reason)
            continue
        result['page_files']={'main':mains[0]['file'],'coded':cards[0]['file'],'notes':[n['file'] for n in notes]}
        results.append(result)
        affected={category for category,prefix in [('main','Page 1:'),('coded','Page 3:')] if any(any(k.startswith(prefix) for k in issue['fields']) for issue in result['validation_flags'])}
        for p in pages:
            p['validation']={'status':'ToBeReviewed' if p['label'] in affected else 'Validated','result':'validation/output_flagged.json','survey_id':survey_id}
        for issue in result['validation_flags']:
            involved=[]
            if any(k.startswith('Page 1:') for k in issue['fields']): involved+=mains
            if any(k.startswith('Page 3:') for k in issue['fields']): involved+=cards
            for p in involved:
                run.flag(p,'validate',f"survey {survey_id}: {issue['type']}: {issue['reason']}")
    summary={'status':'partial' if skipped else 'completed','validated_surveys':len(results),'skipped_surveys':len(skipped),'surveys_with_flags':sum(s['has_flags'] for s in results)}
    full={**summary,'surveys':results,'not_validated':skipped}
    compact={**summary,'surveys':[flags_only(s) for s in results],'not_validated':skipped}
    _write(root/'validation'/'output_flagged.json',full)
    _write(root/'validation'/'output_flags_only.json',compact)
    return summary


def validate_manifest(path):
    """Reuse existing group assignments; no image/model or paid LLM step."""
    path=Path(path).resolve()
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(manifest,dict) or not isinstance(manifest.get('pages'),list):
        raise ValueError('manifest must contain pages as a list')
    if any(not isinstance(p,dict) or not isinstance(p.get('file'),str) or (p.get('survey') is not None and not isinstance(p['survey'],str)) for p in manifest['pages']):
        raise ValueError('Manifest pages require string file names and string/null survey IDs')
    log=manifest.get('steps',[])
    if not isinstance(log,list) or any(not isinstance(e,dict) for e in log):
        raise ValueError('manifest.steps must be an array of step objects')
    review_path=path.parent/'review.json'
    review=json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else []
    if not isinstance(review,list) or any(not isinstance(r,dict) for r in review):
        raise ValueError('review.json must contain an array')
    run=SimpleNamespace(out=path.parent,pages=manifest['pages'],review=review)
    run.flag=lambda page,step,reason:run.review.append({'file':page['file'],'step':step,'reason':reason})
    start=time.perf_counter()
    summary=step_validate(run)
    log=manifest.get('steps',[])
    if not isinstance(log,list):
        raise ValueError('manifest.steps must be a list')
    log=[entry for entry in log if entry.get('step')!='validate']
    log.append({'step':'validate','seconds':round(time.perf_counter()-start,1),'pages':len(run.pages),'flagged':sum(r.get('step')=='validate' for r in run.review),**summary})
    manifest['steps']=log
    _write(review_path,run.review)
    _write(path,manifest)
    return summary


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path,help='Existing grouped output/manifest.json')
    args=parser.parse_args(argv)
    try:
        print(json.dumps(validate_manifest(args.manifest),ensure_ascii=False))
    except (ValueError,OSError) as error:
        parser.exit(2,f'US6 manifest error: {error}\n')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
