"""Resolve the supplied upstream main schema without losing source locations."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
if __package__:
    from .validator import MISSING, _get, _blank, _has_content
else:
    from validator import MISSING, _get, _blank, _has_content

# Left side: stable rule names; right side: upstream source path(s).
MAIN_FIELDS = {
    'NUMBER': [('number_of_dwelling',)],
    'NO. OF SEPARATE BEDROOMS': [('rooms', 'number_of_separate_bedrooms')],
    'NO. OF LIVING ROOMS': [('rooms', 'number_of_living_rooms')],
    'STATE IF USED AS BEDROOMS': [('rooms', 'state_if_used_as_bedrooms')],
    'ROOMS NOT IN DAILY USE': [('rooms', 'rooms_not_in_daily_use')],
    'NUMBER OF SLEEPOUTS': [('rooms', 'sleepouts')],
    'LENGTH OF RESIDENCE': [('length_of_residence',)],
    'PROBABLE AGE': [('probable_age',)],
    'INDUSTRY OF HEAD CODE': [('industry_of_head_code',)],
    'OCCUPATION OF HEAD CODE': [('occupation_of_head_code',)],
}
PERSONAL_FIELDS = {'RELATIONSHIP': 'relationship', 'AGE': 'age', 'SEX': 'sex', 'GENDER': 'gender', 'EARNING STATUS': 'earning_status'}
# Exact Page 3 names from the supplied coded.json template.
CODED_FIELDS = {
    'NUMBER OF DWELLING': [('number_of_dwelling',)],
    'NUMBER OF BEDROOMS': [('number_of_bedrooms',), ('rooms', 'number_of_bedrooms')],
    'NUMBER OF LIVING ROOMS': [('number_of_living_rooms',), ('rooms', 'number_of_living_rooms')],
    'ROOMS NOT IN DAILY USE': [('rooms_not_in_daily_use',), ('rooms', 'rooms_not_in_daily_use')],
    'NUMBER OF SLEEPOUTS': [('number_of_sleepouts',), ('rooms', 'sleepouts')],
    'TOTAL NUMBER OF ROOMS': [('total_number_of_rooms',), ('rooms', 'total_number_of_rooms')],
    'ROOMS SHARED': [('rooms_shared',), ('rooms', 'rooms_shared')],
    'TOTAL NO. RESIDENT MEMBERS': [('total_resident_members',)],
    'NUMBER UNDER 5': [('number_under_5',)],
    'NUMBER 5-10': [('number_5_to_10',)],
    ('NUMBER OVER 10', 'M'): [('number_over_10_m',), ('number_over_10_male',)],
    ('NUMBER OVER 10', 'F'): [('number_over_10_f',), ('number_over_10_female',)],
    'CHILDREN UNDER 14': [('children_under_14',)],
    'NO. OF BOARDERS': [('boarders',), ('no_of_boarders',)],
    'NO. OF PARTICIPATING MEMBERS': [('participating_members',), ('no_of_participating_members',)],
    'NO. OF ADULT M. BREADWINNERS': [('adult_m_breadwinners',), ('no_of_adult_male_breadwinners',)],
    'NO. OF ADULT F. BREADWINNERS': [('adult_f_breadwinners',), ('no_of_adult_female_breadwinners',)],
    'NO. OF JUVENILE BREADWINNERS (UNDER 21)': [('juvenile_breadwinners_under_21',), ('no_of_juvenile_breadwinners',)],
    'PERSONS SHARING': [('persons_sharing',)],
    'RETIRED AND INDEP. PERSONS': [('retired_and_indep_persons',)],
    'HOME DUTIES': [('home_duties',)],
    'AGE OF HEAD': [('age_of_head',)],
    'INDUSTRY OF H.': [('industry_of_head',)],
    'OCCUPATION OF H.': [('occupation_of_head',)],
    'AGE OF HOUSE': [('age_of_house',)],
    'LENGTH OF RESIDENCE': [('length_of_residence',)],
    'CHILDREN OTHER THAN THOSE AT HOME': [('children_other_than_those_at_home',)],
    ('CHILDREN OF H. OR WIFE', 'LIVING'): [('children_of_h_or_wife_living',), ('children_of_head_or_wife_living',)],
    ('CHILDREN OF H. OR WIFE', 'DEAD'): [('children_of_h_or_wife_dead',), ('children_of_head_or_wife_dead',)],
    ('CHILDREN OF H. OR WIFE', 'TOTAL'): [('children_of_h_or_wife_total',), ('children_of_head_or_wife_total',)],
}


def _put(target, path, value):
    for part in path[:-1]:
        target = target.setdefault(part, {})
    target[path[-1]] = value


def normalize_survey(survey: dict[str, Any]):
    """Return (rule input, canonical-to-source paths, warnings).

    Survey input is {survey_id, main: <raw Page1>, coded: <raw Page3>, notes?: ...}.
    Page payloads with a fields wrapper are deliberately not silently unwrapped.
    """
    if not isinstance(survey, dict):
        raise ValueError('Survey must be an object')
    for category in ('main', 'coded'):
        if not isinstance(survey.get(category), dict):
            raise ValueError(f'{category} must be a Page JSON object; both pages are required')
    result = {'survey_id': survey.get('survey_id'), 'pages': {}}
    mapping = {}
    warnings = []

    def assign(category, fields, key, candidates):
        stable = key if isinstance(key, tuple) else (key,)
        source = survey[category]
        present = [(p, _get(source, p)) for p in candidates if _get(source, p) is not MISSING]
        if len(present) > 1:
            # Conflicting aliases must never be hidden by choosing the first.
            if any(v != present[0][1] for _, v in present[1:]):
                raise ValueError(f'Conflicting aliases for {category}.{stable}: {[p for p, _ in present]}')
        chosen, value = present[0] if present else (candidates[0], MISSING)
        mapping[('pages', category, 'fields', *stable)] = (category, *chosen)
        if value is not MISSING:
            _put(fields, stable, deepcopy(value))
        return bool(present)

    for category, registry in [('main', MAIN_FIELDS), ('coded', CODED_FIELDS)]:
        fields = {}
        result['pages'][category] = {'page_category': category, 'fields': fields}
        # Old uppercase Page3 payloads may be passed directly.
        if category == 'coded':
            known_upper = {'NUMBER OVER 10', 'CHILDREN OF H. OR WIFE'} | {k for k in registry if isinstance(k,str)}
            upper = any(k in survey[category] for k in known_upper)
            lower = any(_get(survey[category], p) is not MISSING for candidates in registry.values() for p in candidates)
            if upper and lower:
                raise ValueError('Mixed uppercase and snake_case coded schemas: provide one consistent format')
            if upper:
                fields.update(deepcopy(survey[category]))
                for key in registry:
                    stable = key if isinstance(key, tuple) else (key,)
                    mapping[('pages', category, 'fields', *stable)] = (category, *stable)
                continue
        found = sum(assign(category, fields, key, candidates) for key,candidates in registry.items())
        if category == 'coded' and not found:
            raise ValueError('Coded payload has no recognised validation fields; update CODED_FIELDS to its actual schema')

    source = survey['main']
    residents = source.get('residents', MISSING)
    if residents is not MISSING and residents is not None and not isinstance(residents,list):
        raise ValueError('main.residents must be a list or null')
    main_fields = result['pages']['main']['fields']
    mapping[('pages','main','fields','PERSONNEL')] = ('main','residents')
    if isinstance(residents,list):
        people = []
        for index, resident in enumerate(residents):
            if not isinstance(resident,dict):
                raise ValueError('Every main.residents entry must be an object')
            person = {'PERSONAL': {}}
            # Preserve whether the resident column contains personal source data.
            # The upstream prompt defines residents by personal cells, not income/occupation.
            person['SOURCE_CONTENT'] = {key: resident.get(key) for key in ('relationship', 'age', 'earning_status')}
            for stable, raw in PERSONAL_FIELDS.items():
                mapping[('pages','main','fields','PERSONNEL',index,'PERSONAL',stable)] = ('main','residents',index,raw)
                if raw in resident:
                    person['PERSONAL'][stable] = resident[raw]
            people.append(person)
        # A blank schema's placeholder list is unknown, not zero known residents.
        main_fields['PERSONNEL'] = people if any(_has_content({k:r.get(k) for k in ('relationship','age','earning_status')}) for r in residents) else None
    elif residents is not MISSING:
        main_fields['PERSONNEL'] = None
    # The real main schema stores other_children once at survey level.
    # Entries have no documented element schema, so do not count list entries as children.
    other = source.get('other_children', {})
    if isinstance(other,dict) and any(_has_content(v) for v in other.values()):
        warnings.append('main.other_children lists retained without automatic counts: their entry schema and duplicate semantics are not supplied.')
    return result,mapping,warnings
