"""Regression cases raised in the US6 pull-request review."""
import json
from pathlib import Path

import pytest

from backend.pipeline.validate.run_validation import validate_survey
from backend.pipeline.validate.validator import _relationship

ROOT = Path(__file__).resolve().parents[1] / 'integration' / 'validate'


def survey():
    return tuple(json.loads((ROOT / name).read_text(encoding='utf-8'))
                 for name in ('example_main.json', 'example_coded.json'))


@pytest.mark.parametrize('relationship', ['Head (F)', 'head (female)', 'H. (F)', 'H (f)', ' Head ( F ) '])
def test_female_head_is_identified_and_sex_is_explicit(relationship):
    main, coded = survey()
    main['residents'][0]['relationship'] = relationship
    main['residents'][0].pop('sex')
    coded.update(number_over_10_m='1', number_over_10_f='3')
    result = validate_survey(main, coded)
    assert result['validation_flags'] == []
    coded['age_of_head'] = '75'
    flags = validate_survey(main, coded)['validation_flags']
    assert any(f['type'] == 'Page 1–3 conflict' and f['reason'].startswith('Age of head:') for f in flags)


@pytest.mark.parametrize('text', ['headache', 'head boarder', 'head of son'])
def test_head_prefix_does_not_identify_unrelated_labels(text):
    assert _relationship(text)[0] != 'head'


@pytest.mark.parametrize('duration', ['15 years.', '15 year.', '15 yrs.', '15 y.'])
def test_period_after_year_unit_is_accepted(duration):
    main, coded = survey()
    main.update(probable_age=duration, length_of_residence=duration)
    coded.update(age_of_house='15', length_of_residence='15')
    assert validate_survey(main, coded)['validation_flags'] == []


@pytest.mark.parametrize('age', ['50-60 years.', 'over 50 years.', 'under 60 years.'])
def test_age_ranges_and_bounds_allow_period(age):
    main, coded = survey()
    main['probable_age'] = age
    assert validate_survey(main, coded)['validation_flags'] == []


def test_annotated_son_and_daughter_count_as_resident_children():
    main, coded = survey()
    main['residents'][2]['relationship'] = 'Son (M)'
    main['residents'][3]['relationship'] = 'Daughter (F)'
    assert validate_survey(main, coded)['validation_flags'] == []
    coded.update(children_of_h_or_wife_living='1', children_of_h_or_wife_total='1')
    assert any('resident sons/daughters exceed' in f['reason']
               for f in validate_survey(main, coded)['validation_flags'])
