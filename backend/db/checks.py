"""Each page type's field rules: what a field should hold (its type, whether it's required, the values or range it may take,
a pattern), saved with its template version. A page's values that break a rule are flagged
for review (kind 'invalid')."""
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


def _plain(text):  #"  Mrs. " -> "mrs": words compared without case, extra spaces or a last full stop
    return " ".join(str(text).lower().split()).rstrip(".").strip()


def check_pages(con, page_ids):
    """Flags what breaks its page type's newest rules (kind invalid) on these
    pages and the rest of their records, replacing the last check's flags there; a page waiting to be read again isn't checked."""
    rules = {kind: json.loads(body) for kind, body in con.exec_driver_sql(
        "SELECT kind, rules FROM instruction_versions v WHERE rules IS NOT NULL"
        " AND version_id = (SELECT MAX(version_id) FROM instruction_versions WHERE kind = v.kind)")}
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
        con.exec_driver_sql(f"DELETE FROM flags WHERE kind IN ('invalid') AND page_id IN ({marks})", tuple(p[0] for p in found))
        pages = {page: (category, survey or page, series) for page, category, survey, series, unread in found if not unread}
        marks = ", ".join("?" * len(pages))
        values = {page: {} for page in pages}
        for page, field, raw in con.exec_driver_sql(f"SELECT page_id, field_title, text_raw FROM fields WHERE page_id IN ({marks})",
                                                    tuple(pages)):
            values[page][field] = raw
        flags = set()
        for page, (category, _, _) in pages.items():
            for path, rule in (rules.get(category) or {}).items():
                if path in values[page] and (problem := value_problem(rule, values[page][path])):
                    flags.add((page, path, "invalid", problem))
        for flag in sorted(flags):
            con.exec_driver_sql("INSERT INTO flags(page_id, field_title, kind, reason) VALUES(?, ?, ?, ?)", flag)
