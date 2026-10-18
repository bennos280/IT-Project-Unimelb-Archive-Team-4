"""area_rules.place(): the area (and the residents row band) that an annotation's location words give."""
import re

import pytest

from backend.pipeline.transcribe import area_fields, area_rules, areas
from backend.pipeline.transcribe.area_rules import place

ROW = {"x": 0.04, "width": 0.57}


@pytest.mark.parametrize("location, area", [
    ("top-left, right of dwelling number", "top_left_corner"),
    ("after municipality", "address_block"),
    ("right margin box below codes (red)", "right_margin"),
    ("top centre, red pencil", "header"),
    ("above yard question", "dwelling_block"),
    ("Top Left corner", "top_left_corner"),  # case and spacing do not matter
    ("  upper-right   corner ", "top_right_corner"),
    ("bottom-left margin, pencil", "bottom_left"),  # the bottom-left corner, not the left margin
    ("bottom right, blue pencil", "bottom_right"),
    ("top center", "header"),
    ("left margin, pre-war section", "left_margin"),
    ("left edge", "left_margin"),
    ("right margin, red pencil, top right", "right_margin"),  # the first position phrase says where the mark is
    ("top-right, right of right margin", "top_right_corner"),
    ("dwelling no.", "top_left_corner"),
    ("title", "header"),
    ("below signature of investigator", "top_right_corner"),
    ("no. of families in dwelling", "address_block"),
    ("beside Type of Dwelling", "dwelling_block"),
    ("probable age", "dwelling_block"),  # not the residents' age row
    ("right of weekly rent", "tenure_block"),
    ("beside Furnished or Unfurnished", "tenure_block"),
    ("below industry code", "right_margin"),  # not the industry row
    ("occupation code", "right_margin"),
    ("red pencil, near H.W.S.", "kitchen_block"),
    ("kitchen and bedroom", "kitchen_block"),  # the first field list that fits
    ("next to Number of Sleepouts", "rooms_block"),
    ("by the W.C.", "rooms_block"),
])
def test_main_form_locations(location, area):
    assert place("main", location) == (area, None)


@pytest.mark.parametrize("location, region", [
    ("unearned income weekly amount/source, column 2 (red)", {"x": 0.255, "y": 0.438, "width": 0.093, "height": 0.062}),
    ("residential pref row (red)", {"x": ROW["x"], "y": 0.67, "width": ROW["width"], "height": 0.028}),
    ("Relationship row", {**ROW, "y": 0.292, "height": 0.032}),
    ("age row, column 1", {"x": 0.169, "y": 0.322, "width": 0.093, "height": 0.035}),
    ("Died and Living Elsewhere rows", {**ROW, "y": 0.378, "height": 0.064}),
    ("unearned income", {**ROW, "y": 0.438, "height": 0.062}),  # both its rows
    ("unearned income source", {**ROW, "y": 0.469, "height": 0.031}),
    ("employer's address, column 3", {"x": 0.342, "y": 0.612, "width": 0.09, "height": 0.034}),
    ("employers address", {**ROW, "y": 0.612, "height": 0.034}),
    ("employer row", {**ROW, "y": 0.585, "height": 0.032}),
    ("employer and employer's address", {**ROW, "y": 0.585, "height": 0.061}),
    ("payments to relatives living elsewhere", {**ROW, "y": 0.802, "height": 0.041}),  # not the living elsewhere row
    ("living elsewhere row", {**ROW, "y": 0.406, "height": 0.036}),
    ("pre-war occupation", {**ROW, "y": 0.839, "height": 0.043}),
    ("occupational pref", {**ROW, "y": 0.943, "height": 0.036}),
    ("pre-war normal weekly earnings", {**ROW, "y": 0.876, "height": 0.029}),
    ("place of work", {**ROW, "y": 0.9, "height": 0.052}),
    ("earnings last week", {**ROW, "y": 0.696, "height": 0.035}),
    ("full-time earnings", {**ROW, "y": 0.729, "height": 0.042}),
    ("weekly contribution to board", {**ROW, "y": 0.771, "height": 0.031}),
    ("industry row", {**ROW, "y": 0.495, "height": 0.036}),
    ("transport, columns 3-4", {"x": 0.342, "y": 0.641, "width": 0.176, "height": 0.031}),
])
def test_residents_rows_give_a_band_across_the_named_columns(location, region):
    area, got = place("main", location)
    assert area == "residents_table" and got == pytest.approx(region) and set(got) == {"x", "y", "width", "height"}


def test_an_age_in_brackets_is_not_the_age_row():
    assert place("main", "son (age 9) column") == (None, None)


def test_a_column_without_a_row_is_the_residents_table_and_has_no_band():
    assert place("main", "column 4, red pencil") == ("residents_table", None)
    assert place("main", "right of column 2") == ("residents_table", None)


def test_the_bands_and_columns_lie_inside_the_residents_table_and_the_card():
    for _, _, y0, y1 in area_rules.ROWS:
        assert .29 <= y0 < y1 <= 1
    columns = list(area_rules.COLUMNS.values())
    assert all(x0 < x1 for x0, x1 in columns) and [c[0] for c in columns] == sorted(c[0] for c in columns)
    assert 0 < area_rules.LABELS_AND_COLUMNS[0] < columns[0][0] and columns[-1][1] < area_rules.LABELS_AND_COLUMNS[1] < 1


@pytest.mark.parametrize("location, area", [
    ("bottom-left, red pencil", "bottom_left"),
    ("bottom right, blue pencil", "bottom_right"),
    ("top-left corner, red pencil star", "top_left_corner"),
    ("top right, red pencil above length of residence", "top_right_corner"),
    ("top centre", "middle_column"),
    ("right margin, red", "right_column"),
    ("left edge", "left_margin"),
    ("household members", "left_column"),
    ("beside No. of Boarders", "left_column"),
    ("Under 5 box", "left_column"),
    ("red pencil next to Removal value", "middle_column"),
    ("through Garden and State of Repair values", "middle_column"),
    ("right of occupation of H. value", "middle_column"),
    ("Rooms not in daily use", "right_column"),
    ("total number of rooms", "right_column"),
    ("household income", "left_column"),  # the left list comes first
])
def test_coded_card_locations(location, area):
    assert place("coded", location) == (area, None)


def test_every_area_it_gives_exists_for_the_page_type():
    for page_type in ("main", "coded"):
        given = {area for _, area in area_rules.POSITIONS[page_type]} | {area for area, _ in area_rules.FIELDS[page_type]}
        assert given <= set(areas.names(page_type))
    assert "residents_table" in areas.names("main")


@pytest.mark.parametrize("page_type, location", [
    ("main", "somewhere odd"), ("main", ""), ("main", None), ("coded", "by the star"), ("coded", None),
    ("notes", "top-left"), ("other", "top-left"), ("blank", "bottom left"),
])
def test_an_unknown_location_or_a_page_type_without_areas_gives_nothing(page_type, location):
    assert place(page_type, location) == (None, None)


def test_the_main_forms_residents_words_mean_nothing_on_a_coded_card():
    assert place("coded", "residential pref row") == (None, None)


@pytest.mark.parametrize("location, region", [
    ("third resident column, Relationship/Age/Earning Status rows", {"x": 0.342, "y": 0.292, "width": 0.09, "height": 0.095}),
    ("relationship row, across columns 3-6", {"x": 0.342, "y": 0.292, "width": 0.267, "height": 0.032}),  # past the last box
    ("relationship row, columns 6-7", {**ROW, "y": 0.292, "height": 0.032}),
    ("son (col 3) unearned income row", {"x": 0.342, "y": 0.438, "width": 0.09, "height": 0.062}),
    ("Head column 1943 earnings last week", {**ROW, "y": 0.696, "height": 0.035}),  # 1943 is not column 1
    ("wife column, Wkly. Cont. to Board / Payments rows", {**ROW, "y": 0.771, "height": 0.072}),
    ("Pre-War Norm. Wkly. Earn's row, columns 3-4", {"x": 0.342, "y": 0.876, "width": 0.176, "height": 0.029}),
    ("pre war occupation", {**ROW, "y": 0.839, "height": 0.043}),
])
def test_residents_wordings_seen_in_the_scans(location, region):
    assert place("main", location) == ("residents_table", pytest.approx(region))


def test_the_codes_and_the_dwellings_age_are_not_residents_rows():
    assert place("main", "beside industry and occupation codes") == ("right_margin", None)
    assert place("main", "Type of Dwelling box, below Age") == ("dwelling_block", None)
    assert place("main", "Son column 1943") == ("residents_table", None)


@pytest.mark.parametrize("page_type, location, area", [
    ("coded", "after Length of Residence label", "right_column"),
    ("main", "after Length of Residence label", "tenure_block"),
    ("coded", "beside Total Available I.", "middle_column"),
    ("coded", "Head's Unearned I. value", "middle_column"),
    ("coded", "Number of Dwelling line", "left_column"),
    ("main", "Number of Dwelling line", "top_left_corner"),
    ("main", "Number of Dwelling", "top_left_corner"),
    ("coded", "left of Food Storage value", "right_column"),
    ("main", "left of Food Storage value", "kitchen_block"),
    ("coded", "Sink and Water Service", "right_column"),
    ("coded", "Persons Sharing", "right_column"),
    ("coded", "right of Children of H. or Wife: Total", "right_column"),
    ("coded", "beside Number of Dwelling", "left_column"),
    ("main", "beside No. of Storeys box", "dwelling_block"),
    ("main", "Kitchen: Sink and Water Tap", "kitchen_block"),
    ("main", "right of municipality", "address_block"),
    ("main", "right of Signature of Investigator", "top_right_corner"),
    ("main", "below industry of head code", "right_margin"),
])
def test_a_printed_field_gives_the_area_its_box_is_in(page_type, location, area):
    assert place(page_type, location) == (area, None)


@pytest.mark.parametrize("location", [
    "bottom left-centre", "bottom centre-left", "bottom, left of centre", "Bottom-Left-Centre, pencil", "bottom left of centre",
])
@pytest.mark.parametrize("page_type", ["main", "coded"])
def test_bottom_left_of_centre_is_the_bottom_left(page_type, location):
    assert place(page_type, location) == ("bottom_left", None)


@pytest.mark.parametrize("location", [
    "bottom centre-right", "bottom right-centre", "bottom, right of centre", "bottom-centre-right, red pencil", "bottom right of centre",
])
@pytest.mark.parametrize("page_type", ["main", "coded"])
def test_bottom_right_of_centre_is_the_bottom_right(page_type, location):
    assert place(page_type, location) == ("bottom_right", None)


def test_plain_bottom_centre_and_the_corners():
    assert place("main", "bottom centre") == ("bottom_centre", None)
    assert place("coded", "bottom middle, pencil") == ("bottom_centre", None)
    assert place("main", "bottom right, blue pencil") == ("bottom_right", None)
    assert place("main", "bottom left corner") == ("bottom_left", None)


@pytest.mark.parametrize("page_type, location, expected", [
    ("main", "top-right of resident panel", ("residents_table", None)),
    ("main", "top right of the residents table", ("residents_table", None)),
    ("main", "left of Food Storage", ("kitchen_block", None)),
    ("coded", "left of Food Storage", ("right_column", None)),
    ("main", "right of municipality", ("address_block", None)),
    ("main", "bottom-left of the weekly rent", ("tenure_block", None)),
    ("main", "top-left of relationship row", ("residents_table", pytest.approx({"x": 0.04, "y": 0.292, "width": 0.57, "height": 0.032}))),
    ("main", "bottom right of column 2", ("residents_table", None)),
    ("main", "top-right of nothing we know", (None, None)),
    ("main", "top-right, right of dwelling number", ("top_right_corner", None)),  # a comma ends the position
    ("main", "top right of centre", ("top_right_corner", None)),
    ("main", "right margin of the form", ("right_margin", None)),  # margins stay absolute
    ("coded", "left margin of card", ("left_margin", None)),
])
def test_a_position_followed_by_of_something_is_placed_by_that_thing(page_type, location, expected):
    assert place(page_type, location) == expected


def test_the_head_column_is_residents_column_1():
    assert place("main", "Head column") == ("residents_table", None)
    area, region = place("main", "Head column, age row")
    assert area == "residents_table" and region == pytest.approx({"x": 0.169, "y": 0.322, "width": 0.093, "height": 0.035})
    assert place("main", "head column, age row") == place("main", "age row, column 1")
    assert place("main", "head's column, relationship row") == place("main", "relationship, column 1")
    assert place("coded", "head column") == (None, None)  # a main form's words
    assert place("main", "wife column, age row") == ("residents_table", pytest.approx({**ROW, "y": 0.322, "height": 0.035}))


def field_ids(page_type):
    return {re.sub(r"\.\d+", "", field_id) for field_id in area_fields.boxes(page_type)}


@pytest.mark.parametrize("page_type", ["main", "coded"])
def test_every_review_screen_field_is_listed_in_exactly_one_area(page_type):
    ids = area_fields.boxes(page_type)
    assert len(ids) > 40
    for field_id in ids:
        label = area_fields.printed(page_type, field_id)
        listed = [name for name in areas.names(page_type) if label in areas.fields(page_type, name)]
        assert len(listed) == 1, (field_id, label, listed)


@pytest.mark.parametrize("page_type", ["main", "coded"])
def test_areas_json_fields_are_what_the_generator_gives_from_the_field_boxes(page_type):
    assert area_fields.generate()[page_type] == {name: areas.fields(page_type, name) for name in areas.names(page_type)}


def test_fields_are_where_the_boxes_are():
    assert "Length of Residence" in areas.fields("coded", "right_column")
    assert "Number of Dwelling" in areas.fields("coded", "left_column")
    assert "Total Available I." in areas.fields("coded", "middle_column")
    assert "Wkly. Cost Transport" in areas.fields("main", "residents_table")
    assert "Kitchen: Food Storage?" in areas.fields("main", "kitchen_block")
    assert "Signature of Investigator" in areas.fields("main", "top_right_corner")
    assert "W.C.: Shared?" in areas.fields("main", "rooms_block")  # the bottom-right box overlaps it


def test_of_the_middle_column_is_relative_but_of_centre_is_not():
    assert place("coded", "bottom-right of middle column, red pencil") == ("middle_column", None)
    assert place("coded", "bottom-right of centre, red pencil")[0] == "bottom_right"


@pytest.mark.parametrize("page_type, location, expected", [
    ("main", "top right corner of right margin box", ("right_margin", None)),
    ("main", "top-right corner of rooms box", ("rooms_block", None)),
    ("main", "right edge of W.C. box", ("rooms_block", None)),
    ("main", "vertical, left edge of rooms box", ("rooms_block", None)),
    ("main", "top right corner of residents table", ("residents_table", None)),
    ("main", "top right corner of resident grid", (None, None)),  # relative to a thing the rules do not know, not the card corner
    ("main", "left edge of right-hand box", (None, None)),
    ("main", "top-left of form, blue pencil", ("top_left_corner", None)),  # the card itself is not a thing
    ("main", "top right corner of the page", ("top_right_corner", None)),
    ("coded", "bottom left of the card", ("bottom_left", None)),
    ("main", "top right corner, red pencil", ("top_right_corner", None)),
    ("main", "right edge, pencil", ("right_margin", None)),
    ("main", "right margin of residents grid", ("right_margin", None)),
])
def test_a_corner_or_edge_of_something_is_relative_to_it_but_not_to_the_card(page_type, location, expected):
    assert place(page_type, location) == expected


@pytest.mark.parametrize("location, area", [
    ("bottom, below Other", "bottom_left"),
    ("bottom-left, below Other", "bottom_left"),  # the same spot with the corner named
    ("pencil below Other value", "bottom_left"),
    ("bottom, beside Other, pencil", "bottom_left"),
    ("bottom, right of Other", "bottom_left"),
    ("beside Other", "left_column"),
    ("blue pencil, near 'Other' value", "left_column"),
    ("right of Other value", "left_column"),
    ("Children other than those at home value", "right_column"),  # "other" in another label
    ("the other side, pencil", None),  # an everyday word
    ("beside other marks", None),
    ("beside Other than the 3", None),
    ("below other marks, pencil", None),
    ("pencil below 'Other', red", "bottom_left"),
    ("beside Other (original value)", "left_column"),
])
def test_other_is_the_last_left_column_line_only_after_a_preposition(location, area):
    assert place("coded", location) == (area, None)


@pytest.mark.parametrize("location, area", [
    ("Washhouse value", "right_column"),
    ("left of Washhouse value", "right_column"),
    ("grey pencil, left of Children Living/Dead", "right_column"),
    ("beside Children Total", "right_column"),
    ("left of Dead", "right_column"),
    ("Children of H. or Wife column", "right_column"),
    ("after Living value", "right_column"),
])
def test_the_shorter_children_and_washhouse_wordings_seen_in_the_scans(location, area):
    assert place("coded", location) == (area, None)


@pytest.mark.parametrize("location", [
    "Wkly. Payments to rel. living elsewhere row", "wkly payments to rel. liv'g elsewhere", "payments to relatives living elsewhere",
])
def test_payments_to_relatives_is_one_row_however_it_is_abbreviated(location):
    assert place("main", f"{location}, head column") == ("residents_table", pytest.approx({"x": 0.169, "y": 0.802, "width": 0.093, "height": 0.041}))


def test_an_absolute_position_beats_a_field_and_a_residents_row_beats_a_field():
    assert place("main", "top-left, below dwelling number, above Address") == ("top_left_corner", None)
    assert place("main", "bottom right, beside Type of Dwelling") == ("bottom_right", None)
    assert place("main", "Municipality, age row")[0] == "residents_table"
    assert place("main", "Age row, beside Tenure") == ("residents_table", pytest.approx({**ROW, "y": 0.322, "height": 0.035}))
    assert place("coded", "top left, over Number of Dwelling") == ("top_left_corner", None)
    assert place("coded", "bottom left of centre, near Garden")[0] == "bottom_left"


#the printed label of a field and the area its box centre is in, checked by eye against fieldLocations.ts
SPOT_CHECKS = {
    "main": {"Date of Interview": "top_right_corner", "Signature of Investigator": "top_right_corner", "Municipality": "address_block",
             "Type of Dwelling": "dwelling_block", "Probable Age": "dwelling_block", "Tenure": "tenure_block",
             "Length of Residence.": "tenure_block", "No of Separate Bedrooms": "rooms_block", "Wash-house?": "rooms_block",
             "Kitchen: Food Storage?": "kitchen_block", "Kitchen: Cooking facilities?": "kitchen_block",
             "Kitchen: H.W.S.?": "kitchen_block", "W.C.: Shared?": "rooms_block", "Bath: Location?": "rooms_block",
             "Industry code": "right_margin", "Occupation code": "right_margin", "archive reference": "header",
             "Dwelling No.": "top_left_corner", "Wkly. Cost Transport": "residents_table", "Pre-War: Occupation": "residents_table"},
    "coded": {"Municipality": "left_column", "Number of Dwelling": "left_column", "Other": "left_column", "Home Duties": "left_column",
              "Normal Household I.": "middle_column", "Total Available I.": "middle_column", "Head's Unearned I.": "middle_column",
              "Age of Head": "middle_column", "State of Repair": "middle_column", "Tenure": "middle_column",
              "Length of Residence": "right_column", "Total Number of Rooms": "right_column", "W.C": "right_column",
              "Sink and Water Service": "right_column", "Persons Sharing": "right_column", "Children of H. or Wife: Total": "right_column"},
}


@pytest.mark.parametrize("page_type", ["main", "coded"])
def test_spot_checked_fields_are_in_the_area_their_box_is_in(page_type):
    boxes = area_fields.boxes(page_type)
    ids = {area_fields.printed(page_type, field_id): centre for field_id, centre in boxes.items()}
    for label, area in SPOT_CHECKS[page_type].items():
        assert label in areas.fields(page_type, area), (label, area)
        centre = ids.get(label)  #a label that is only an extra name has no box of its own
        if centre and label != "Signature of Investigator" and label != "Length of Residence":
            box = areas.box(page_type, area)
            assert box["x"] <= centre[0] < box["x"] + box["width"] and box["y"] <= centre[1] < box["y"] + box["height"], label


def test_with_several_printed_fields_the_longest_label_decides():
    assert place("coded", "between Removal and Persons Sharing") == ("right_column", None)
    assert place("coded", "between Persons Sharing and Removal") == ("right_column", None)


@pytest.mark.parametrize("location, area", [
    ("right panel, top right", "right_margin"),
    ("right panel above Unearned Income, grey pencil", "right_margin"),
    ("right panel above kitchen", "right_margin"),
    ("right box, red pencil", "right_margin"),
    ("right-hand panel, pencil", "right_margin"),
    ("top right box, blue pencil", "top_right_corner"),
])
def test_the_main_cards_right_panel_is_the_right_margin(location, area):
    assert place("main", location)[0] == area


@pytest.mark.parametrize("location, area", [
    ("37 Poverty (Family 2)", "middle_column"),
    ("33 Unshared (Family 2 rooms)", "middle_column"),
    ("58 Grade of Occup. of Fam. 3, pencil mark", "right_column"),
    ("21 Overcrowding (Dominant Family)", "left_column"),
    ("27-29 T.A.I. (Family 2)", "left_column"),
    ("items 61-78", "right_column"),
    ("row 57", "middle_column"),
])
def test_numbered_coded_items_go_by_their_number(location, area):
    assert place("coded", location)[0] == area


def test_a_number_before_a_lower_case_word_is_not_an_item():
    assert place("coded", "3 circled in red beside Sink and Water Service")[0] == "right_column"


def test_the_shown_box_is_grown_and_kept_on_the_page():
    from backend.pipeline.transcribe import areas
    corner = areas.shown("main", "top_left_corner", None)
    assert (corner["x"], corner["y"]) == (0, 0) and corner["width"] == pytest.approx(0.28) and corner["height"] == pytest.approx(0.15)
    cell = areas.shown("main", "residents_table", '{"x": 0.255, "y": 0.438, "width": 0.093, "height": 0.062}')
    assert (cell["x"], cell["y"], cell["width"], cell["height"]) == (0.24, 0.423, 0.123, 0.092)
    assert areas.shown("main", None, None) is None
