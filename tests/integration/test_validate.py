"""Exercise US6 on the example main form and coded card, using the real reading format."""
import importlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from backend.pipeline.validate.run_validation import validate_survey

ROOT = Path(__file__).resolve().parent / 'validate'
TEMPLATES = Path(__file__).resolve().parents[2] / 'backend' / 'pipeline' / 'transcribe' / 'templates'


class TestUs6Integration:

    def setup_method(self):
        self.m = json.loads((ROOT / 'example_main.json').read_text(encoding='utf-8'))
        self.c = json.loads((ROOT / 'example_coded.json').read_text(encoding='utf-8'))

    def test_example_survey_has_no_flags(self):
        result = validate_survey(self.m, self.c, survey_id='test')
        assert not result['has_flags']
        assert result['validation_flags'] == []
        assert result['survey_id'] == 'test'

    def test_conflict_names_the_nested_field_and_changes_nothing(self):
        self.c['number_of_bedrooms'] = '4'
        original = deepcopy(self.m)
        result = validate_survey(self.m, self.c)
        assert self.m == original
        assert self.m['rooms']['number_of_separate_bedrooms'] == '3'
        assert any(('Page 1: rooms.number_of_separate_bedrooms' in i['fields'] for i in result['validation_flags']))

    def test_native_age_derivation(self):
        self.m['residents'][2]['age'] = '8'
        self.m['residents'][3]['age'] = '7'
        self.c.update({'number_5_to_10': '2', 'children_under_14': '2', 'number_over_10_male': '1', 'number_over_10_female': '1'})
        assert not validate_survey(self.m, self.c)['has_flags']
        self.c['children_under_14'] = '1'
        result = validate_survey(self.m, self.c)
        assert any((i['type'] == 'Page 1–3 conflict' and 'Page 1: residents[2].age' in i['fields'] for i in result['validation_flags']))

    def test_missing_native_location(self):
        del self.c['number_of_bedrooms']
        result = validate_survey(self.m, self.c)
        assert any((i['fields'].get('Page 3: number_of_bedrooms') == '<missing>' for i in result['validation_flags']))

    def test_blank_upstream_template_is_not_zero_known_residents(self):
        blank = json.loads((TEMPLATES / 'main.json').read_text(encoding='utf-8'))
        coded = json.loads((TEMPLATES / 'coded.json').read_text(encoding='utf-8'))
        assert not validate_survey(blank, coded)['has_flags']
        assert validate_survey(blank, self.c)['has_flags']

    def test_unrecognised_coded_card_is_not_silent_success(self):
        for coded in ({}, {'unknown_count': 4}, {'fields': self.c}, {'NUMBER OF DWELLING': '3'}):
            with pytest.raises(ValueError, match='not a coded card reading'):
                validate_survey(self.m, coded)

    def test_number_does_not_fallback_without_definition(self):
        del self.m['number_of_dwelling']
        result = validate_survey(self.m, self.c)
        assert any((i['fields'].get('Page 1: number_of_dwelling') == '<missing>' for i in result['validation_flags']))

    def test_unknown_fields_are_ignored(self):
        self.m['additional_handwritten_field'] = '[?]'
        result = validate_survey(self.m, self.c, survey_id='x')
        assert not result['has_flags']

    def test_other_children_list_not_guessed_count(self):
        self.m['other_children']['died'] = [{'raw': 'two children'}]
        result = validate_survey(self.m, self.c)
        assert any(('other_children' in w for w in result['validation_warnings']))
        assert not result['has_flags']

    def test_missing_page_fails_before_output(self):
        with pytest.raises(ValueError):
            validate_survey(self.m, None)

    def test_package_import(self):
        module = importlib.import_module('backend.pipeline.validate')
        assert not module.validate_survey(self.m, self.c)['has_flags']
