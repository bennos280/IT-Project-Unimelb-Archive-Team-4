import pytest
from backend.pipeline.validate.run_validation import validate_survey
from backend.pipeline.validate.validator import find_issues
"""Regression tests for the user's false-positive and missing-value examples."""
import json
from copy import deepcopy
from pathlib import Path

class TestUs6Validation:

    def setup_method(self):
        survey = json.loads((Path(__file__).resolve().parents[1] / 'integration' / 'validate' / 'sample_input.json').read_text(encoding='utf-8'))
        m, c = (survey['main'], survey['coded'])
        m['residents'][0]['sex'] = 'M'
        c.update({'number_of_dwelling': '1', 'total_number_resident_members': '4', 'number_of_bedrooms': '3', 'number_of_adult_male_breadwinners': '1', 'number_of_adult_female_breadwinners': '1', 'number_of_juvenile_breadwinners_under_21': '0', 'rooms_shared': '0', 'children_other_than_those_at_home': '0'})
        c.update({'children_of_head_or_wife_living': '2', 'children_of_head_or_wife_dead': '0', 'children_of_head_or_wife_total': '2'})
        self.m, self.c = (m, c)

    def issues(self):
        return find_issues({'main': self.m, 'coded': self.c})

    def test_consistent_sample_no_flags(self):
        assert self.issues() == []

    def test_isolated_unreadable_ignored(self):
        self.m['signature_of_investigator'] = '[?]'
        self.c['municipality'] = '[?]'
        assert self.issues() == []

    def test_no_codebook_mapping_guessed(self):
        self.m['municipality'] = 'Essendon'
        self.c['municipality'] = '2'
        assert self.issues() == []

    def test_children_from_ages_8_and_7(self):
        people = self.m['residents']
        people[0]['age'] = '31'
        people[1]['age'] = '30'
        people[2]['age'] = '8'
        people[3]['age'] = '7'
        self.c.update({'age_of_head': '31', 'number_5_to_10': '2', 'children_under_14': '2'})
        self.c['number_over_10_male'] = '1'
        self.c['number_over_10_female'] = '1'
        assert self.issues() == []
        self.c['children_under_14'] = '1'
        assert any((i['type'] == 'Page 1–3 conflict' and i['reason'].startswith('CHILDREN UNDER 14:') for i in self.issues()))

    def test_age_boundaries(self):
        for age, under5, band, under14 in [(4, 1, 0, 1), (5, 0, 1, 1), (10, 0, 1, 1), (11, 0, 0, 1), (13, 0, 0, 1), (14, 0, 0, 0)]:
            self.m['residents'][2]['age'] = str(age)
            self.c.update({'number_under_5': str(under5), 'number_5_to_10': str(band), 'children_under_14': str(under14)})
            self.c['number_over_10_male'] = str(2 - under5 - band)
            assert self.issues() == []

    def test_corresponding_missing_markers(self):
        for missing in [None, '', ' ', '/', '[?]']:
            self.c['number_of_bedrooms'] = missing
            assert any((i['type'] == 'Page 1–3 comparison incomplete' and i['reason'].startswith('NUMBER OF BEDROOMS:') for i in self.issues()))

    def test_absent_field_has_location(self):
        del self.c['number_of_bedrooms']
        result = validate_survey(self.m, self.c, survey_id='sample')
        assert any((i['fields'].get('Page 3: number_of_bedrooms') == '<missing>' for i in result['validation_flags']))

    def test_both_corresponding_blank_no_crosspage_issue(self):
        self.m['number_of_dwelling'] = None
        self.c['number_of_dwelling'] = '/'
        assert self.issues() == []

    def test_unknown_age_not_silently_zero(self):
        self.m['residents'][2]['age'] = '[?]'
        assert any(('CHILDREN UNDER 14:' in i['reason'] and 'incomplete' in i['type'] for i in self.issues()))

    def test_unknown_sex_not_guessed_from_head(self):
        del self.m['residents'][0]['sex']
        assert not any('Residents over 10' in i['reason'] for i in self.issues())

    def test_empty_template_columns_not_residents(self):
        self.m['residents'].append({'age': None, 'relationship': '/'})
        assert self.issues() == []

    def test_page3_age_sum_reason(self):
        self.c['total_number_resident_members'] = '5'
        assert any((i['type'] == 'Page 3 internal conflict' and 'age bands' in i['reason'] for i in self.issues()))

    def test_children_arithmetic(self):
        self.c['children_of_head_or_wife_total'] = '3'
        assert any((i['type'] == 'Page 3 internal conflict' and 'living plus dead' in i['reason'] for i in self.issues()))

    def test_combined_rooms(self):
        self.c['total_number_of_rooms'] = '4'
        assert any(('Separate bedrooms plus living rooms' in i['reason'] for i in self.issues()))

    def test_page1_conflict(self):
        self.m['rooms']['state_if_used_as_bedrooms'] = 'Yes'
        self.m['rooms']['number_of_living_rooms'] = '0'
        assert any((i['type'] == 'Page 1 internal conflict' for i in self.issues()))

    def test_equivalent_count_text(self):
        self.m['rooms']['rooms_not_in_daily_use'] = 'None'
        self.c['rooms_not_in_daily_use'] = 0
        self.m['number_of_dwelling'] = '01'
        assert self.issues() == []

    def test_probable_age_range(self):
        self.c['age_of_house'] = '61'
        assert any(('probable-age interval' in i['reason'] for i in self.issues()))

    def test_children_elsewhere_bound(self):
        self.c['children_other_than_those_at_home'] = '1'
        assert any(('Resident children plus children elsewhere' in i['reason'] for i in self.issues()))

    def test_legacy_other_children_is_not_used(self):
        self.m['residents'][0]['other_children'] = {'died': '1'}
        self.m['other_children']['died'] = ['1']
        assert not any(("Head's other children" in i['reason'] for i in self.issues()))

    def test_negative_only_flagged_in_relationship(self):
        self.c['removal'] = '-1'
        assert self.issues() == []
        self.c['number_of_bedrooms'] = '-1'
        assert any('NUMBER OF BEDROOMS' in i['reason'] for i in self.issues())

    def test_preserves_input_and_deterministic_batch(self):
        original = deepcopy((self.m, self.c))
        first = validate_survey(self.m, self.c, survey_id='sample')
        assert first == validate_survey(self.m, self.c, survey_id='sample')
        assert self.issues() == self.issues() == []
        assert (self.m, self.c) == original

    def test_missing_page_is_input_error(self):
        with pytest.raises(ValueError):
            find_issues({'main': self.m})
