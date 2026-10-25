"""The review screen's id for a value read off a page. A field's id is its title; a value in a list on the page is
<list name>.<item number from 0>.<its field's title in the item>, without the last part for a list of text; an annotation is
annotations.<its number>."""
import re

#template names never have a part that is all digits (instructions.KEY), so the first such part is a list item's number
LIST_VALUE = re.compile(r"(.+?)\.([0-9]+)(?:\.(.+))?")
ANNOTATION = re.compile(r"annotations\.([0-9]+)")


def field_id(list_name: str, item_no: int, field_title: str) -> str:
    if not list_name:
        return field_title
    return ".".join([list_name, str(item_no)] + ([field_title] if field_title else []))


def annotation_id(annotation_no: int) -> str:
    return f"annotations.{annotation_no}"


#the annotation an id is, or None if it isn't one
def annotation_no(field_id: str) -> int | None:
    match = ANNOTATION.fullmatch(field_id)
    return int(match[1]) if match else None


#(list name, item number, field title) of a value's id: ("", 0, title) for a field outside a list, a title "" for a list of text
def parse(field_id: str) -> tuple[str, int, str]:
    match = LIST_VALUE.fullmatch(field_id)
    if match is None:
        return "", 0, field_id
    return match[1], int(match[2]), match[3] or ""
