"""Each page type's field rules: what a field should hold (its type, whether it's required, the values or range it may take,
a pattern), saved with its template version; a page's values that break them are flagged for review (kind 'invalid')."""
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
    """'1,234' -> 1234.0; None if it isn't a number"""
    text = re.sub(r"(?<=\d)[ ,](?=\d{3}\b)", "", str(text).strip()) if text is not None else ""
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


def _in(value, entry):  #value is entry's code (or its meaning, after " = "), or in its range of codes ("000-996")
    code, _, meaning = entry.partition(" = ")
    if (low := re.fullmatch(r"(\d+)-(\d+)", code.strip())) and value.isdigit():
        return int(low[1]) <= int(value) <= int(low[2])
    plain = lambda text: " ".join(text.lower().split())
    return plain(value) in (plain(code), plain(meaning)) if meaning else plain(value) == plain(code)


def value_problem(rule, raw):
    """Why raw breaks rule, for the reviewer; None if it doesn't. Blank and '/' are empty; '[?]' is flagged as unreadable already."""
    value = (raw or "").strip()
    if value in ("", "/"):
        return "Required, but empty" if rule.get("required") else None
    if "[?]" in value:
        return None
    kind, low, high = rule.get("type", "text"), rule.get("min"), rule.get("max")
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
        parts = [p.strip() for p in re.split(r"[,;]", value) if p.strip()] if kind == "several_of" else [value]
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
            try:
                compiled = re.compile(rule.get("pattern") or "")
                if not rule.get("pattern"):
                    found.append(f"{name}: give the pattern")
                elif rule.get("example") and not compiled.fullmatch(rule["example"]):
                    found.append(f"{name}: its example {rule['example']} doesn't match its pattern")
            except re.error as error:
                found.append(f"{name}: its pattern isn't valid ({error})")
    return found


def check_pages(con, page_ids):
    """Flags each page's fields that break its page type's newest rules (kind 'invalid'), replacing the flags of the last check."""
    rules = {kind: json.loads(body) for kind, body in con.exec_driver_sql(
        "SELECT kind, rules FROM instruction_versions v WHERE rules IS NOT NULL"
        " AND version_id = (SELECT MAX(version_id) FROM instruction_versions WHERE kind = v.kind)")}
    for page_id in page_ids:
        con.exec_driver_sql("DELETE FROM flags WHERE page_id = ? AND kind = 'invalid'", (page_id,))
        category = con.exec_driver_sql("SELECT category FROM pages WHERE page_id = ?", (page_id,)).scalar()
        if not rules.get(category):
            continue
        values = dict(con.exec_driver_sql("SELECT field_title, text_raw FROM fields WHERE page_id = ?", (page_id,)).fetchall())
        for path, rule in rules[category].items():
            if path in values and (problem := value_problem(rule, values[path])):
                con.exec_driver_sql("INSERT INTO flags(page_id, field_title, kind, reason) VALUES(?, ?, 'invalid', ?)",
                                    (page_id, path, problem))
