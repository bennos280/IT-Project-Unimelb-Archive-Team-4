"""US6: evidence-based consistency checks; no transcription is corrected."""
from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

PathTuple = tuple[Any, ...]
MISSING = object()


def _get(data: Any, path: PathTuple) -> Any:
    for part in path:
        try:
            data = data[part]
        except (KeyError, IndexError, TypeError):
            return MISSING
    return data


def _blank(value: Any) -> bool:
    return value is MISSING or value is None or (isinstance(value, str) and value.strip() in ('', '/', '[?]'))


def _text(value: Any) -> str | None:
    if _blank(value) or isinstance(value, (dict, list, bool)):
        return None
    return ' '.join(str(value).split()).casefold()


def _number(value: Any) -> Decimal | None:
    if _blank(value) or isinstance(value, (dict, list, bool)):
        return None
    text = str(value).strip().casefold()
    if text in ('none', 'nil', 'no', 'zero'):
        return Decimal(0)
    try:
        result = Decimal(text.replace(',', ''))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def _dwelling(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    match = re.fullmatch(r'(\d+)\s*([a-z]?)', text)
    return str(int(match[1])) + match[2].upper() if match else None


def _code(value: Any) -> str | None:
    text = _text(value)
    return str(int(text)) if text and re.fullmatch(r'\d+',text) else None


def _count(value: Any) -> Decimal | None:
    n = _number(value)
    return n if n is not None and n >= 0 and n == n.to_integral_value() else None


def _years(value: Any) -> Decimal | None:
    text = _text(value)
    if text is None:
        return None
    for fraction, decimal in [('½', '.5'), ('¼', '.25'), ('¾', '.75')]:
        text = text.replace(fraction, decimal)
    # An exact duration, not a range or an approximation.
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:years?|yrs?\.?|y\.?)?', text)
    return Decimal(match[1]) if match else None


def _has_content(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_content(v) for k, v in value.items() if not k.endswith(('_flag', '_review_status')))
    if isinstance(value, list):
        return any(_has_content(v) for v in value)
    return not _blank(value)


@dataclass(frozen=True)
class Ref:
    path: PathTuple
    value: Any


class Adapter:
    """Only this class resolves page categories and source-field locations."""
    def __init__(self, survey: dict[str, Any]):
        self.survey = survey
        pages = survey.get('pages')
        if not isinstance(pages, dict):
            raise ValueError('survey.pages must be an object')
        self.keys: dict[str, str] = {}
        for key, page in pages.items():
            if not isinstance(page, dict):
                raise ValueError(f'Page {key!r} must be an object')
            category = page.get('page_category', key)
            category = {'page1': 'main', 'page 1': 'main', 'page3': 'coded', 'page 3': 'coded'}.get(category, category)
            if category in ('main', 'coded'):
                if category in self.keys:
                    raise ValueError(f'Multiple {category} pages: resolve bundling before US6')
                if not isinstance(page.get('fields'), dict):
                    raise ValueError(f'{category}.fields must be an object')
                self.keys[category] = key
        # Missing pages belong to the upstream bundling step, not value mismatches.
        for category in ('main', 'coded'):
            if category not in self.keys:
                raise ValueError(f'Missing {category} page: cannot run Page 1–3 validation')

    def ref(self, category: str, *parts: Any) -> Ref:
        path = ('pages', self.keys[category], 'fields', *parts)
        return Ref(path, _get(self.survey, path))

    def main(self, *parts: Any) -> Ref:
        return self.ref('main', *parts)

    def coded(self, *parts: Any) -> Ref:
        return self.ref('coded', *parts)


def _label(path: PathTuple, adapter: Adapter) -> str:
    page = 'Page 1' if path[1] == adapter.keys['main'] else 'Page 3'
    suffix = '.'.join(f'[{part}]' if isinstance(part, int) else str(part) for part in path[3:])
    return f'{page}: {suffix}'


def find_issues(survey: dict[str, Any]) -> list[dict[str, Any]]:
    a = Adapter(survey)
    issues: list[dict[str, Any]] = []

    def issue(kind: str, reason: str, refs: list[Ref], derived: str | None = None) -> None:
        # Deduplicate refs but retain stable source order and each missing location.
        fields = []
        seen = set()
        for ref in refs:
            if ref.path in seen:
                continue
            seen.add(ref.path)
            fields.append({'field': _label(ref.path, a), 'value': None if ref.value is MISSING else ref.value,
                           'missing': ref.value is MISSING, 'path': ref.path})
        item = {'type': kind, 'reason': reason, 'fields': fields}
        if derived:
            item['comparison'] = derived
        issues.append(item)

    def compare(left: Ref, right: Ref, name: str, convert: Callable = _count) -> None:
        if _blank(left.value) and _blank(right.value):
            return
        lv, rv = convert(left.value), convert(right.value)
        if lv is None or rv is None:
            issue('Page 1–3 comparison incomplete', f'{name}: one corresponding value is missing, marked / or [?], or cannot be interpreted for this comparison.', [left, right])
        elif lv != rv:
            issue('Page 1–3 conflict', f'{name}: the corresponding values differ.', [left, right])

    def relation(refs: list[Ref], name: str, predicate: Callable, expression: str, page='Page 3') -> None:
        if all(_blank(r.value) for r in refs):
            return
        values = [_count(r.value) for r in refs]
        if any(v is None for v in values):
            issue(f'{page} comparison incomplete', f'{name}: a value required by this relationship is missing or is not a non-negative whole count.', refs, expression)
        elif not predicate(values):
            issue(f'{page} internal conflict', name, refs, expression)

    for left, right in [
        ('NUMBER', 'NUMBER OF DWELLING'),
        ('NO. OF SEPARATE BEDROOMS', 'NUMBER OF BEDROOMS'),
        ('NO. OF LIVING ROOMS', 'NUMBER OF LIVING ROOMS'),
        ('ROOMS NOT IN DAILY USE', 'ROOMS NOT IN DAILY USE'),
        ('NUMBER OF SLEEPOUTS', 'NUMBER OF SLEEPOUTS'),
    ]:
        compare(a.main(left), a.coded(right), right, _dwelling if left == 'NUMBER' else _count)
    for source,target in [('INDUSTRY OF HEAD CODE','INDUSTRY OF H.'),('OCCUPATION OF HEAD CODE','OCCUPATION OF H.')]:
        # Only explicit handwritten codes, never the occupation/industry prose.
        if a.main(source).value is not MISSING:
            compare(a.main(source),a.coded(target),source,_code)
    compare(a.main('LENGTH OF RESIDENCE'), a.coded('LENGTH OF RESIDENCE'), 'Length of residence', _years)

    table = a.main('PERSONNEL')
    if not _blank(table.value) and not isinstance(table.value, list):
        raise ValueError('main.fields.PERSONNEL must be a list or null')
    people = [(i, person) for i, person in enumerate(table.value or []) if _has_content(person)] if isinstance(table.value, list) else []
    if any(not isinstance(p, dict) for _, p in people):
        raise ValueError('Every populated PERSONNEL entry must be an object')
    total = a.coded('TOTAL NO. RESIDENT MEMBERS')

    def derived_compare(target: Ref, value: int | None, refs: list[Ref], name: str, explanation: str) -> None:
        if value is None and _blank(target.value) and all(_blank(r.value) for r in refs):
            return
        tv = _count(target.value)
        if value is None or tv is None:
            issue('Page 1–3 comparison incomplete', f'{name}: the corresponding source data or coded count is missing or insufficient to compute an exact count.', refs + [target], explanation)
        elif value != tv:
            issue('Page 1–3 conflict', f'{name}: Page 1 derives {value}, but Page 3 records {target.value}.', refs + [target], explanation)

    derived_compare(total, len(people) if isinstance(table.value, list) else None, [table], 'Resident total', 'Count populated PERSONNEL columns; empty template columns are ignored.')
    age_refs = [a.main('PERSONNEL', i, 'PERSONAL', 'AGE') for i, _ in people]
    ages = [_count(r.value) for r in age_refs]
    complete_ages = isinstance(table.value, list) and all(v is not None for v in ages)
    for field, predicate in [('NUMBER UNDER 5', lambda n: n < 5), ('NUMBER 5-10', lambda n: 5 <= n <= 10), ('CHILDREN UNDER 14', lambda n: n < 14)]:
        value = sum(predicate(v) for v in ages) if complete_ages else None
        derived_compare(a.coded(field), value, age_refs or [table], field, f'Count resident ages using {field}; 5–10 includes ages 5 and 10; under 14 excludes 14.')

    def sex(person: dict) -> str | None:
        personal = person.get('PERSONAL', {})
        explicit = _text(personal.get('SEX')) or _text(personal.get('GENDER'))
        if explicit in ('m', 'male'):
            return 'M'
        if explicit in ('f', 'female'):
            return 'F'
        rel = _text(personal.get('RELATIONSHIP'))
        if rel in ('son', 'husband', 'father', 'brother'):
            return 'M'
        if rel in ('daughter', 'wife', 'mother', 'sister'):
            return 'F'
        return None  # Head, boarder and names do not establish sex.

    sex_refs = [a.main('PERSONNEL', i, 'PERSONAL', 'RELATIONSHIP') for i, _ in people]
    sex_refs += [a.main('PERSONNEL', i, 'PERSONAL', key) for i, p in people for key in ('SEX', 'GENDER') if key in p.get('PERSONAL', {})]
    for gender in ('M', 'F'):
        older = [(i, p, age) for (i, p), age in zip(people, ages) if age is not None and age > 10]
        known = complete_ages and all(sex(p) is not None for _, p, _ in older)
        value = sum(sex(p) == gender for _, p, _ in older) if known else None
        derived_compare(a.coded('NUMBER OVER 10', gender), value, age_refs + sex_refs or [table], f'Residents over 10 ({gender})', 'Count ages >10 by explicit sex or unambiguous relationship; do not guess the sex of Head.')

    heads = [(i, p) for i, p in people if _text(p.get('PERSONAL', {}).get('RELATIONSHIP')) in ('head', 'h', 'h.')]
    if len(heads) == 1:
        i, _ = heads[0]
        compare(a.main('PERSONNEL', i, 'PERSONAL', 'AGE'), a.coded('AGE OF HEAD'), 'Age of head')
    elif heads or not _blank(a.coded('AGE OF HEAD').value):
        issue('Page 1–3 comparison incomplete', 'Age of head: Page 1 does not identify exactly one Head; no person is selected by position.', [a.main('PERSONNEL', i, 'PERSONAL', 'RELATIONSHIP') for i, _ in people] + [a.coded('AGE OF HEAD')])

    # Derive boarder counts only with a complete relationship column.
    rels = [_text(p.get('PERSONAL', {}).get('RELATIONSHIP')) for _, p in people]
    boarders = sum(r in ('boarder', 'lodger') for r in rels) if isinstance(table.value, list) and all(r is not None for r in rels) else None
    derived_compare(a.coded('NO. OF BOARDERS'), boarders, sex_refs or [table], 'Boarders', 'Count explicit Boarder/Lodger relationships; no inference from income.')

    child = lambda key: a.coded('CHILDREN OF H. OR WIFE', key)
    relation([child('LIVING'), child('DEAD'), child('TOTAL')], 'Children living plus dead must equal children total.', lambda v: v[0] + v[1] == v[2], 'LIVING + DEAD = TOTAL')
    bands = [a.coded('NUMBER UNDER 5'), a.coded('NUMBER 5-10'), a.coded('NUMBER OVER 10', 'M'), a.coded('NUMBER OVER 10', 'F')]
    relation(bands + [total], 'Resident age bands must add to resident total.', lambda v: sum(v[:-1]) == v[-1], 'UNDER 5 + 5–10 + OVER 10 M + OVER 10 F = TOTAL RESIDENTS')
    bread = [a.coded(n) for n in ('NO. OF ADULT M. BREADWINNERS', 'NO. OF ADULT F. BREADWINNERS', 'NO. OF JUVENILE BREADWINNERS (UNDER 21)')]
    relation(bread + [total], 'Breadwinner categories cannot exceed residents.', lambda v: sum(v[:-1]) <= v[-1], 'ADULT M + ADULT F + JUVENILE BREADWINNERS <= TOTAL RESIDENTS')
    for name in ('NO. OF BOARDERS', 'NO. OF PARTICIPATING MEMBERS', 'CHILDREN UNDER 14', 'PERSONS SHARING', 'RETIRED AND INDEP. PERSONS', 'HOME DUTIES'):
        relation([a.coded(name), total], f'{name} cannot exceed residents.', lambda v: v[0] <= v[1], f'{name} <= TOTAL RESIDENTS')
    # Age subgroups overlap: under-14 includes all under-5 and 5–10 residents.
    relation(bands[:2] + [a.coded('CHILDREN UNDER 14')], 'Children under 14 cannot be fewer than residents aged 10 or younger.', lambda v: v[0] + v[1] <= v[2], 'UNDER 5 + 5–10 <= CHILDREN UNDER 14')
    rooms = a.coded('TOTAL NUMBER OF ROOMS')
    for name in ('NUMBER OF BEDROOMS', 'NUMBER OF LIVING ROOMS', 'ROOMS NOT IN DAILY USE', 'ROOMS SHARED'):
        relation([a.coded(name), rooms], f'{name} cannot exceed total rooms.', lambda v: v[0] <= v[1], f'{name} <= TOTAL ROOMS')
    # Separate bedrooms and living rooms are distinct rooms, even when a living room is also slept in.
    relation([a.coded('NUMBER OF BEDROOMS'), a.coded('NUMBER OF LIVING ROOMS'), rooms], 'Separate bedrooms plus living rooms cannot exceed total rooms.', lambda v: v[0] + v[1] <= v[2], 'BEDROOMS + LIVING ROOMS <= TOTAL ROOMS')

    # Main-page relationships: rooms not in use are not an extra room category.
    for state, count in [('STATE IF USED AS BEDROOMS', 'NO. OF LIVING ROOMS')]:
        s, c = a.main(state), a.main(count)
        if _text(s.value) in ('yes', 'y', 'y.') and _count(c.value) == 0:
            issue('Page 1 internal conflict', 'Living rooms are said to be used as bedrooms, but the living-room count is zero.', [s, c])
        elif _text(s.value) in ('yes', 'y', 'y.') and _count(c.value) is None:
            issue('Page 1 comparison incomplete', 'Living rooms used as bedrooms: the living-room count is missing or cannot be interpreted.', [s, c])

    # Child relationship establishes a lower bound, not a full parentage count.
    resident_children = [a.main('PERSONNEL', i, 'PERSONAL', 'RELATIONSHIP') for i, p in people if _text(p.get('PERSONAL', {}).get('RELATIONSHIP')) in ('son', 'daughter')]
    if resident_children:
        living = _count(child('LIVING').value)
        if living is None:
            issue('Page 1–3 comparison incomplete', 'Resident sons/daughters require a comparable living-children count.', resident_children + [child('LIVING')])
        elif len(resident_children) > living:
            issue('Page 1–3 conflict', 'Page 1 resident sons/daughters exceed Page 3 living children.', resident_children + [child('LIVING')], f'Resident sons/daughters ({len(resident_children)}) <= LIVING')
    relation([a.coded('CHILDREN OTHER THAN THOSE AT HOME'), child('LIVING')], 'Children living elsewhere cannot exceed living children.', lambda v: v[0] <= v[1], 'CHILDREN OTHER THAN THOSE AT HOME <= LIVING')
    if resident_children and not _blank(a.coded('CHILDREN OTHER THAN THOSE AT HOME').value):
        elsewhere = _count(a.coded('CHILDREN OTHER THAN THOSE AT HOME').value)
        living = _count(child('LIVING').value)
        refs = resident_children + [a.coded('CHILDREN OTHER THAN THOSE AT HOME'), child('LIVING')]
        if elsewhere is not None and living is not None and len(resident_children) + elsewhere > living:
            issue('Page 1–3 conflict', 'Resident children plus children elsewhere exceed living children.', refs, f'{len(resident_children)} resident sons/daughters + elsewhere <= LIVING')
    for main_name, target in [('DIED', child('DEAD')), ('LIVING ELSEWHERE', a.coded('CHILDREN OTHER THAN THOSE AT HOME'))]:
        sources = [a.main('PERSONNEL', i, 'OTHER CHILDREN', main_name) for i, _ in heads]
        if len(heads) == 1 and sources and not _blank(sources[0].value):
            compare(sources[0], target, f"Head's other children: {main_name}")
        # With multiple parents the source may be duplicated; do not sum it.
    # A probable-age interval can validate membership without equality.
    probable, house_age = a.main('PROBABLE AGE'), a.coded('AGE OF HOUSE')
    raw = _text(probable.value)
    if raw and _blank(house_age.value):
        issue('Page 1–3 comparison incomplete', 'Age of house: the corresponding coded age is missing.', [probable, house_age])
    elif raw:
        interval = re.fullmatch(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?\.?)?', raw)
        exact = _years(probable.value)
        if interval or exact is not None:
            low, high = (Decimal(interval[1]), Decimal(interval[2])) if interval else (exact, exact)
            age = _years(house_age.value)
            if age is None:
                issue('Page 1–3 comparison incomplete', 'Age of house: the corresponding coded age is missing or cannot be interpreted.', [probable, house_age])
            elif not low <= age <= high:
                issue('Page 1–3 conflict', 'Coded age of house is outside the Page 1 probable-age interval.', [probable, house_age], f'{low} <= AGE OF HOUSE <= {high}')
        else:
            bound = re.fullmatch(r'(over|under|more than|less than)\s+(\d+(?:\.\d+)?)\s*(?:years?|yrs?\.?)?', raw)
            age = _years(house_age.value)
            if bound and age is not None:
                threshold = Decimal(bound[2])
                good = age > threshold if bound[1] in ('over', 'more than') else age < threshold
                if not good:
                    issue('Page 1–3 conflict', 'Coded age of house contradicts the Page 1 probable-age bound.', [probable, house_age])
            else:
                issue('Page 1–3 comparison incomplete', 'Age of house: the supplied ages cannot be compared without interpreting an approximation or unclear unit.', [probable, house_age])
    elif not _blank(house_age.value):
        issue('Page 1–3 comparison incomplete', 'Age of house: the corresponding probable age is missing.', [probable, house_age])
    return issues


def find_flagged_fields(survey: dict[str, Any]) -> set[PathTuple]:
    """Compatibility API: exact affected locations. Use find_issues for reasons."""
    return {f['path'] for item in find_issues(survey) for f in item['fields']}


def _public_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in issues:
        public = {k: v for k, v in item.items() if k != 'fields'}
        def display(field):
            if field['missing']:
                return '<missing>'
            if field['path'][-1] == 'PERSONNEL' and isinstance(field['value'], list):
                return {'populated_records': sum(_has_content(p) for p in field['value'])}
            return field['value']
        public['fields'] = {f['field']: display(f) for f in item['fields']}
        result.append(public)
    return result


def make_flags_only_output(survey: dict[str, Any], flags=None) -> dict[str, Any]:
    """One flat entry per relationship; no repeated page wrappers/boolean flags."""
    issues = find_issues(survey) if flags is None or isinstance(flags, set) else flags
    return {'survey_id': survey.get('survey_id'), 'flags': _public_issues(issues)}


def make_flagged_output(survey: dict[str, Any], flags=None) -> dict[str, Any]:
    issues = find_issues(survey) if flags is None or isinstance(flags, set) else flags
    locations = {f['path'] for item in issues for f in item['fields']}
    output = deepcopy(survey)
    output['has_flags'] = bool(issues)
    output['validation_flags'] = _public_issues(issues)
    for path in sorted(locations, key=lambda p: tuple(str(x) for x in p)):
        page = output['pages'][path[1]]
        page['flagged'] = True
        parent = _get(output, path[:-1])
        if isinstance(parent, dict):
            parent[f'{path[-1]}_flag'] = True
            parent[f'{path[-1]}_review_status'] = 'ToBeReviewed'
        # Missing intermediate containers are preserved; validation_flags still
        # contains their exact missing location. Do not invent original values.
    return output


def validate_document(document: Any) -> tuple[Any, Any]:
    """Accept a single survey, a list, or {surveys: [...]} without merging records."""
    def one(survey):
        if not isinstance(survey, dict):
            raise ValueError('Each survey must be an object')
        issues = find_issues(survey)
        return make_flagged_output(survey, issues), make_flags_only_output(survey, issues)
    if isinstance(document, list):
        results = [one(s) for s in document]
        return [r[0] for r in results], [r[1] for r in results]
    if isinstance(document, dict) and 'surveys' in document:
        if not isinstance(document['surveys'], list):
            raise ValueError('surveys must be a list')
        full, compact = validate_document(document['surveys'])
        return {**document, 'surveys': full}, {'surveys': compact}
    return one(document)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python validate.py sample_input.json')
    input_path = Path(sys.argv[1])
    if input_path.name in ('output_flagged.json', 'output_flags_only.json'):
        raise SystemExit('Use an original input filename, not an output filename')
    try:
        document = json.loads(input_path.read_text(encoding='utf-8'))
        full, compact = validate_document(document)
    except (ValueError, OSError) as error:
        raise SystemExit(f'Validation input error: {error}') from error
    # Validate the entire batch before writing either output.
    for name, value in [('output_flagged.json', full), ('output_flags_only.json', compact)]:
        (input_path.parent / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Created {name}')


if __name__ == '__main__':
    main()
