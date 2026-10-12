import pytest
from pipeline.us6.validator import find_issues, make_flagged_output, make_flags_only_output, validate_document
"""Regression tests for the user's false-positive and missing-value examples."""
import json
from copy import deepcopy
from pathlib import Path

class TestUs6Validation:

    def setup_method(self):
        self.survey = json.loads((Path(__file__).resolve().parents[2] / 'pipeline' / 'us6' / 'sample_input.json').read_text(encoding='utf-8'))
        m, c = (self.survey['pages']['main']['fields'], self.survey['pages']['coded']['fields'])
        m['PERSONNEL'][0]['PERSONAL']['SEX'] = 'M'
        c.update({'NUMBER OF DWELLING': '1', 'TOTAL NO. RESIDENT MEMBERS': '4', 'NUMBER OF BEDROOMS': '3', 'NO. OF ADULT M. BREADWINNERS': '1', 'NO. OF ADULT F. BREADWINNERS': '1', 'NO. OF JUVENILE BREADWINNERS (UNDER 21)': '0', 'ROOMS SHARED': '0', 'CHILDREN OTHER THAN THOSE AT HOME': '0'})
        c['CHILDREN OF H. OR WIFE'] = {'LIVING': '2', 'DEAD': '0', 'TOTAL': '2'}
        self.m, self.c = (m, c)

    def issues(self):
        return find_issues(self.survey)

    def test_consistent_sample_no_flags(self):
        assert self.issues() == []

    def test_isolated_unreadable_ignored(self):
        self.m['SIGNATURE OF INVESTIGATOR'] = '[?]'
        self.c['MUNICIPALITY'] = '[?]'
        assert self.issues() == []

    def test_no_codebook_mapping_guessed(self):
        self.m['MUNICIPALITY'] = 'Essendon'
        self.c['MUNICIPALITY'] = '2'
        assert self.issues() == []

    def test_children_from_ages_8_and_7(self):
        people = self.m['PERSONNEL']
        people[0]['PERSONAL']['AGE'] = '31'
        people[1]['PERSONAL']['AGE'] = '30'
        people[2]['PERSONAL']['AGE'] = '8'
        people[3]['PERSONAL']['AGE'] = '7'
        self.c.update({'AGE OF HEAD': '31', 'NUMBER 5-10': '2', 'CHILDREN UNDER 14': '2'})
        self.c['NUMBER OVER 10'] = {'M': '1', 'F': '1'}
        assert self.issues() == []
        self.c['CHILDREN UNDER 14'] = '1'
        assert any((i['type'] == 'Page 1–3 conflict' and i['reason'].startswith('CHILDREN UNDER 14:') for i in self.issues()))

    def test_age_boundaries(self):
        for age, under5, band, under14 in [(4, 1, 0, 1), (5, 0, 1, 1), (10, 0, 1, 1), (11, 0, 0, 1), (13, 0, 0, 1), (14, 0, 0, 0)]:
            self.m['PERSONNEL'][2]['PERSONAL']['AGE'] = str(age)
            self.c.update({'NUMBER UNDER 5': str(under5), 'NUMBER 5-10': str(band), 'CHILDREN UNDER 14': str(under14)})
            self.c['NUMBER OVER 10']['M'] = str(2 - under5 - band)
            assert self.issues() == []

    def test_corresponding_missing_markers(self):
        for missing in [None, '', ' ', '/', '[?]']:
            self.c['NUMBER OF BEDROOMS'] = missing
            assert any((i['type'] == 'Page 1–3 comparison incomplete' and i['reason'].startswith('NUMBER OF BEDROOMS:') for i in self.issues()))

    def test_absent_field_has_location(self):
        del self.c['NUMBER OF BEDROOMS']
        compact = make_flags_only_output(self.survey)
        assert any((i['fields'].get('Page 3: NUMBER OF BEDROOMS') == '<missing>' for i in compact['flags']))
        full = make_flagged_output(self.survey)
        assert 'NUMBER OF BEDROOMS' not in full['pages']['coded']['fields']
        assert full['pages']['coded']['fields']['NUMBER OF BEDROOMS_review_status'] == 'ToBeReviewed'

    def test_both_corresponding_blank_no_crosspage_issue(self):
        self.m['NUMBER'] = None
        self.c['NUMBER OF DWELLING'] = '/'
        assert self.issues() == []

    def test_unknown_age_not_silently_zero(self):
        self.m['PERSONNEL'][2]['PERSONAL']['AGE'] = '[?]'
        assert any(('CHILDREN UNDER 14:' in i['reason'] and 'incomplete' in i['type'] for i in self.issues()))

    def test_unknown_sex_not_guessed_from_head(self):
        del self.m['PERSONNEL'][0]['PERSONAL']['SEX']
        assert not any('Residents over 10' in i['reason'] for i in self.issues())

    def test_empty_template_columns_not_residents(self):
        self.m['PERSONNEL'].append({'PERSONAL': {'AGE': None, 'RELATIONSHIP': '/'}})
        assert self.issues() == []

    def test_page3_age_sum_reason(self):
        self.c['TOTAL NO. RESIDENT MEMBERS'] = '5'
        assert any((i['type'] == 'Page 3 internal conflict' and 'age bands' in i['reason'] for i in self.issues()))

    def test_children_arithmetic(self):
        self.c['CHILDREN OF H. OR WIFE']['TOTAL'] = '3'
        assert any((i['type'] == 'Page 3 internal conflict' and 'living plus dead' in i['reason'] for i in self.issues()))

    def test_combined_rooms(self):
        self.c['TOTAL NUMBER OF ROOMS'] = '4'
        assert any(('Separate bedrooms plus living rooms' in i['reason'] for i in self.issues()))

    def test_page1_conflict(self):
        self.m['STATE IF USED AS BEDROOMS'] = 'Yes'
        self.m['NO. OF LIVING ROOMS'] = '0'
        assert any((i['type'] == 'Page 1 internal conflict' for i in self.issues()))

    def test_equivalent_count_text(self):
        self.m['ROOMS NOT IN DAILY USE'] = 'None'
        self.c['ROOMS NOT IN DAILY USE'] = 0
        self.m['NUMBER'] = '01'
        assert self.issues() == []

    def test_probable_age_range(self):
        self.c['AGE OF HOUSE'] = '61'
        assert any(('probable-age interval' in i['reason'] for i in self.issues()))

    def test_children_elsewhere_bound(self):
        self.c['CHILDREN OTHER THAN THOSE AT HOME'] = '1'
        assert any(('Resident children plus children elsewhere' in i['reason'] for i in self.issues()))

    def test_legacy_other_children_is_not_used(self):
        self.m['PERSONNEL'][0]['OTHER CHILDREN']['DIED'] = '1'
        assert not any(("Head's other children" in i['reason'] for i in self.issues()))

    def test_negative_only_flagged_in_relationship(self):
        self.c['REMOVAL'] = '-1'
        assert self.issues() == []
        self.c['NUMBER OF BEDROOMS'] = '-1'
        assert any('NUMBER OF BEDROOMS' in i['reason'] for i in self.issues())

    def test_preserves_input_and_deterministic_batch(self):
        original = deepcopy(self.survey)
        first = validate_document({'surveys': [self.survey, self.survey]})
        assert first == validate_document({'surveys': [self.survey, self.survey]})
        assert self.survey == original
        assert first[1]['surveys'][0]['flags'] == []

    def test_missing_page_is_input_error(self):
        del self.survey['pages']['coded']
        with pytest.raises(ValueError):
            self.issues()
