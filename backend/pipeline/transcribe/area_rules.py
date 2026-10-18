"""The area (areas.py) and, on a residents table, the row band an annotation's free-text location names."""
import re
from functools import cache

from . import areas

CENTRE = r"(?:centre|center|middle)(?! column)"
#a bottom position beside the centre ("bottom left-centre", "bottom, right of centre") is that bottom corner's area
BESIDE_CENTRE = [(rf"bottom[-, ]+(?:left(?:[- ]of)?[- ]{CENTRE}|{CENTRE}[- ]left(?! of))", "bottom_left"),
                 (rf"bottom[-, ]+(?:right(?:[- ]of)?[- ]{CENTRE}|{CENTRE}[- ]right(?! of))", "bottom_right")]
#position words: the earliest one in the text wins, a tie goes to the first listed; (pattern, area) per page type
POSITIONS = {
    "main": [*BESIDE_CENTRE, (rf"bottom[- ]{CENTRE}", "bottom_centre"), (rf"(?:top|upper)[- ]{CENTRE}", "header"),
             (r"(?:top|upper)[- ]left", "top_left_corner"), (r"(?:top|upper)[- ]right", "top_right_corner"),
             (r"bottom[- ]left", "bottom_left"), (r"bottom[- ]right", "bottom_right"),
             (r"right[- ](?:margin|edge)", "right_margin"), (r"left[- ](?:margin|edge)", "left_margin")],
    "coded": [*BESIDE_CENTRE, (rf"bottom[- ]{CENTRE}", "bottom_centre"), (rf"(?:top|upper)[- ]{CENTRE}", "middle_column"),
              (r"(?:top|upper)[- ]left", "top_left_corner"), (r"(?:top|upper)[- ]right", "top_right_corner"),
              (r"bottom[- ]left", "bottom_left"), (r"bottom[- ]right", "bottom_right"),
              (r"right[- ](?:margin|edge)", "right_column"), (r"left[- ](?:margin|edge)", "left_margin")],
}

#the main card's right panel (codes and sums beside the residents table); position words after it are within the panel; "top right box" is the date box
RIGHT_PANEL = re.compile(r"\bright(?:-hand)?(?: side)? panel\b|(?<!top )(?<!top-)(?<!upper )\bright box\b")
#a position (or "corner") followed by "of <something>" is relative to that thing, except "of centre" and "of the page"; margins stay absolute
RELATIVE = re.compile(rf"(?:\s+corner)?\s+of\b(?!\s+(?:the\s+)?(?:{CENTRE}|(?:page|card|form|sheet|scan|image)\b))")

BESIDE = "below|under|beneath|beside|near|next to|above|after|right of|left of"
OTHER = r"'?other'?(?=\s*(?:$|[,;(])|\s+(?:value|line|row|box|label|column|field|entry)\b)"  #not "other marks"
#field words, in order; the first area with a match wins
FIELDS = {
    "main": [
        ("top_left_corner", r"dwelling n(?:o|umber)"),
        ("header", r"archive|header|title|universit"),
        ("top_right_corner", r"date of interview|investigator|signature"),
        ("address_block", r"municipality|address|famil(?:y|ies)"),
        ("dwelling_block", r"type of dwelling|structural|storeys?|probable age|\byard|garden|fruit|commercial"),
        ("tenure_block", r"tenure|\brent|furnished|length of residence"),
        ("right_margin", r"\bcodes?\b|industry code|occupation code"),
        ("kitchen_block", r"kitchen|cooking|\bsink|food storage|h\.?w\.?s\b"),
        ("rooms_block", r"bedroom|living room|sleepout|\brooms?\b|\bbath|\bw\.?c\b|\bwash"),
        ("residents_table", r"residents? (?:panel|table|section|block)"),
    ],
    "coded": [
        ("left_column", r"left column|household|famil(?:y|ies)|members|under 5|breadwinner|boarders|military|retired|home duties"),
        ("middle_column", rf"(?:middle|centre|center) column|income|\brent|earnings|occupation|industry|place of work|age of head|tenure|repair|garden|removal"),
        ("right_column", r"right column|total number of rooms|bedrooms|living rooms|daily use"),
        #"Other", the last left column line, is also an everyday word: only after a preposition; below it is the bottom-left
        ("bottom_left", rf"\bbottom\b.*\b(?:{BESIDE}) {OTHER}|\b(?:below|under|beneath) {OTHER}"),
        ("left_column", rf"\b(?:{BESIDE}) {OTHER}"),
    ],
}

#residents table rows of the main form (y0, y1); a row is looked for in this order and its words are used up, so the
#longer name wins ("employer's address" before "employer", "payments to relatives living elsewhere" before "living elsewhere")
ROWS = [
    ("payments to relatives", r"payments?(?: to rel(?:atives?)?\.?)?(?: living elsewhere)?", .802, .843),
    ("employer's address", r"employer'?s? address", .612, .646),
    ("pre-war occupation", r"pre[- ]?war occupation(?!al)", .839, .882),
    ("occupational pref", r"occupational pref(?:erence)?", .943, .979),
    ("normal weekly earnings", r"(?:pre[- ]?war )?norm(?:al|\.)? (?:weekly|wkly\.?) earn\w*(?:'s)?", .876, .905),
    ("place of work", r"(?:pre[- ]?war )?place of work", .9, .952),
    ("earnings last week", r"earnings last week", .696, .731),
    ("full-time earnings", r"full[- ]time earnings", .729, .771),
    ("residential pref", r"residential pref(?:erence)?", .67, .698),
    ("living elsewhere", r"living elsewhere", .406, .442),
    ("earning status", r"earning status", .352, .387),
    ("weekly amount", r"weekly amount", .438, .473),
    ("source", r"\bsource", .469, .5),
    ("unearned income", r"unearned income", .438, .5),  #both rows, unless the amount or the source is named
    ("relationship", r"relationship", .292, .324),
    ("age", r"(?<!probable )\bage\b(?! \d)", .322, .357),
    ("died", r"\bdied\b", .378, .413),
    ("industry", r"industry(?! code)", .495, .531),
    ("craft", r"\bcraft", .524, .557),
    ("regularity", r"regularity", .554, .587),
    ("employer", r"\bemployer", .585, .617),
    ("transport", r"transport", .641, .672),
    ("board", r"\bboard\b", .771, .802),
]
COLUMNS = {1: (.169, .262), 2: (.255, .348), 3: (.342, .432), 4: (.427, .518), 5: (.515, .609)}
#"column 3", "columns 2-3", "col 3", "third column"; a number above 5 is past the last box
COLUMN = re.compile(r"\bcol(?:umns?)?\b\.?\s*(\d)(?!\d)(?:\s*(?:-|to|and|&|/|,)\s*(\d)(?!\d))?")
ORDINAL = re.compile(r"\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)(?: resident)? column\b")
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5}
HEAD_COLUMN = re.compile(r"\bhead(?:'s)? column\b(?! ?\d)")  #the head is column 1; "head column 1943" is a year
LABELS_AND_COLUMNS = (.04, .61)


def residents(text):
    """(True, region) if the text names a residents row or a column; the region is None when no row is named."""
    bands = []
    for name, pattern, y0, y1 in ROWS:
        if name == "unearned income" and any(n in ("weekly amount", "source") for n, _, _ in bands):
            text = re.sub(pattern, " ", text)
            continue
        found = re.search(pattern, text)
        if name == "age" and "dwelling" in text:  #the age of the dwelling
            continue
        if found:
            bands.append((name, y0, y1))
            text = text[:found.start()] + " " * (found.end() - found.start()) + text[found.end():]
    column, ordinal, head = COLUMN.search(text), ORDINAL.search(text), HEAD_COLUMN.search(text)
    if not bands and not column and not ordinal and not head and not re.search(r"column 19[0-9][0-9]", text):  #a resident's 1941/1943 column
        return False, None
    if not bands:
        return True, None
    x0, x1 = LABELS_AND_COLUMNS
    numbers = [int(n) for n in column.groups() if n] if column else [ORDINALS[ordinal.group(1)]] if ordinal else [1] if head else []
    numbers = [n for n in numbers if n > 0]
    if numbers and min(numbers) <= 5:
        x0, x1 = COLUMNS[min(numbers)][0], COLUMNS[min(max(numbers), 5)][1]
    y0, y1 = min(b[1] for b in bands), max(b[2] for b in bands)
    return True, {"x": round(x0, 4), "y": round(y0, 4), "width": round(x1 - x0, 4), "height": round(y1 - y0, 4)}


#printed-label matching: punctuation goes, card abbreviations are spelt out, "label"/"value"/"line"/"box"/"row" are dropped
ABBREVIATIONS = {"no": "number", "wkly": "weekly", "i": "income", "h": "head", "occup": "occupation", "indep": "independent",
                 "m": "male", "f": "female", "hws": "hot water service"}
SUFFIXES = {"label", "value", "line", "box", "row", "labels", "values", "lines", "boxes", "rows"}
TOO_GENERIC = {"number", "other"}  #labels that are also everyday words


def norm(text):
    """text in lower case, as words, for matching printed labels."""
    words = re.sub(r"[^a-z0-9]+", " ", text.lower().replace("’", "'").replace(".", "").replace("'", "")).split()
    return " ".join(ABBREVIATIONS.get(w, w) for w in words if w not in SUFFIXES)


@cache
def labels(page_type):
    """[(normalised printed label, area)], longest first; the residents table is left to its row bands."""
    found = {norm(label): area for area in areas.names(page_type) if area != "residents_table"
             for label in areas.fields(page_type, area)}
    return sorted(((label, area) for label, area in found.items() if label not in TOO_GENERIC), key=lambda item: -len(item[0]))


def absolute(text, pattern):
    """The first match of a position that is not relative to something ("top-right of resident panel")."""
    for m in re.finditer(pattern, text):
        if "margin" in m.group() or not RELATIVE.match(text, m.end()):
            return m


#coded cards in the numbered layout ("21 Overcrowding", "items 61-78"): items 1-31 are the left column, 32-57 the middle, 58-79 the right
def numbered_item(location):
    m = re.match(r"(\d{1,2})(?:\s*[-–,]\s*\d{1,2})?\s+[A-Z]", location.strip()) or re.search(r"\b(?:items?|row)\s+(\d{1,2})\b", location, re.I)
    n = m and int(m.group(1))
    return n and ("left_column" if n <= 31 else "middle_column" if n <= 57 else "right_column" if n <= 79 else None)


#(area name, region) for a page type's location text; (None, None) when no rule fits
def place(page_type, location):
    if page_type not in POSITIONS or not location:
        return None, None
    text = re.sub(r"\s+", " ", location.lower().replace("’", "'")).strip()
    if page_type == "main" and RIGHT_PANEL.search(text):
        return "right_margin", None
    found = [(m.start(), n, area) for n, (pattern, area) in enumerate(POSITIONS[page_type]) if (m := absolute(text, pattern))]
    if found:
        return min(found)[2], None
    if page_type == "coded" and (area := numbered_item(location)):
        return area, None
    if page_type == "main":
        is_table, region = residents(re.sub(r"(?:industry|occupation)(?: of (?:the )?head)?(?: (?:and|&)|/|,)?(?: (?:industry|occupation))? codes?", " ", text))
        if is_table:
            return "residents_table", region
    words = f" {norm(text)} "
    for label, area in labels(page_type):
        if f" {label} " in words:
            return area, None
    for area, pattern in FIELDS[page_type]:
        if re.search(pattern, text):
            return area, None
    return None, None
