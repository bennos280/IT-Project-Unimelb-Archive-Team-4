"""Validate declared Page 3 domains using the repository's data dictionary."""
from __future__ import annotations

import json
import re
from pathlib import Path

if __package__:
    from .validator import _blank, _count, _get, _text, MISSING
else:
    from validator import _blank, _count, _get, _text, MISSING

# Dictionary spellings differ from the actual transcriber template.
ALIASES = {
    'number_of_dwellings': ('number_of_dwelling',),
    'number_of_households': ('number_of_household',),
    'number_over_10_male': ('number_over_10_m',),
    'number_over_10_female': ('number_over_10_f',),
    'no_of_boarders': ('boarders',),
    'no_of_participating_members': ('participating_members',),
    'no_of_adult_male_breadwinners': ('adult_m_breadwinners',),
    'no_of_adult_female_breadwinners': ('adult_f_breadwinners',),
    'no_of_juvenile_breadwinners': ('juvenile_breadwinners_under_21',),
    'main_source_of_heads_unearned_income': ('main_source_heads_unearned_income',),
    'subsidiary_source_of_heads_income': ('subsidiary_source_heads_income',),
    'pre_war_occupation': ('prewar_occupation',),
    'washouse': ('washhouse',),
    'children_of_head_or_wife_living': ('children_of_h_or_wife_living',),
    'children_of_head_or_wife_dead': ('children_of_h_or_wife_dead',),
    'children_of_head_or_wife_total': ('children_of_h_or_wife_total',),
}
ROOM_COUNTS = {'total_number_of_rooms', 'number_of_bedrooms', 'number_of_living_rooms'}


def load_dictionary(path=None):
    """A missing default dictionary preserves the standalone API with a warning.

    A supplied path or an existing invalid dictionary is an input error.
    """
    target = Path(path) if path is not None else Path(__file__).resolve().parents[2] / 'data_dict.json'
    if path is None and not target.exists():
        return None, ['Codebook checks not run: repository-root data_dict.json is unavailable.']
    data = json.loads(target.read_text(encoding='utf-8'))
    fields = _get(data, ('pages', '3', 'fields'))
    if not isinstance(fields, dict) or not fields:
        raise ValueError('data_dict.json must contain a non-empty pages.3.fields object')
    for name, spec in fields.items():
        if not isinstance(spec, dict) or 'data_type' not in spec or 'possible_values' not in spec:
            raise ValueError(f'Invalid codebook definition for {name}')
        allowed = spec['possible_values']
        if allowed != 'N/A' and not isinstance(allowed, dict):
            raise ValueError(f'Invalid possible_values for {name}')
        if isinstance(allowed, dict) and any(not re.fullmatch(r'\d+(?:-\d+)?', key) for key in allowed):
            raise ValueError(f'Unsupported codebook range for {name}')
    return fields, []


def _allowed(value, choices):
    text = _text(value)
    if text is None or not re.fullmatch(r'\d+', text):
        return False
    number = int(text)
    for key in choices:
        low, _, high = key.partition('-')
        if int(low) <= number <= int(high or low):
            return True
    return False


def find_codebook_issues(document, fields):
    """Return native-source issues; N/A definitions and blank cells are skipped."""
    if fields is None:
        return []
    coded = document['coded']
    issues = []

    def issue(kind, reason, paths, comparison):
        issues.append({'type': kind, 'reason': reason, 'comparison': comparison,
                       'fields': [{'path': path} for path in paths]})

    for name, spec in fields.items():
        candidates = (name, *ALIASES.get(name, ()))
        present = [key for key in candidates if key in coded]
        if len(present) > 1 and any(coded[key] != coded[present[0]] for key in present[1:]):
            raise ValueError(f'Conflicting codebook aliases for coded.{name}: {present}')
        if not present:
            continue
        key = present[0]
        value = coded[key]
        if _blank(value):
            continue
        choices = spec['possible_values']
        # The plural dictionary label is not a count in the transcriber: this
        # is a dwelling identifier, including letters. Do not redefine it here.
        if name in ('number_of_dwellings', 'number_of_households'):
            continue
        if name in ROOM_COUNTS:
            number = _count(value)
            valid = number is not None and number <= 11
            expression = 'Codes 1-11 are exact room counts; 0 represents over 11.'
        elif isinstance(choices, dict):
            valid = _allowed(value, choices)
            expression = 'Allowed codebook entries: ' + ', '.join(choices)
        elif str(spec['data_type']).upper() == 'INTEGER':
            valid = _count(value) is not None
            expression = 'Codebook data_type INTEGER: non-negative whole count.'
        else:
            continue
        if not valid:
            issue('Page 3 codebook conflict', f'{key}: value is outside the domain declared in data_dict.json.', [('coded', key)], expression)

    # Municipality names have an explicit, unambiguous mapping in this file.
    spec = fields.get('municipality', {})
    choices = spec.get('possible_values')
    raw_main = document['main'].get('municipality', MISSING)
    raw_code = coded.get('municipality', MISSING)
    if isinstance(choices, dict) and not (_blank(raw_main) and _blank(raw_code)):
        paths = [('main', 'municipality'), ('coded', 'municipality')]
        if _blank(raw_main) or _blank(raw_code):
            issue('Page 1–3 comparison incomplete', 'Municipality: a corresponding name or code is missing.', paths, 'Compare Page 1 municipality with the explicit dictionary label for Page 3.')
        elif _allowed(raw_code, choices):
            label = next((v for k, v in choices.items() if '-' not in k and int(k) == int(str(raw_code).strip())), None)
            if label and _text(label) in ('not known', 'not applicable'):
                issue('Page 1–3 comparison incomplete', 'Municipality: the coded value supplies no comparable municipality name.', paths, f'Page 3 code represents {label}.')
            elif label and _text(raw_main) != _text(label):
                issue('Page 1–3 conflict', f'Municipality: Page 1 records {raw_main}, but Page 3 code {raw_code} means {label}.', paths, 'Use the explicit municipality mapping in data_dict.json; no fuzzy name matching.')
    return issues
