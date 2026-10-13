"""US6: evidence-based consistency checks between a survey's main form (page 1) and coded card (page 3).
No transcription is corrected."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:years?\.?|yrs?\.?|y\.?)?', text)
    return Decimal(match[1]) if match else None


def _relationship(value: Any) -> tuple[str | None, str | None]:
    """Recognize exact relationships with an optional explicit sex suffix.

    A full match avoids treating 'head boarder' or 'headache' as a Head.
    Annotated relationships also count in boarder and child comparisons.
    """
    text = _text(value)
    if text is None:
        return None, None
    match = re.fullmatch(r'(head|h\.?|son|daughter|wife|husband|father|mother|brother|sister|boarder|lodger)\s*(?:\(\s*(m|f|male|female)\s*\))?', text)
    if not match:
        return text, None
    relation, annotation = match.groups()
    if relation in ('h', 'h.'):
        relation = 'head'
    gender = annotation[0].upper() if annotation else None
    return relation, gender


def _room_bounds(value: Any):
    """Room codes 1-11 are exact; 0 is the codebook's over-11 bucket."""
    count = _count(value)
    if count is None or count > 11:
        return None
    return (Decimal(12), None) if count == 0 else (count, count)


def _has_content(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_content(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_content(v) for v in value)
    return not _blank(value)


@dataclass(frozen=True)
class Ref:
    path: PathTuple
    value: Any


# a resident's own cells; the rest of the column is about their work
PERSON = ('relationship', 'age', 'sex', 'gender', 'earning_status')


def find_issues(survey: dict[str, Any]) -> list[dict[str, Any]]:
    """survey: {'main': page 1 reading, 'coded': page 3 reading}. Each issue lists its fields' paths,
    e.g. ('coded', 'number_of_bedrooms')."""
    for page in ('main', 'coded'):
        if not isinstance(survey.get(page), dict):
            raise ValueError(f'{page} must be a page reading (a JSON object); both pages are required')
    # every coded card's template has it: a reading without it isn't a coded card (an empty or garbled reading, another format)
    if 'number_of_dwelling' not in survey['coded']:
        raise ValueError('coded has no number_of_dwelling: not a coded card reading')
    m = lambda *parts: Ref(('main', *parts), _get(survey['main'], parts))
    c = lambda *parts: Ref(('coded', *parts), _get(survey['coded'], parts))
    issues: list[dict[str, Any]] = []

    def issue(kind: str, reason: str, refs: list[Ref], derived: str | None = None) -> None:
        item = {'type': kind, 'reason': reason, 'fields': list(dict.fromkeys(ref.path for ref in refs))}
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

    compare(m('number_of_dwelling'), c('number_of_dwelling'), 'NUMBER OF DWELLING', _dwelling)
    compare(m('rooms', 'rooms_not_in_daily_use'), c('rooms_not_in_daily_use'), 'ROOMS NOT IN DAILY USE')
    for source, target, name in [('industry_of_head_code', 'industry_of_head', 'INDUSTRY OF HEAD CODE'),
                                 ('occupation_of_head_code', 'occupation_of_head', 'OCCUPATION OF HEAD CODE')]:
        # Only explicit handwritten codes, never the occupation/industry prose.
        if m(source).value is not MISSING:
            compare(m(source), c(target), name, _code)
    for source, target, name in [('number_of_separate_bedrooms', 'number_of_bedrooms', 'NUMBER OF BEDROOMS'),
                                 ('number_of_living_rooms', 'number_of_living_rooms', 'NUMBER OF LIVING ROOMS')]:
        left, right = m('rooms', source), c(target)
        if _blank(left.value) and _blank(right.value):
            continue
        count, bounds = _count(left.value), _room_bounds(right.value)
        if count is None or bounds is None:
            issue('Page 1–3 comparison incomplete', f'{name}: a corresponding room count/code is missing or cannot be interpreted.', [left, right])
        elif count < bounds[0] or (bounds[1] is not None and count > bounds[1]):
            issue('Page 1–3 conflict', f'{name}: the Page 1 count contradicts the coded room count/bucket.', [left, right], 'Page 3 codes 1–11 are exact counts; code 0 means over 11.')

    left, right = m('rooms', 'number_of_sleepouts'), c('number_of_sleepouts')
    if not (_blank(left.value) and _blank(right.value)):
        count, code = _count(left.value), _count(right.value)
        named_type = {'verandah': 1, 'balcony': 2, 'outhouse': 3}.get(_text(left.value))
        if code is None or code not in (0, 1, 2, 3, 4) or (count is None and named_type is None):
            issue('Page 1–3 comparison incomplete', 'Sleepouts: a corresponding count/type or coded category is missing or cannot be interpreted.', [left, right])
        else:
            allowed = {named_type} if named_type is not None else ({0} if count == 0 else {1, 2, 3} if count == 1 else {4})
            if code not in allowed:
                issue('Page 1–3 conflict', 'Sleepouts: the Page 1 count/type contradicts the Page 3 category.', [left, right], 'Count 0 -> code 0; count 1 -> code 1/2/3; count >=2 -> code 4. Explicit types restrict the matching code.')

    residence, residence_code = m('length_of_residence'), c('length_of_residence')
    code = _count(residence_code.value)
    if code == 99:
        pass  # Valid unknown/vague code; not an exact 99-year duration.
    elif code == 0 and not _blank(residence.value):
        years = _years(residence.value)
        if years is None:
            issue('Page 1–3 comparison incomplete', 'Length of residence: the Page 1 duration cannot be compared with the under-one-year code.', [residence, residence_code])
        elif years >= 1:
            issue('Page 1–3 conflict', 'Length of residence: Page 3 says under one year but Page 1 records at least one year.', [residence, residence_code])
    else:
        compare(residence, residence_code, 'Length of residence', _years)

    rows = m('residents').value
    if not _blank(rows) and not isinstance(rows, list):
        raise ValueError('main.residents must be a list or null')
    if isinstance(rows, list) and any(not isinstance(r, dict) for r in rows):
        raise ValueError('Every main.residents entry must be an object')
    # A blank template's empty columns mean the residents are unknown, not zero residents.
    known = isinstance(rows, list) and any(_has_content({k: r.get(k) for k in ('relationship', 'age', 'earning_status')}) for r in rows)
    table = Ref(('main', 'residents'), rows if known else (MISSING if rows is MISSING else None))
    people = [(i, r) for i, r in enumerate(rows) if _has_content({k: r.get(k) for k in PERSON})] if known else []
    total = c('total_number_resident_members')

    def derived_compare(target: Ref, value: int | None, refs: list[Ref], name: str, explanation: str) -> None:
        if value is None and _blank(target.value) and all(_blank(r.value) for r in refs):
            return
        tv = _count(target.value)
        if value is None or tv is None:
            issue('Page 1–3 comparison incomplete', f'{name}: the corresponding source data or coded count is missing or insufficient to compute an exact count.', refs + [target], explanation)
        elif value != tv:
            issue('Page 1–3 conflict', f'{name}: Page 1 derives {value}, but Page 3 records {target.value}.', refs + [target], explanation)

    derived_compare(total, len(people) if known else None, [table], 'Resident total', 'Count residents with anything written; empty template columns are ignored.')
    age_refs = [m('residents', i, 'age') for i, _ in people]
    ages = [_count(r.value) for r in age_refs]
    complete_ages = known and all(v is not None for v in ages)
    for name, field, predicate in [('NUMBER UNDER 5', 'number_under_5', lambda n: n < 5), ('NUMBER 5-10', 'number_5_to_10', lambda n: 5 <= n <= 10),
                                   ('CHILDREN UNDER 14', 'children_under_14', lambda n: n < 14)]:
        value = sum(predicate(v) for v in ages) if complete_ages else None
        derived_compare(c(field), value, age_refs or [table], name, f'Count resident ages using {name}; 5–10 includes ages 5 and 10; under 14 excludes 14.')

    def sex(person: dict) -> str | None:
        explicit = _text(person.get('sex')) or _text(person.get('gender'))
        if explicit in ('m', 'male'):
            return 'M'
        if explicit in ('f', 'female'):
            return 'F'
        rel, annotation = _relationship(person.get('relationship'))
        if annotation is not None:
            return annotation
        if rel in ('son', 'husband', 'father', 'brother'):
            return 'M'
        if rel in ('daughter', 'wife', 'mother', 'sister'):
            return 'F'
        return None  # Head, boarder and names do not establish sex.

    sex_refs = [m('residents', i, 'relationship') for i, _ in people]
    sex_refs += [m('residents', i, key) for i, p in people for key in ('sex', 'gender') if key in p]
    older = [(i, p, age) for (i, p), age in zip(people, ages) if age is not None and age > 10]
    gender_targets = [c('number_over_10_male'), c('number_over_10_female')]
    if complete_ages:
        unknown = sum(sex(p) is None for _, p, _ in older)
        for gender, target in zip(('M', 'F'), gender_targets):
            minimum = sum(sex(p) == gender for _, p, _ in older)
            maximum = minimum + unknown
            recorded = _count(target.value)
            refs = age_refs + sex_refs or [table]
            if recorded is None:
                derived_compare(target, None, refs, f'Residents over 10 ({gender})', 'The coded count is missing or cannot be interpreted.')
            elif recorded < minimum or recorded > maximum:
                issue('Page 1–3 conflict', f'Residents over 10 ({gender}): the coded count is outside the range supported by Page 1.', refs + [target], f'{minimum} <= OVER 10 {gender} <= {maximum}; unknown sex is not guessed.')
        counts = [_count(target.value) for target in gender_targets]
        if all(count is not None for count in counts) and sum(counts) != len(older):
            issue('Page 1–3 conflict', 'Residents over 10: coded male plus female counts differ from the Page 1 age-derived total.', age_refs + gender_targets, f'OVER 10 M + OVER 10 F = {len(older)}')
    else:
        for gender, target in zip(('M', 'F'), gender_targets):
            derived_compare(target, None, age_refs + sex_refs or [table], f'Residents over 10 ({gender})', 'Missing source ages prevent establishing an age-group range.')

    heads = [(i, p) for i, p in people if _relationship(p.get('relationship'))[0] == 'head']
    if _count(c('age_of_head').value) == 0:
        pass  # 00 means not known, not an age of zero.
    elif len(heads) == 1:
        i, _ = heads[0]
        compare(m('residents', i, 'age'), c('age_of_head'), 'Age of head')
    elif heads or not _blank(c('age_of_head').value):
        issue('Page 1–3 comparison incomplete', 'Age of head: Page 1 does not identify exactly one Head; no person is selected by position.', [m('residents', i, 'relationship') for i, _ in people] + [c('age_of_head')])

    # Derive boarder counts only with a complete relationship column.
    rels = [_relationship(p.get('relationship'))[0] for _, p in people]
    boarders = sum(r in ('boarder', 'lodger') for r in rels) if known and all(r is not None for r in rels) else None
    derived_compare(c('number_of_boarders'), boarders, sex_refs or [table], 'Boarders', 'Count explicit Boarder/Lodger relationships; no inference from income.')

    child = lambda key: c(f'children_of_head_or_wife_{key}')
    relation([child('living'), child('dead'), child('total')], 'Children living plus dead must equal children total.', lambda v: v[0] + v[1] == v[2], 'LIVING + DEAD = TOTAL')
    bands = [c('number_under_5'), c('number_5_to_10'), *gender_targets]
    relation(bands + [total], 'Resident age bands must add to resident total.', lambda v: sum(v[:-1]) == v[-1], 'UNDER 5 + 5–10 + OVER 10 M + OVER 10 F = TOTAL RESIDENTS')
    bread = [c('number_of_adult_male_breadwinners'), c('number_of_adult_female_breadwinners'), c('number_of_juvenile_breadwinners_under_21')]
    relation(bread + [total], 'Breadwinner categories cannot exceed residents.', lambda v: sum(v[:-1]) <= v[-1], 'ADULT M + ADULT F + JUVENILE BREADWINNERS <= TOTAL RESIDENTS')
    for name, field in [('NO. OF BOARDERS', 'number_of_boarders'), ('NO. OF PARTICIPATING MEMBERS', 'number_of_participating_members'),
                        ('CHILDREN UNDER 14', 'children_under_14'), ('PERSONS SHARING', 'persons_sharing'),
                        ('RETIRED AND INDEP. PERSONS', 'retired_and_independent_persons'), ('HOME DUTIES', 'home_duties')]:
        relation([c(field), total], f'{name} cannot exceed residents.', lambda v: v[0] <= v[1], f'{name} <= TOTAL RESIDENTS')
    # Age subgroups overlap: under-14 includes all under-5 and 5–10 residents.
    relation(bands[:2] + [c('children_under_14')], 'Children under 14 cannot be fewer than residents aged 10 or younger.', lambda v: v[0] + v[1] <= v[2], 'UNDER 5 + 5–10 <= CHILDREN UNDER 14')
    rooms = c('total_number_of_rooms')

    def room_relation(refs, name, add=False):
        if all(_blank(ref.value) for ref in refs):
            return
        ranges = [_room_bounds(ref.value) if ref.path[-1] != 'rooms_not_in_daily_use' else ((_count(ref.value), _count(ref.value)) if _count(ref.value) is not None else None) for ref in refs]
        if any(bounds is None for bounds in ranges):
            issue('Page 3 comparison incomplete', name + ': a required room count/code is missing or cannot be interpreted.', refs)
            return
        lower = sum(bounds[0] for bounds in ranges[:-1]) if add else ranges[0][0]
        total_upper = ranges[-1][1]
        if total_upper is not None and lower > total_upper:
            issue('Page 3 internal conflict', name, refs, 'Use exact room counts or the over-11 lower bound; flag only a definite contradiction.')

    for name, field in [('NUMBER OF BEDROOMS', 'number_of_bedrooms'), ('NUMBER OF LIVING ROOMS', 'number_of_living_rooms'),
                        ('ROOMS NOT IN DAILY USE', 'rooms_not_in_daily_use')]:
        room_relation([c(field), rooms], f'{name} cannot exceed total rooms.')
    room_relation([c('number_of_bedrooms'), c('number_of_living_rooms'), rooms], 'Separate bedrooms plus living rooms cannot exceed total rooms.', add=True)
    # rooms_shared is a facility-sharing category, never a room count.

    # Main-page relationships: rooms not in use are not an extra room category.
    s, n = m('rooms', 'state_if_used_as_bedrooms'), m('rooms', 'number_of_living_rooms')
    if _text(s.value) in ('yes', 'y', 'y.') and _count(n.value) == 0:
        issue('Page 1 internal conflict', 'Living rooms are said to be used as bedrooms, but the living-room count is zero.', [s, n])
    elif _text(s.value) in ('yes', 'y', 'y.') and _count(n.value) is None:
        issue('Page 1 comparison incomplete', 'Living rooms used as bedrooms: the living-room count is missing or cannot be interpreted.', [s, n])

    # Child relationship establishes a lower bound, not a full parentage count.
    resident_children = [m('residents', i, 'relationship') for i, p in people if _relationship(p.get('relationship'))[0] in ('son', 'daughter')]
    if resident_children:
        living = _count(child('living').value)
        if living is None:
            issue('Page 1–3 comparison incomplete', 'Resident sons/daughters require a comparable living-children count.', resident_children + [child('living')])
        elif len(resident_children) > living:
            issue('Page 1–3 conflict', 'Page 1 resident sons/daughters exceed Page 3 living children.', resident_children + [child('living')], f'Resident sons/daughters ({len(resident_children)}) <= LIVING')
    elsewhere_ref = c('children_other_than_those_at_home')
    relation([elsewhere_ref, child('living')], 'Children living elsewhere cannot exceed living children.', lambda v: v[0] <= v[1], 'CHILDREN OTHER THAN THOSE AT HOME <= LIVING')
    if resident_children and not _blank(elsewhere_ref.value):
        elsewhere = _count(elsewhere_ref.value)
        living = _count(child('living').value)
        refs = resident_children + [elsewhere_ref, child('living')]
        if elsewhere is not None and living is not None and len(resident_children) + elsewhere > living:
            issue('Page 1–3 conflict', 'Resident children plus children elsewhere exceed living children.', refs, f'{len(resident_children)} resident sons/daughters + elsewhere <= LIVING')
    # main.other_children holds raw text lists: no counts are guessed from them.
    # A probable-age interval can validate membership without equality.
    probable, house_age = m('probable_age'), c('age_of_house')
    raw = _text(probable.value)
    special_house_age = _count(house_age.value)
    if special_house_age in (0, 98):
        pass  # No indication / old with no exact age, not numeric zero/98.
    elif special_house_age == 99:
        bound = re.fullmatch(r'(over|more than)\s+(\d+(?:\.\d+)?)\s*(?:years?\.?|yrs?\.?)?', raw or '')
        if bound and Decimal(bound[2]) <= 99:
            pass
        elif _years(probable.value) is not None and _years(probable.value) <= 99:
            issue('Page 1–3 conflict', 'Age of house: the exact Page 1 age contradicts the over-99 coded bucket.', [probable, house_age], 'Page 3 code 99 means age >99, not age exactly 99.')
        elif raw:
            interval = re.fullmatch(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(?:years?\.?|yrs?\.?)?', raw)
            upper = re.fullmatch(r'(under|less than)\s+(\d+(?:\.\d+)?)\s*(?:years?\.?|yrs?\.?)?', raw)
            if (interval and Decimal(interval[2]) <= 99) or (upper and Decimal(upper[2]) <= 99):
                issue('Page 1–3 conflict', 'Age of house: the Page 1 age bound contradicts the over-99 coded bucket.', [probable, house_age])
        # Otherwise the bucket overlaps the source or supplies no exact comparison.
    elif raw and _blank(house_age.value):
        issue('Page 1–3 comparison incomplete', 'Age of house: the corresponding coded age is missing.', [probable, house_age])
    elif raw:
        interval = re.fullmatch(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(?:years?\.?|yrs?\.?)?', raw)
        exact = _years(probable.value)
        if interval or exact is not None:
            low, high = (Decimal(interval[1]), Decimal(interval[2])) if interval else (exact, exact)
            age = _years(house_age.value)
            if age is None:
                issue('Page 1–3 comparison incomplete', 'Age of house: the corresponding coded age is missing or cannot be interpreted.', [probable, house_age])
            elif not low <= age <= high:
                issue('Page 1–3 conflict', 'Coded age of house is outside the Page 1 probable-age interval.', [probable, house_age], f'{low} <= AGE OF HOUSE <= {high}')
        else:
            bound = re.fullmatch(r'(over|under|more than|less than)\s+(\d+(?:\.\d+)?)\s*(?:years?\.?|yrs?\.?)?', raw)
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
