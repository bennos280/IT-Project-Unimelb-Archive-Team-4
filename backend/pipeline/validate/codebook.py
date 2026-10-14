"""Validate declared Page 3 domains using the repository's data dictionary."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .validator import _blank, _count, _get, _text, load_conventions, MISSING

ROOM_COUNTS = {'total_number_of_rooms', 'number_of_bedrooms', 'number_of_living_rooms'}


def load_dictionary(path=None):
    """A missing default dictionary preserves the standalone API with a warning.

    A supplied path or an existing invalid dictionary is an input error.
    """
    target = Path(path) if path is not None else Path(__file__).resolve().parents[2] / 'db' / 'data_dict.json'
    if path is None and not target.exists():
        return None, ['Codebook checks not run: backend/db/data_dict.json is unavailable.']
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


def _name(value):
    """'N. Fitzroy.' -> 'n fitzroy'"""
    return ' '.join(re.sub(r'[^\w\s]', ' ', _text(value) or '').split())


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


def find_codebook_issues(document, fields, conventions=None):
    """Return native-source issues; N/A definitions and blank cells are skipped. conventions: as load_conventions()."""
    if fields is None:
        return []
    on = load_conventions() if conventions is None else conventions
    coded = document['coded']
    issues = []

    def issue(check, kind, reason, paths, comparison):
        issues.append({'check': check, 'type': kind, 'reason': reason, 'comparison': comparison,
                       'fields': list(paths)})

    for name, spec in fields.items():
        if name not in coded:
            continue
        value = coded[name]
        if _blank(value):
            continue
        choices = spec['possible_values']
        # a dwelling identifier, letters included (24A), not a count
        if name == 'number_of_dwelling':
            continue
        # 0: no room used as a bedroom (not listed in the codebook)
        if name == 'whether_used_as_bedrooms' and _text(value) == '0':
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
            issue('codebook_codes', 'Page 3 codebook conflict', f"{name}: {value} isn't one of the codebook's codes; check the card for an overwritten or unclear figure.", [('coded', name)], expression)

    # page 1 often names the suburb (Glen Iris), coded as its council (Camberwell)
    spec = fields.get('municipality', {})
    choices = spec.get('possible_values')
    raw_main = document['main'].get('municipality', MISSING)
    raw_code = coded.get('municipality', MISSING)
    if isinstance(choices, dict) and not (_blank(raw_main) and _blank(raw_code)):
        paths = [('main', 'municipality'), ('coded', 'municipality')]
        # codes 29 onwards aren't councils (Various, Outside Metrop. area, ...)
        councils = {_name(label) for code, label in choices.items() if '-' not in code and int(code) < 29}
        if _blank(raw_main) or _blank(raw_code):
            issue('municipality', 'Page 1–3 comparison incomplete', 'Municipality: a corresponding name or code is missing.', paths, 'Compare Page 1 municipality with the explicit dictionary label for Page 3.')
        elif _allowed(raw_code, choices):
            label = next((v for k, v in choices.items() if '-' not in k and int(k) == int(str(raw_code).strip())), None)
            if label and _text(label) in ('not known', 'not applicable'):
                issue('municipality', 'Page 1–3 comparison incomplete', 'Municipality: the coded value supplies no comparable municipality name.', paths, f'Page 3 code represents {label}.')
            elif label and _name(raw_main) != _name(label) and (_name(raw_main) in councils or not on['suburb_coded_as_council']):
                issue('municipality', 'Page 1–3 conflict', f'Municipality: Page 1 records {raw_main}, but Page 3 code {raw_code} means {label}.', paths, 'The names in data_dict.json; punctuation is ignored.')
    return issues
