"""Codebook boundaries, special codes, and review false-positive regressions."""
import json
from pathlib import Path

import pytest

from backend.pipeline.validate.run_validation import validate_survey, flags_only

ROOT = Path(__file__).resolve().parents[2]


def records():
    return tuple(json.loads((ROOT / 'tests' / 'integration' / 'validate' / name).read_text(encoding='utf-8'))
                 for name in ('example_main.json', 'example_coded.json'))


def validate(main, coded):
    return validate_survey(main, coded, codebook_path=ROOT / 'backend' / 'db' / 'data_dict.json')


def age_flags(result):
    return [f for f in result['validation_flags'] if f['reason'].startswith('Residents over 10')]


@pytest.mark.parametrize('male,female', [('1', '1'), ('0', '2')])
def test_unspecified_head_sex_accepts_feasible_assignments(male, female):
    main, coded = records()
    main['residents'] = [{'relationship': 'Head', 'age': '71'}, {'relationship': 'Wife', 'age': '69'}]
    coded.update(number_over_10_m=male, number_over_10_f=female)
    assert age_flags(validate(main, coded)) == []


@pytest.mark.parametrize('male,female', [('2', '0'), ('1', '2'), ('0', '0')])
def test_unspecified_head_sex_still_rejects_impossible_assignments(male, female):
    main, coded = records()
    main['residents'] = [{'relationship': 'Head', 'age': '71'}, {'relationship': 'Wife', 'age': '69'}]
    coded.update(number_over_10_m=male, number_over_10_f=female)
    assert any(f['type'] == 'Page 1–3 conflict' for f in age_flags(validate(main, coded)))


@pytest.mark.parametrize('count,code', [('0', '0'), ('1', '1'), ('1', '2'), ('1', '3'), ('2', '4'), ('9', '4'), ('Balcony', '2')])
def test_sleepout_count_and_category_compatible(count, code):
    main, coded = records()
    main['rooms']['sleepouts'] = count
    coded['number_of_sleepouts'] = code
    assert not any(f['reason'].startswith('Sleepouts:') for f in validate(main, coded)['validation_flags'])


@pytest.mark.parametrize('count,code', [('0', '1'), ('1', '4'), ('2', '2'), ('Balcony', '1')])
def test_sleepout_count_and_category_conflict(count, code):
    main, coded = records()
    main['rooms']['sleepouts'] = count
    coded['number_of_sleepouts'] = code
    assert any(f['type'] == 'Page 1–3 conflict' and f['reason'].startswith('Sleepouts:') for f in validate(main, coded)['validation_flags'])


def test_shared_facility_code_is_not_a_room_count():
    main, coded = records()
    coded['rooms_shared'] = '7'
    assert validate(main, coded)['validation_flags'] == []
    coded['rooms_shared'] = '8'
    assert any(f['type'] == 'Page 3 codebook conflict' and 'rooms_shared' in f['reason'] for f in validate(main, coded)['validation_flags'])


@pytest.mark.parametrize('field,valid,invalid', [
    ('municipality', '08', '33'),
    ('type_of_family', '8', '9'),
    ('normal_household_income', '999', '1000'),
    ('weekly_rent', '99', '100'),
    ('grade_of_occupation_of_head', '9', '8'),
    ('sex_of_head', '1', '2'),
    ('structural_material', '7', '8'),
    ('number_of_sleepouts', '4', '5'),
    ('whether_used_as_bedrooms', '5', '1'),
    ('cooking_facilities', '9', '0'),
    ('age_of_house', '99', '100'),
    ('washhouse', '5', '6'),
])
def test_declared_codebook_domains(field, valid, invalid):
    main, coded = records()
    coded[field] = valid
    if field == 'municipality':
        main['municipality'] = 'Essendon'
    assert not any(f['type'] == 'Page 3 codebook conflict' and f['reason'].startswith(field + ':') for f in validate(main, coded)['validation_flags'])
    coded[field] = invalid
    assert any(f['type'] == 'Page 3 codebook conflict' and f['reason'].startswith(field + ':') for f in validate(main, coded)['validation_flags'])


@pytest.mark.parametrize('name,code', [('Essendon', '08'), ('Brunswick', '2'), ('Box Hill', '00')])
def test_municipality_uses_actual_mapping(name, code):
    main, coded = records()
    main['municipality'] = name
    coded['municipality'] = code
    assert validate(main, coded)['validation_flags'] == []


def test_municipality_mismatch_is_explained():
    main, coded = records()
    main['municipality'] = 'Essendon'
    coded['municipality'] = '2'
    result = validate(main, coded)
    assert any('means Brunswick' in f['reason'] for f in result['validation_flags'])
    assert result['main']['municipality_review_status'] == 'ToBeReviewed'
    assert result['coded']['municipality'] == '2'
    assert 'Page 3: municipality' in flags_only(result)['flags'][0]['fields']


@pytest.mark.parametrize('missing', [None, '/', '[?]'])
def test_missing_municipality_counterpart_is_incomplete(missing):
    main, coded = records()
    main['municipality'] = 'Essendon'
    coded['municipality'] = missing
    assert any(f['type'] == 'Page 1–3 comparison incomplete' and f['reason'].startswith('Municipality:') for f in validate(main, coded)['validation_flags'])


def test_no_reference_fields_and_special_money_codes_not_reinterpreted():
    main, coded = records()
    coded.update(industry_of_head='802', occupation_of_head='5500', removal='[?]', military_service='unmapped text', normal_household_income='997')
    assert validate(main, coded)['validation_flags'] == []


@pytest.mark.parametrize('exact', ['12', '18'])
def test_zero_room_code_accepts_over_eleven(exact):
    main, coded = records()
    main['rooms']['number_of_separate_bedrooms'] = exact
    coded.update(number_of_bedrooms='0', total_number_of_rooms='0')
    assert validate(main, coded)['validation_flags'] == []


def test_over_eleven_bedrooms_cannot_fit_in_five_rooms():
    main, coded = records()
    main['rooms']['number_of_separate_bedrooms'] = '12'
    coded['number_of_bedrooms'] = '0'
    assert any(f['type'] == 'Page 3 internal conflict' and 'bedrooms plus living rooms' in f['reason'] for f in validate(main, coded)['validation_flags'])


@pytest.mark.parametrize('code,source', [('00', '55'), ('98', 'old'), ('99', '105 years.'), ('99', 'over 99 years.')])
def test_house_special_codes_not_treated_as_exact_ages(code, source):
    main, coded = records()
    main['probable_age'] = source
    coded['age_of_house'] = code
    assert not any(f['reason'].startswith('Age of house:') for f in validate(main, coded)['validation_flags'])


def test_over_ninety_nine_house_code_conflicts_with_fifteen():
    main, coded = records()
    main['probable_age'] = '15 years.'
    coded['age_of_house'] = '99'
    assert any(f['type'] == 'Page 1–3 conflict' and f['reason'].startswith('Age of house:') for f in validate(main, coded)['validation_flags'])


@pytest.mark.parametrize('source,code', [('0.5 years', '00'), ('22 years', '99')])
def test_residence_special_codes(source, code):
    main, coded = records()
    main['length_of_residence'] = source
    coded['length_of_residence'] = code
    assert not any(f['reason'].startswith('Length of residence:') for f in validate(main, coded)['validation_flags'])


def test_codebook_aliases_preserve_original_paths():
    main, coded = records()
    coded['no_of_boarders'] = coded.pop('boarders')
    coded['number_over_10_male'] = coded.pop('number_over_10_m')
    coded['no_of_boarders'] = '-1'
    result = validate(main, coded)
    assert any('Page 3: no_of_boarders' in f['fields'] for f in result['validation_flags'])
    assert 'boarders' not in result['coded']


def test_explicit_missing_dictionary_fails(tmp_path):
    # A supplied missing path must fail rather than silently disabling checks.
    main, coded = records()
    with pytest.raises(FileNotFoundError):
        validate_survey(main, coded, codebook_path=tmp_path / 'missing.json')


def test_malformed_dictionary_fails_before_validation(tmp_path):
    path = tmp_path / 'data_dict.json'
    path.write_text('{}', encoding='utf-8')
    main, coded = records()
    with pytest.raises(ValueError):
        validate_survey(main, coded, codebook_path=path)


def test_missing_default_dictionary_preserves_standalone_api(tmp_path, monkeypatch):
    from backend.pipeline.validate import codebook
    monkeypatch.setattr(codebook, '__file__', str(tmp_path / 'backend' / 'pipeline' / 'validate' / 'codebook.py'))
    main, coded = records()
    result = validate_survey(main, coded)
    assert result['validation_flags'] == []
    assert any('Codebook checks not run' in warning for warning in result['validation_warnings'])
