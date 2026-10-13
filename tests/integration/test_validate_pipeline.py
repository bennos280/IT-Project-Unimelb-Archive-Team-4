import pytest
from backend.pipeline.validate.pipeline_step import validate_manifest
from backend.pipeline.validate.run_validation import validate_survey
import json
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent / 'validate'
TEMPLATES = Path(__file__).resolve().parents[2] / 'backend' / 'pipeline' / 'transcribe' / 'templates'

class TestUs6Pipeline:

    def make_run(self, tmp):
        root = Path(tmp)
        (root / 'transcribe').mkdir()
        for kind in ('main', 'coded'):
            (root / 'transcribe' / f'{kind}.json').write_bytes((ROOT / f'example_{kind}.json').read_bytes())
        pages = [{'file': kind + '.png', 'label': kind, 'survey': 'survey-24A', 'transcript': 'transcribe/' + kind + '.json'} for kind in ('main', 'coded')]
        path = root / 'manifest.json'
        path.write_text(json.dumps({'input': 'original.pdf', 'pages': pages, 'steps': [{'step': 'group'}], 'transcripts': {'preserve': True}}), encoding='utf-8')
        (root / 'review.json').write_text(json.dumps([{'file': 'main.png', 'step': 'group', 'reason': 'preserve grouping review'}]), encoding='utf-8')
        return path

    def test_group_manifest_uses_cached_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp)
            result = validate_manifest(path)
            assert result['validated_surveys'] == 1
            assert result['surveys_with_flags'] == 0
            assert json.loads(path.read_text(encoding='utf-8'))['transcripts'] == {'preserve': True}
            assert json.loads((path.parent / 'review.json').read_text(encoding='utf-8'))[0]['step'] == 'group'

    def test_no_transcript_changes_and_idempotent_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp)
            card = path.parent / 'transcribe' / 'coded.json'
            data = json.loads(card.read_text(encoding='utf-8'))
            data['number_of_dwelling'] = '2'
            card.write_text(json.dumps(data), encoding='utf-8')
            before = card.read_bytes()
            validate_manifest(path)
            first = json.loads((path.parent / 'review.json').read_text(encoding='utf-8'))
            validate_manifest(path)
            assert first == json.loads((path.parent / 'review.json').read_text(encoding='utf-8'))
            assert card.read_bytes() == before
            assert any((r['step'] == 'validate' for r in first))

    def test_repeated_main_not_merged_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp)
            doc = json.loads(path.read_text(encoding='utf-8'))
            doc['pages'].append(dict(doc['pages'][0], file='second.png'))
            path.write_text(json.dumps(doc), encoding='utf-8')
            result = validate_manifest(path)
            assert result['status'] == 'partial'
            assert result['skipped_surveys'] == 1
            assert result['validated_surveys'] == 0

    def test_missing_coded_reported_not_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp)
            doc = json.loads(path.read_text(encoding='utf-8'))
            doc['pages'] = doc['pages'][:1]
            path.write_text(json.dumps(doc), encoding='utf-8')
            assert validate_manifest(path)['skipped_surveys'] == 1

    def test_missing_transcript_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp)
            (path.parent / 'transcribe' / 'coded.json').unlink()
            assert validate_manifest(path)['skipped_surveys'] == 1

    def test_unassigned_page_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp)
            doc = json.loads(path.read_text(encoding='utf-8'))
            doc['pages'][0]['survey'] = None
            path.write_text(json.dumps(doc), encoding='utf-8')
            assert validate_manifest(path)['status'] == 'partial'

    def test_letter_dwelling_numbers(self):
        m = json.loads((ROOT / 'example_main.json').read_text(encoding='utf-8'))
        c = json.loads((ROOT / 'example_coded.json').read_text(encoding='utf-8'))
        m['number_of_dwelling'] = '024 a'
        c['number_of_dwelling'] = '24A'
        assert not validate_survey(m, c)['has_flags']
        c['number_of_dwelling'] = '24B'
        assert any(('NUMBER OF DWELLING' in f['reason'] and f['type'] == 'Page 1–3 conflict' for f in validate_survey(m, c)['validation_flags']))

    def test_actual_coded_all_null_schema(self):
        m = json.loads((TEMPLATES / 'main.json').read_text(encoding='utf-8'))
        c = json.loads((TEMPLATES / 'coded.json').read_text(encoding='utf-8'))
        assert not validate_survey(m, c)['has_flags']

    def test_explicit_margin_codes_compare(self):
        m = json.loads((ROOT / 'example_main.json').read_text(encoding='utf-8'))
        c = json.loads((ROOT / 'example_coded.json').read_text(encoding='utf-8'))
        m['industry_of_head_code'] = '0802'
        c['industry_of_head'] = '802'
        assert not validate_survey(m, c)['has_flags']
        c['industry_of_head'] = '803'
        assert any(('INDUSTRY OF HEAD CODE' in f['reason'] for f in validate_survey(m, c)['validation_flags']))

    def test_nonpersonal_metadata_not_resident(self):
        m = json.loads((ROOT / 'example_main.json').read_text(encoding='utf-8'))
        c = json.loads((ROOT / 'example_coded.json').read_text(encoding='utf-8'))
        m['residents'].append({'relationship': None, 'age': None, 'earning_status': None, 'craft': 'stray annotation'})
        assert not validate_survey(m, c)['has_flags']
