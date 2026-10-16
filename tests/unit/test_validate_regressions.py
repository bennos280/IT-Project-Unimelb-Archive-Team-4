"""Regression cases raised in the US6 pull-request review."""
import json
from pathlib import Path

import pytest

from backend.pipeline.validate.run_validation import validate_survey
from backend.pipeline.validate.validator import CHECKS, CONVENTIONS, _relationship, _sleepouts, load_checks, load_conventions

ROOT = Path(__file__).resolve().parents[1] / 'integration' / 'validate'


def survey():
    return tuple(json.loads((ROOT / name).read_text(encoding='utf-8'))
                 for name in ('example_main.json', 'example_coded.json'))


@pytest.mark.parametrize('relationship', ['Head (F)', 'head (female)', 'H. (F)', 'H (f)', ' Head ( F ) '])
def test_female_head_is_identified_and_sex_is_explicit(relationship):
    main, coded = survey()
    main['residents'][0]['relationship'] = relationship
    main['residents'][0].pop('sex')
    coded.update(number_over_10_male='1', number_over_10_female='3')
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
    coded.update(children_of_head_or_wife_living='1', children_of_head_or_wife_total='1')
    assert any('resident sons/daughters exceed' in f['reason']
               for f in validate_survey(main, coded)['validation_flags'])


ALL = dict.fromkeys(CONVENTIONS, True)


def flagged(main, coded, start, **switches):
    """Whether a flag's reason starts with start, with every convention accepted except those switched off."""
    flags = validate_survey(main, coded, conventions={**ALL, **switches})['validation_flags']
    return any(f['reason'].startswith(start) for f in flags)


def clean(main, coded, **switches):
    return validate_survey(main, coded, conventions={**ALL, **switches})['validation_flags'] == []


def test_conventions_file(tmp_path):
    assert set(load_conventions()) == set(CONVENTIONS)
    for bad in ({**ALL, 'kitchen_not_a_living_room': 'no'}, {k: v for k, v in ALL.items() if k != 'part_years_dropped'},
                {**ALL, 'kitchn_not_a_living_room': True}):
        (tmp_path / 'conventions.json').write_text(json.dumps(bad), encoding='utf-8')
        with pytest.raises(ValueError):
            load_conventions(tmp_path / 'conventions.json')


def test_checks_file(tmp_path):
    assert set(load_checks()) == set(CHECKS)
    every = dict.fromkeys(CHECKS, True)
    for bad in ({**every, 'bedrooms': 'yes'}, {k: v for k, v in every.items() if k != 'bedrooms'}, {**every, 'bedroomz': True}):
        (tmp_path / 'checks.json').write_text(json.dumps(bad), encoding='utf-8')
        with pytest.raises(ValueError):
            load_checks(tmp_path / 'checks.json')


def test_switched_off_check_gives_no_flags():
    main, coded = survey()
    coded['number_of_bedrooms'] = '5'
    raised = lambda **off: {f['check'] for f in validate_survey(main, coded, checks={**dict.fromkeys(CHECKS, True), **off})['validation_flags']}
    assert 'bedrooms' in raised()
    assert 'bedrooms' not in raised(bedrooms=False)


@pytest.mark.parametrize('text,relationship', [('Son.', ('son', None)), ('Head (F).', ('head', 'F')), ('H. (F.)', ('head', 'F')),
                                               ('Head (R.S.)', ('head', None)), ('daughter.', ('daughter', None))])
def test_relationship_with_full_stops(text, relationship):
    assert _relationship(text) == relationship


@pytest.mark.parametrize('text,count', [('B 1', 1), ('B V O ✓✓', 2), ('B yes. V O', 1), ('V', 1), ('none.', 0), ('B Y O', None), ('B V 9', None)])
def test_sleepout_marks(text, count):
    assert _sleepouts(text) == count


@pytest.mark.parametrize('sex,ok', [('1', True), ('0', False)])
def test_another_resident_may_stand_in_as_head(sex, ok):
    main, coded = survey()
    coded.update(age_of_head='70', sex_of_head=sex)
    assert flagged(main, coded, 'Age of head:') != ok
    assert flagged(main, coded, 'Age of head:', another_resident_as_head=False)


def test_sleepout_may_be_counted_as_a_bedroom():
    main, coded = survey()
    main['rooms']['number_of_sleepouts'] = 'V yes.'
    coded.update(number_of_bedrooms='4', number_of_sleepouts='0', total_number_of_rooms='6')
    assert clean(main, coded)
    assert flagged(main, coded, 'NUMBER OF BEDROOMS:', sleepout_counted_as_bedroom=False)
    coded['number_of_bedrooms'] = '3'
    assert flagged(main, coded, 'Sleepouts:') and not flagged(main, coded, 'NUMBER OF BEDROOMS:')
    coded['number_of_bedrooms'] = '5'
    assert flagged(main, coded, 'NUMBER OF BEDROOMS:')


@pytest.mark.parametrize('code,total,ok', [('2', '5', True), ('1', '5', True), ('1', '7', False), ('0', '5', False), ('3', '5', False)])
def test_living_rooms_may_leave_out_the_kitchen(code, total, ok):
    main, coded = survey()
    coded.update(number_of_living_rooms=code, total_number_of_rooms=total)
    assert flagged(main, coded, 'NUMBER OF LIVING ROOMS:') != ok
    assert flagged(main, coded, 'NUMBER OF LIVING ROOMS:', kitchen_not_a_living_room=False) != (code == '2')


@pytest.mark.parametrize('cell,text', [('earning_status', 'M.'), ('industry', 'A.I.F.'), ('industry', 'R.A.A.F'), ('craft', 'in Army.'), ('industry', 'In camp')])
def test_residents_serving_in_the_forces_may_be_left_out(cell, text):
    main, coded = survey()
    main['residents'][2][cell] = text
    coded.update(total_number_resident_members='3', number_over_10_male='1', children_other_than_those_at_home='1')
    starts = ('Resident total:', 'Residents over 10', 'Resident children plus children elsewhere')
    assert clean(main, coded)
    assert all(flagged(main, coded, start, serving_residents_left_out=False) for start in starts)
    main['residents'][2][cell] = 'Clerk'
    assert all(flagged(main, coded, start) for start in starts)


@pytest.mark.parametrize('band,female,ok', [('1', '1', True), ('0', '2', True), ('0', '1', False)])
def test_ten_year_old_may_be_counted_over_10(band, female, ok):
    main, coded = survey()
    main['residents'][3]['age'] = '10'
    coded.update(number_5_to_10=band, number_over_10_female=female, children_under_14='1',
                 total_number_resident_members=str(2 + int(band) + int(female)))
    starts = ('NUMBER 5-10:', 'Residents over 10', 'Resident total:')
    assert any(flagged(main, coded, start) for start in starts) != ok
    assert any(flagged(main, coded, start, ten_year_olds_over_10=False) for start in starts) != (band == '1')


@pytest.mark.parametrize('code,ok', [('04', True), ('05', True), ('03', False), ('06', False)])
def test_part_years_of_residence_may_be_dropped_or_rounded_up(code, ok):
    main, coded = survey()
    main['length_of_residence'] = '4½ yrs.'
    coded['length_of_residence'] = code
    assert flagged(main, coded, 'Length of residence:') != ok
    assert flagged(main, coded, 'Length of residence:', part_years_dropped=False)
