import pytest
from backend.pipeline.validate.run_validation import validate_survey, validate_document, flags_only
from backend.pipeline.validate.input_adapter import CODED_FIELDS, normalize_survey
"""Exercise the supplied main schema, native output paths, and both CLI modes."""
import json
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
ROOT = Path(__file__).resolve().parent / 'validate'
CODE = Path(__file__).resolve().parents[2] / 'backend' / 'pipeline' / 'validate'

class TestUs6Integration:

    def setup_method(self):
        self.m = json.loads((ROOT / 'example_main.json').read_text(encoding='utf-8'))
        self.c = json.loads((ROOT / 'example_coded.json').read_text(encoding='utf-8'))

    def test_real_main_schema_adapter(self):
        result = validate_survey(self.m, self.c, survey_id='test')
        assert not result['has_flags']
        assert result['validation_flags'] == []
        assert result['main']['number'] == '99'

    def test_native_nested_statuses_and_preserved_values(self):
        self.c['number_of_bedrooms'] = '4'
        original = deepcopy(self.m)
        result = validate_survey(self.m, self.c)
        assert self.m == original
        assert result['main']['rooms']['number_of_separate_bedrooms'] == '3'
        assert result['main']['rooms']['number_of_separate_bedrooms_review_status'] == 'ToBeReviewed'
        assert any(('Page 1: rooms.number_of_separate_bedrooms' in i['fields'] for i in result['validation_flags']))

    def test_native_age_derivation(self):
        self.m['residents'][2]['age'] = '8'
        self.m['residents'][3]['age'] = '7'
        self.c.update({'number_5_to_10': '2', 'children_under_14': '2', 'number_over_10_m': '1', 'number_over_10_f': '1'})
        assert not validate_survey(self.m, self.c)['has_flags']
        self.c['children_under_14'] = '1'
        result = validate_survey(self.m, self.c)
        assert any((i['type'] == 'Page 1–3 conflict' and 'Page 1: residents[2].age' in i['fields'] for i in result['validation_flags']))
        assert result['main']['residents'][2]['age_review_status'] == 'ToBeReviewed'

    def test_missing_native_location(self):
        del self.c['number_of_bedrooms']
        result = validate_survey(self.m, self.c)
        assert any((i['fields'].get('Page 3: number_of_bedrooms') == '<missing>' for i in result['validation_flags']))

    def test_blank_upstream_template_is_not_zero_known_residents(self):
        blank = json.loads((ROOT / 'main_schema.json').read_text(encoding='utf-8'))
        coded = {}
        for candidates in CODED_FIELDS.values():
            target = coded
            for p in candidates[0][:-1]:
                target = target.setdefault(p, {})
            target[candidates[0][-1]] = None
        assert not validate_survey(blank, coded)['has_flags']
        assert validate_survey(blank, self.c)['has_flags']

    def test_unrecognised_coded_schema_is_not_silent_success(self):
        with pytest.raises(ValueError):
            validate_survey(self.m, {'unknown_count': 4})

    def test_conflicting_coded_aliases_are_rejected(self):
        self.c['rooms'] = {'number_of_bedrooms': '8'}
        with pytest.raises(ValueError):
            validate_survey(self.m, self.c)

    def test_number_does_not_fallback_without_definition(self):
        del self.m['number_of_dwelling']
        result = validate_survey(self.m, self.c)
        assert any((i['fields'].get('Page 1: number_of_dwelling') == '<missing>' for i in result['validation_flags']))

    def test_notes_and_unknown_fields_preserved(self):
        self.m['additional_handwritten_field'] = '[?]'
        result = validate_survey(self.m, self.c, notes={'body': '[?]'}, survey_id='x')
        assert not result['has_flags']
        assert result['notes'] == {'body': '[?]'}
        assert result['main']['additional_handwritten_field'] == '[?]'

    def test_other_children_list_not_guessed_count(self):
        self.m['other_children']['died'] = [{'raw': 'two children'}]
        result = validate_survey(self.m, self.c)
        assert any(('other_children' in w for w in result['validation_warnings']))
        assert not result['has_flags']

    def test_cli_two_page_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(CODE / 'run_validation.py'), '--main', str(ROOT / 'example_main.json'), '--coded', str(ROOT / 'example_coded.json'), '--survey-id', 'cli', '--output-dir', tmp], capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            assert json.loads((Path(tmp) / 'output_flags_only.json').read_text(encoding='utf-8')) == {'survey_id': 'cli', 'flags': []}

    def test_cli_grouped_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(CODE / 'run_validation.py'), str(ROOT / 'example_survey.json'), '--output-dir', tmp], capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            full = json.loads((Path(tmp) / 'output_flagged.json').read_text(encoding='utf-8'))
            assert not full['has_flags']
            assert full['notes']['text'] == 'Preserve these notes.'

    def test_batch_separates_surveys(self):
        second = deepcopy(self.c)
        second['number_of_dwelling'] = '2'
        result = validate_document({'surveys': [{'survey_id': 'a', 'main': self.m, 'coded': self.c}, {'survey_id': 'b', 'main': self.m, 'coded': second}]})
        assert not result['surveys'][0]['has_flags']
        assert result['surveys'][1]['has_flags']
        assert len(flags_only(result)['surveys']) == 2

    def test_missing_page_fails_before_output(self):
        with pytest.raises(ValueError):
            validate_document({'main': self.m})

    def test_package_import(self):
        import importlib
        module = importlib.import_module('backend.pipeline.validate')
        assert not module.validate_survey(self.m, self.c)['has_flags']
