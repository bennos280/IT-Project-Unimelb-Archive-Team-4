"""Each page type's field rules: what a field should hold (its type, whether it's required, the values or range it may take,
a pattern), saved with its template version; and each series' checks across fields. A page's values that break a rule are flagged
for review (kind 'invalid'), and those that fail a check too (kind 'check')."""
import calendar
import json
import re

TYPES = ("text", "number", "date", "yes_no", "one_of", "several_of", "pattern")
KEYS = {"type", "required", "min", "max", "values", "pattern", "example"}
YES_NO = {"yes", "no", "y", "n", "true", "false", "✓", "✔", "✗", "✘"}
MONTHS = {name.lower(): n for n in range(1, 13) for name in (calendar.month_name[n], calendar.month_abbr[n])} | {"sept": 9}
MONTH = rf"({'|'.join(sorted(MONTHS, key=len, reverse=True))})\.?"
DATES = [  #each to (year, month, day), as far as it goes; a two-digit year is a date whose century isn't known
    (re.compile(r"(\d{4})"), lambda m: (int(m[1]),)),
    (re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})"), lambda m: (int(m[3]) if len(m[3]) == 4 else None, int(m[2]), int(m[1]))),
    (re.compile(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH},?\s+(\d{{4}})", re.I), lambda m: (int(m[3]), MONTHS[m[2].lower()], int(m[1]))),
    (re.compile(rf"{MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", re.I), lambda m: (int(m[3]), MONTHS[m[1].lower()], int(m[2]))),
    (re.compile(rf"{MONTH},?\s+(\d{{4}})", re.I), lambda m: (int(m[2]), MONTHS[m[1].lower()])),
]


def number(text):
    """'1,234' -> 1234.0, 'nil' -> 0.0 (a count of none); None if it isn't a number"""
    text = re.sub(r"(?<=\d)[ ,](?=\d{3}\b)", "", str(text).strip()) if text is not None else ""
    if text.lower() in ("nil", "none", "no", "zero"):
        return 0.0
    return float(text) if re.fullmatch(r"[-+]?(\d+(\.\d*)?|\.\d+)", text) else None


def date(text):
    """'12 March 1917' -> (1917, 3, 12), 'March 1917' -> (1917, 3), '1917' -> (1917,); None if it isn't a date"""
    for pattern, parts in DATES:
        if m := pattern.fullmatch(str(text).strip()):
            found = parts(m)
            if len(found) > 1 and not 1 <= found[1] <= 12:
                return None
            if len(found) > 2 and not 1 <= found[2] <= calendar.monthrange(found[0] or 2000, found[1])[1]:
                return None
            return found
    return None


def _before(a, b):  #a is before b, to the precision both have; a two-digit year can't be compared
    k = min(len(a), len(b))
    return None not in (a[0], b[0]) and a[:k] < b[:k]


def _in(value, entry):
    """value is entry's code (a number code as a number: 1 is 01) or its meaning (after " = "), or in its range of codes (000-996)"""
    code, _, meaning = (part.strip() for part in entry.partition(" = "))
    if value.isdecimal() and (codes := re.fullmatch(r"(\d+)(?:-(\d+))?", code)):
        return int(codes[1]) <= int(value) <= int(codes[2] or codes[1])
    return _plain(value) in (_plain(code), _plain(meaning)) if meaning else _plain(value) == _plain(code)


NESTED_REPEAT = re.compile(r"\([^()]*[+*][^()]*\)[+*{]")  #(a+)+ or (\d*)*: a repeat of a repeat can take forever to fail


def value_problem(rule, raw):
    """Why raw breaks rule, for the reviewer; None if it doesn't. Blank and '/' are empty; '[?]' is flagged as unreadable already."""
    value = (raw or "").strip()
    if value in ("", "/"):
        return "Required, but empty" if rule.get("required") else None
    if "[?]" in value:
        return None
    kind, low, high = rule.get("type", "text"), rule.get("min"), rule.get("max")
    if kind in ("date", "yes_no"):
        value = value.rstrip(".").strip()  #the card's own full stop: "Yes.", "12 March 1917." (a list's values are matched without it)
    if kind == "number":
        if (n := number(value)) is None:
            return "Should be a number"
        if (low is not None and n < number(low)) or (high is not None and n > number(high)):
            return _range(low, high)
    elif kind == "date":
        if (d := date(value)) is None:
            return "Should be a date, like 12 March 1917 or 12/3/1917"
        if (low is not None and _before(d, date(low))) or (high is not None and _before(date(high), d)):
            return _range(low, high)
    elif kind == "yes_no" and value.lower() not in YES_NO:
        return "Should be yes or no"
    elif kind in ("one_of", "several_of"):
        values = rule.get("values") or []
        whole = any(_in(value, entry) for entry in values)  #an allowed value may hold a comma: "Missing, believed killed"
        parts = [p.strip() for p in re.split(r"[,;]", value) if p.strip()] if kind == "several_of" and not whole else [value]
        if wrong := [p for p in parts if not any(_in(p, entry) for entry in values)]:
            shown = ", ".join(entry.partition(" = ")[0] for entry in values[:8]) + (", …" if len(values) > 8 else "")
            return (f"Should be one of: {shown}" if kind == "one_of" else f"“{wrong[0]}” isn't one of: {shown}")
    elif kind == "pattern" and not re.fullmatch(rule["pattern"], value):
        return f"Should look like {rule['example']}" if rule.get("example") else "Doesn't match its pattern"
    return None


def _range(low, high):
    return (f"Should be from {low} to {high}" if low is not None and high is not None
            else f"Should be at least {low}" if low is not None else f"Should be at most {high}")


def fields(template, parent=None):
    """A template's fields that rules can be set on: its leaves, by dotted path (not the residents list or annotations)."""
    for key, value in template.items():
        path = f"{parent}.{key}" if parent else key
        if isinstance(value, dict):
            yield from fields(value, path)
        elif not isinstance(value, list):
            yield path


def rule_problems(rules, template):
    """Why rules can't be saved with template; [] if they can."""
    if not isinstance(rules, dict):
        return ["Rules must be an object of fields"]
    leaves, found = set(fields(template)), []
    for path, rule in rules.items():
        name = f"'{path}'"
        if path not in leaves:
            found.append(f"{name} isn't a field of the template")
            continue
        if not isinstance(rule, dict) or rule.get("type", "text") not in TYPES or set(rule) - KEYS:
            found.append(f"{name}: a rule has a type ({', '.join(TYPES)}) and only {', '.join(sorted(KEYS - {'type'}))}")
            continue
        kind, low, high = rule.get("type", "text"), rule.get("min"), rule.get("max")
        if any(not isinstance(v, (str, int, float, type(None))) or isinstance(v, bool) for v in (low, high)):
            found.append(f"{name}: its range is a number or a date")
            continue
        if "required" in rule and not isinstance(rule["required"], bool):
            found.append(f"{name}: required is true or false")
        if kind in ("number", "date"):
            read = number if kind == "number" else date
            if any(v is not None and read(v) is None for v in (low, high)):
                found.append(f"{name}: its range must be {'numbers' if kind == 'number' else 'dates'}")
            elif low is not None and high is not None and (read(high) < read(low) if kind == "number" else _before(date(high), date(low))):
                found.append(f"{name}: its lowest is above its highest")
        elif low is not None or high is not None:
            found.append(f"{name}: only a number or a date has a range")
        if kind in ("one_of", "several_of"):
            values = rule.get("values")
            if not (isinstance(values, list) and values and all(isinstance(v, str) and v.strip() for v in values)):
                found.append(f"{name}: list the values it may take")
        if kind == "pattern":
            pattern, example = rule.get("pattern"), rule.get("example")
            if not isinstance(pattern, str) or not pattern or not isinstance(example, (str, type(None))):
                found.append(f"{name}: give the pattern (and its example) as text")
                continue
            if NESTED_REPEAT.search(pattern):
                found.append(f"{name}: its pattern repeats a repeat, like (a+)+, which can take forever to check: drop the outer one")
                continue
            try:
                if not re.compile(pattern).fullmatch(example or "") and example:
                    found.append(f"{name}: its example {example} doesn't match its pattern")
            except re.error as error:
                found.append(f"{name}: its pattern isn't valid ({error})")
    return found


#--A SERIES' CHECKS--# rules across fields, of one page or of a record's pages, saved as versions (models.CheckVersion). A check names
#fields as "<page type>.<field path>"; it compares them ({kind: compare, left: [fields], op, right: [fields] or value: text}: several
#fields are added up; op names: the left field is the name its list gives the right field's code) or says that if one is so another
#must be ({kind: if, if: field, is: filled|empty|is, isValue, then: field, must: filled|empty|is, mustValue}); each has an id, may be
#switched off (on: false), and may say its own message. A comparison as codes (as: codes) compares only values that are all digits.
OPS = {"=": "equal", "!=": "differ from", "<": "be less than", "<=": "be at most", ">": "be more than", ">=": "be at least",
       "names": "name"}
STATES = ("filled", "empty", "is")


def refs(check):
    """the fields a check names, each once, in order"""
    named = [*check.get("left", []), *check.get("right", [])] if check.get("kind") == "compare" else [check.get("if"), check.get("then")]
    return list(dict.fromkeys(named))


def check_problems(checks, fields):
    """Why a series' checks can't be saved; [] if they can. fields: each of its page types -> its template's fields"""
    if not isinstance(checks, list):
        return ["Checks must be a list"]
    found, ids = [], set()
    for n, check in enumerate(checks, 1):
        try:
            found += _check_problems(f"Check {n}", check, fields, ids)
        except (TypeError, AttributeError, ValueError):
            found.append(f"Check {n}: isn't written as a check (its fields are lists of names, its values text)")
    return found


def _check_problems(name, check, fields, ids):
    if not isinstance(check, dict) or check.get("kind") not in ("compare", "if"):
        return [f"{name}: compares fields, or says if one field is so another must be"]
    found = []
    if not isinstance(check.get("id"), str) or not check["id"] or check["id"] in ids:
        found.append(f"{name}: needs an id of its own")
    ids.add(check.get("id"))
    if not isinstance(check.get("on", True), bool) or not isinstance(check.get("message", ""), str):
        found.append(f"{name}: on is true or false, and its message is text")
    found += [f"{name}: {ref} isn't a field of this series' page types" for ref in refs(check)
              if not (isinstance(ref, str) and ref.partition(".")[2] in fields.get(ref.partition(".")[0], ()))]
    if check["kind"] == "compare":
        if check.get("op") not in OPS:
            found.append(f"{name}: compares with one of {' '.join(OPS)}")
        if not check.get("left") or not isinstance(check["left"], list):
            found.append(f"{name}: needs a field to compare")
        if bool(check.get("right")) == ("value" in check) or ("value" in check and not str(check["value"]).strip()):
            found.append(f"{name}: compares with fields or with a value")
        elif check.get("op") == "names" and not (len(check.get("left") or []) == len(check.get("right") or []) == 1):
            found.append(f"{name}: names compares one field with one coded field")
        if check.get("as", "values") not in ("values", "codes"):
            found.append(f"{name}: compares as values, or as codes (digits only)")
    else:
        for state, value in (("is", "isValue"), ("must", "mustValue")):
            if check.get(state) not in STATES or (check[state] == "is" and not str(check.get(value, "")).strip()):
                found.append(f"{name}: {state} is filled, empty, or a value")
    return found


def _blank(value):
    return value is None or value.strip() in ("", "/")


def _plain(text):  #"  Mrs. " -> "mrs": words compared without case, extra spaces or a last full stop
    return " ".join(str(text).lower().split()).rstrip(".").strip()


def _unsure(value):  #"17?", "10/", "1/3", "45(1)", two lines: marked as unsure (or crossed out) as transcribed; not "N/A", a date
    text = value.strip()
    return ("?" in text or "\n" in text or bool(re.search(r"\(\s*\d", text))
            or (bool(re.search(r"\d/|/\d", text)) and date(text.rstrip(".")) is None))


def _loose(text):  #"N. Fitzroy" -> "nfitzroy", "03 A" -> "3a", not "1.5" -> "15": as written on another page, up to case, spaces,
    #full stops and commas outside a number, and leading zeros
    text = re.sub(r"\s+", "", re.sub(r"(?<!\d)[.,]|[.,](?!\d)", "", str(text).lower()))
    return re.sub(r"(?<!\d)0+(?=\d)", "", text)


def _label(ref):  #"coded.rooms.total_rooms" -> "Total rooms", as the review screen calls it
    return ref.rpartition(".")[2].replace("_", " ").capitalize()


def check_failure(check, read, values_of=lambda ref: None):
    """Why a check fails, for the reviewer; None if it passes, or can't be told (a value it needs is empty or unreadable, or the
    values can't be compared that way, or one is marked as unsure). read: field -> its value; values_of: field -> its list of values ("code = name"), for names"""
    if check["kind"] == "if":
        given, then = read(check["if"]), read(check["then"])
        if any(value and not _blank(value) and _unsure(value) for value in (given, then)):
            return None

        def holds(value, state, wanted):
            if state == "filled":
                return not _blank(value)
            if state == "empty":
                return _blank(value)
            return not _blank(value) and _plain(value) == _plain(wanted)
        if not holds(given, check["is"], check.get("isValue")) or holds(then, check["must"], check.get("mustValue")):
            return None
        said = {"filled": "is filled", "empty": "is empty", "is": f"is {check.get('isValue')}"}[check["is"]]
        should = {"filled": "be filled", "empty": "be empty", "is": f"be {check.get('mustValue')}"}[check["must"]]
        return check.get("message") or f"{_label(check['if'])} {said}, so {_label(check['then'])} should {should}"
    left, right = [read(r) for r in check["left"]], [read(r) for r in check.get("right") or []] or [str(check.get("value"))]
    read_values = left + (right if check.get("right") else [])  #a check's own value isn't transcribed: it can't be unsure
    if any(_blank(v) for v in left + right) or any(_unsure(v) for v in read_values):  #only what's written plainly is compared
        return None
    op, single = check["op"], len(left) == len(right) == 1
    if op == "names":
        return _misnamed(check, left[0], right[0], values_of(check["right"][0]) or [])
    if check.get("as") == "codes" and not all(v.strip().isdecimal() for v in left + right):  #a code is its digits: 0133, not 013.3
        return None
    numbers = [[number(v) for v in side] for side in (left, right)]
    dates = (date(left[0].strip().rstrip(".")), date(right[0].strip().rstrip("."))) if single else (None, None)  #"12 March 1917."
    if all(n is not None for side in numbers for n in side):
        a, b = round(sum(numbers[0]), 9), round(sum(numbers[1]), 9)  #0.1 + 0.2 is 0.3
    elif None not in dates:  #two dates, to the precision both have; one with a two-digit year can't be told
        if None in (dates[0][0], dates[1][0]):
            return None
        k = min(len(dates[0]), len(dates[1]))
        a, b = dates[0][:k], dates[1][:k]
    elif op in ("=", "!=") and single:
        a, b = _loose(left[0]), _loose(right[0])
    else:
        return None
    if {"=": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]:
        return None
    show = lambda fields, values: f"{' + '.join(map(_label, fields))} ({' + '.join(values)})"
    other = show(check["right"], right) if check.get("right") else right[0]
    return check.get("message") or f"{show(check['left'], left)} should {OPS[op]} {other}"


def _misnamed(check, name, code, entries):
    """Why name isn't what its list calls code; None if it is, or can't be told: the code isn't listed or means not known, or the
    name isn't one the list gives (a suburb coded as its council)"""
    names = {_loose(meaning): meaning for _, _, meaning in (e.partition(" = ") for e in entries) if meaning}
    meaning = next((m.strip() for c, _, m in (e.partition(" = ") for e in entries)
                    if m and (int(c) == int(code) if c.strip().isdecimal() and code.strip().isdecimal() else _plain(c) == _plain(code))), None)
    if meaning is None or _plain(meaning) in ("not known", "not applicable") or _loose(name) not in names or _loose(name) == _loose(meaning):
        return None
    return check.get("message") or (f"{_label(check['left'][0])} ({name}) should name {_label(check['right'][0])} {code} ({meaning})")


def check_pages(con, page_ids):
    """Flags what breaks its page type's newest rules (kind invalid) and what fails its series' newest checks (kind check) on these
    pages and the rest of their records, replacing the last check's flags there. A check across page types needs one page of each in
    the record. Values are as reviewers last saved them; a page waiting to be read again isn't checked."""
    rules = {kind: json.loads(body) for kind, body in con.exec_driver_sql(
        "SELECT kind, rules FROM instruction_versions v WHERE rules IS NOT NULL"
        " AND version_id = (SELECT MAX(version_id) FROM instruction_versions WHERE kind = v.kind)")}
    series_checks = {series: [c for c in json.loads(body) if c.get("on", True)] for series, body in con.exec_driver_sql(
        "SELECT collection_id, body FROM check_versions v"
        " WHERE version_id = (SELECT MAX(version_id) FROM check_versions WHERE collection_id = v.collection_id)")}
    for start in range(0, len(page_ids), 400):
        chunk = list(page_ids[start:start + 400])
        marks = ", ".join("?" * len(chunk))
        found = con.exec_driver_sql(
            "SELECT p.page_id, p.category, p.survey_id, b.collection_id, p.needs_transcription FROM pages p JOIN bundles b"
            f" ON b.bundle_id = p.bundle_id WHERE p.page_id IN ({marks})"
            f" OR p.survey_id IN (SELECT survey_id FROM pages WHERE page_id IN ({marks}))", tuple(chunk) * 2).fetchall()
        if not found:
            continue
        marks = ", ".join("?" * len(found))
        con.exec_driver_sql(f"DELETE FROM flags WHERE kind IN ('invalid', 'check') AND page_id IN ({marks})", tuple(p[0] for p in found))
        pages = {page: (category, survey or page, series) for page, category, survey, series, unread in found if not unread}
        marks = ", ".join("?" * len(pages))
        values = {page: {} for page in pages}
        for page, field, raw in con.exec_driver_sql(  #rules are on fields outside lists
                f"SELECT page_id, field_title, text_raw FROM fields WHERE list_name = '' AND page_id IN ({marks})", tuple(pages)):
            values[page][field] = raw
        for page, field, edit in con.exec_driver_sql(  #each field's newest saved edit (ix_edits_page_field)
                "SELECT e.page_id, e.field_title, e.edit_text FROM edits e JOIN (SELECT MAX(edit_id) AS newest FROM edits"
                f" WHERE list_name = '' AND field_title IS NOT NULL AND page_id IN ({marks}) GROUP BY page_id, field_title) n"
                " ON e.edit_id = n.newest", tuple(pages)):
            if field in values[page]:
                values[page][field] = edit
        flags = set()
        for page, (category, _, _) in pages.items():
            for path, rule in (rules.get(category) or {}).items():
                if path in values[page] and (problem := value_problem(rule, values[page][path])):
                    flags.add((page, path, "invalid", problem))
        records = {}
        for page, (category, record, series) in pages.items():
            records.setdefault((series, record), {}).setdefault(category, []).append(page)
        for (series, _), by_type in records.items():
            for check in series_checks.get(series, []):
                named = refs(check)
                types = {ref.partition(".")[0] for ref in named}
                if len(types) == 1:
                    groups = [{next(iter(types)): page} for page in by_type.get(next(iter(types)), [])]
                else:
                    groups = [{t: by_type[t][0] for t in types}] if all(len(by_type.get(t, [])) == 1 for t in types) else []
                for group in groups:
                    page_of = lambda ref: group[ref.partition(".")[0]]
                    if reason := check_failure(check, lambda ref: values[page_of(ref)].get(ref.partition(".")[2]),
                                               lambda ref: (rules.get(ref.partition(".")[0]) or {}).get(ref.partition(".")[2], {}).get("values")):
                        flags |= {(page_of(ref), ref.partition(".")[2], "check", reason) for ref in named
                                  if ref.partition(".")[2] in values[page_of(ref)]}
        for flag in sorted(flags):
            con.exec_driver_sql("INSERT INTO flags(page_id, field_title, kind, reason) VALUES(?, ?, ?, ?)", flag)
