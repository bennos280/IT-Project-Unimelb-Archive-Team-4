#the review screen's section for each field (a nested one, like kitchen.shared, goes under its parent)
SECTIONS_MAIN = {
    "Address": ["address", "municipality", "number_of_families_in_dwelling", "number", "number_of_dwelling"],
    "Dwelling": ["type_of_dwelling", "structural_material", "number_of_storeys", "probable_age"],
    "Yard and garden": ["yard_or_uncultivated_space", "cultivated_garden", "weekly_value_of_fruit_and_vegetables_grown",
                        "weekly_value_of_fruit_and_vegetables_sold", "other_commercial_activities_on_premises"],
    "Interview": ["date_of_interview", "signature_of_investigator"],
    "Tenure": ["tenure", "weekly_rent_or_instalments", "furnished_or_unfurnished", "length_of_residence"],
    "Archive and codes": ["archive_reference", "industry_of_head_code", "occupation_of_head_code"],
    "Wash house": ["wash_house"],
    "Survey details": ["text"],
}

SECTIONS_CODED = {
    "Left column": ["municipality", "number_of_dwelling", "number_of_household", "type_of_family",
                    "total_number_resident_members", "number_under_5", "number_5_to_10", "number_over_10_male",
                    "number_over_10_female", "military_service", "number_of_boarders",
                    "number_of_participating_members", "number_of_adult_male_breadwinners",
                    "number_of_adult_female_breadwinners", "number_of_juvenile_breadwinners_under_21",
                    "children_under_14", "retired_and_independent_persons", "home_duties", "other",
                    "normal_household_income", "weekly_rent", "total_available_income"],
    "Middle column": ["earnings_of_head", "heads_unearned_income", "main_source_of_heads_unearned_income",
                      "subsidiary_source_of_heads_income", "industry_of_head", "occupation_of_head",
                      "grade_of_occupation_of_head", "place_of_work", "age_of_head", "sex_of_head",
                      "regularity_of_work", "pre_war_occupation", "removal", "type_of_dwelling", "structural_material",
                      "age_of_house", "garden", "state_of_repair", "tenure", "length_of_residence",
                      "total_number_of_rooms", "number_of_bedrooms"],
    "Right column": ["number_of_living_rooms", "whether_used_as_bedrooms", "rooms_not_in_daily_use",
                     "number_of_sleepouts", "bathroom", "wc", "washouse", "kitchen", "sink_and_water_service",
                     "cooking_facilities", "food_storage", "rooms_shared", "persons_sharing",
                     "children_other_than_those_at_home", "children_of_head_or_wife_living",
                     "children_of_head_or_wife_dead", "children_of_head_or_wife_total"],
}

groupings_main = {field: section for section, fields in SECTIONS_MAIN.items() for field in fields}
groupings_coded = {field: section for section, fields in SECTIONS_CODED.items() for field in fields}
