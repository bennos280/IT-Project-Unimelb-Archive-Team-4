import json
import tempfile
import unittest
from pathlib import Path
if __package__:
    from .pipeline_step import validate_manifest
    from .run_validation import validate_survey
else:
    from pipeline_step import validate_manifest
    from run_validation import validate_survey
ROOT=Path(__file__).parent

class PipelineTests(unittest.TestCase):
    def make_run(self,tmp):
        root=Path(tmp);(root/'transcribe').mkdir()
        for kind in ('main','coded'):
            (root/'transcribe'/f'{kind}.json').write_bytes((ROOT/f'example_{kind}.json').read_bytes())
        pages=[{'file':kind+'.png','label':kind,'survey':'survey-24A','transcript':'transcribe/'+kind+'.json'} for kind in ('main','coded')]
        path=root/'manifest.json'
        path.write_text(json.dumps({'input':'original.pdf','pages':pages,'steps':[{'step':'group'}],'transcripts':{'preserve':True}}), encoding='utf-8')
        (root/'review.json').write_text(json.dumps([{'file':'main.png','step':'group','reason':'preserve grouping review'}]), encoding='utf-8')
        return path

    def test_group_manifest_uses_cached_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.make_run(tmp)
            result=validate_manifest(path)
            self.assertEqual(result['validated_surveys'],1)
            self.assertEqual(result['surveys_with_flags'],0)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['transcripts'],{'preserve':True})
            self.assertEqual(json.loads((path.parent/'review.json').read_text(encoding='utf-8'))[0]['step'],'group')

    def test_no_transcript_changes_and_idempotent_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.make_run(tmp)
            card=path.parent/'transcribe'/'coded.json'
            data=json.loads(card.read_text(encoding='utf-8'));data['number_of_dwelling']='2';card.write_text(json.dumps(data), encoding='utf-8')
            before=card.read_bytes()
            validate_manifest(path)
            first=json.loads((path.parent/'review.json').read_text(encoding='utf-8'))
            validate_manifest(path)
            self.assertEqual(first,json.loads((path.parent/'review.json').read_text(encoding='utf-8')))
            self.assertEqual(card.read_bytes(),before)
            self.assertTrue(any(r['step']=='validate' for r in first))

    def test_repeated_main_not_merged_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.make_run(tmp);doc=json.loads(path.read_text(encoding='utf-8'));doc['pages'].append(dict(doc['pages'][0],file='second.png'));path.write_text(json.dumps(doc), encoding='utf-8')
            result=validate_manifest(path)
            self.assertEqual(result['status'],'partial')
            self.assertEqual(result['skipped_surveys'],1)
            self.assertEqual(result['validated_surveys'],0)

    def test_missing_coded_reported_not_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.make_run(tmp);doc=json.loads(path.read_text(encoding='utf-8'));doc['pages']=doc['pages'][:1];path.write_text(json.dumps(doc), encoding='utf-8')
            self.assertEqual(validate_manifest(path)['skipped_surveys'],1)

    def test_missing_transcript_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.make_run(tmp);(path.parent/'transcribe'/'coded.json').unlink()
            self.assertEqual(validate_manifest(path)['skipped_surveys'],1)

    def test_unassigned_page_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.make_run(tmp);doc=json.loads(path.read_text(encoding='utf-8'));doc['pages'][0]['survey']=None;path.write_text(json.dumps(doc), encoding='utf-8')
            self.assertEqual(validate_manifest(path)['status'],'partial')

    def test_letter_dwelling_numbers(self):
        m=json.loads((ROOT/'example_main.json').read_text(encoding='utf-8'));c=json.loads((ROOT/'example_coded.json').read_text(encoding='utf-8'))
        m['number_of_dwelling']='024 a';c['number_of_dwelling']='24A'
        self.assertFalse(validate_survey(m,c)['has_flags'])
        c['number_of_dwelling']='24B'
        self.assertTrue(any('NUMBER OF DWELLING' in f['reason'] and f['type']=='Page 1–3 conflict' for f in validate_survey(m,c)['validation_flags']))

    def test_actual_coded_all_null_schema(self):
        m=json.loads((ROOT/'main_schema.json').read_text(encoding='utf-8'));c=json.loads((ROOT/'coded_schema.json').read_text(encoding='utf-8'))
        self.assertFalse(validate_survey(m,c)['has_flags'])

    def test_explicit_margin_codes_compare(self):
        m=json.loads((ROOT/'example_main.json').read_text(encoding='utf-8'));c=json.loads((ROOT/'example_coded.json').read_text(encoding='utf-8'))
        m['industry_of_head_code']='0802';c['industry_of_head']='802'
        self.assertFalse(validate_survey(m,c)['has_flags'])
        c['industry_of_head']='803'
        self.assertTrue(any('INDUSTRY OF HEAD CODE' in f['reason'] for f in validate_survey(m,c)['validation_flags']))

    def test_nonpersonal_metadata_not_resident(self):
        m=json.loads((ROOT/'example_main.json').read_text(encoding='utf-8'));c=json.loads((ROOT/'example_coded.json').read_text(encoding='utf-8'))
        m['residents'].append({'relationship':None,'age':None,'earning_status':None,'craft':'stray annotation'})
        self.assertFalse(validate_survey(m,c)['has_flags'])

if __name__=='__main__':unittest.main()
