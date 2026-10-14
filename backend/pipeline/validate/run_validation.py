"""One survey's main form and coded card readings -> its flags (US6)."""
from __future__ import annotations

from .codebook import find_codebook_issues, load_dictionary
from .validator import MISSING, _get, _has_content, find_issues, load_checks, load_conventions


#('main', 'residents', 0, 'age') -> 'Page 1: residents[0].age'
def _label(path):
    page, *parts = path
    suffix = ''
    for part in parts:
        suffix += f'[{part}]' if isinstance(part, int) else ('.' if suffix else '') + part
    return ('Page 1' if page == 'main' else 'Page 3') + ': ' + suffix


#a flagged field's value as the reading has it; the residents list as how many residents have anything written
def _shown(document, path):
    raw = _get(document, path)
    if raw is MISSING:
        return '<missing>'
    if path == ('main', 'residents') and isinstance(raw, list):
        return {'populated_records': sum(_has_content(p) for p in raw)}
    return raw


def validate_survey(main: dict, coded: dict, *, survey_id=None, codebook_path=None, conventions=None, checks=None) -> dict:
    """{survey_id, has_flags, validation_flags, validation_warnings} for one survey. Each flag has a type, a reason,
    an optional comparison and its fields ({'Page 1: rooms.number_of_living_rooms': value}). Reads the codebook,
    backend/db/data_dict.json unless codebook_path is given, and the coding conventions to accept from conventions.json
    unless given (as load_conventions() returns); only the checks switched on in checks.json (or checks, as load_checks()
    returns) give flags. Changes nothing."""
    document = {'survey_id': survey_id, 'main': main, 'coded': coded}
    conventions = load_conventions() if conventions is None else conventions
    issues = find_issues(document, conventions)
    warnings = []
    other = main.get('other_children', {})
    if isinstance(other, dict) and any(_has_content(v) for v in other.values()):
        warnings.append('main.other_children lists retained without automatic counts: their entry schema and duplicate semantics are not supplied.')
    dictionary, codebook_warnings = load_dictionary(codebook_path)
    warnings.extend(codebook_warnings)
    for field, special_codes in [('age_of_head', {0}), ('age_of_house', {0, 98}), ('length_of_residence', {99})]:
        value = coded.get(field)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip().isdigit() and int(str(value).strip()) in special_codes:
            warnings.append(f'coded.{field} uses a valid unknown/no-exact-value code; exact cross-page age/duration comparison is not performed.')
    issues.extend(find_codebook_issues(document, dictionary, conventions))
    enabled = load_checks() if checks is None else checks
    issues = [issue for issue in issues if enabled[issue['check']]]
    flags = []
    for issue in issues:
        flag = {k: v for k, v in issue.items() if k != 'fields'}
        flag['fields'] = {_label(path): _shown(document, path) for path in issue['fields']}
        flags.append(flag)
    return {'survey_id': survey_id, 'has_flags': bool(flags), 'validation_flags': flags, 'validation_warnings': warnings}
