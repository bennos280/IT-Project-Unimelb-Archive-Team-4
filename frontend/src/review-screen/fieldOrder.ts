// Defines main-page presentation order without changing backend field IDs or values.
import type { Field, PageType } from "./model";

const sections: [string, string[]][] = [
  [
    "Address",
    ["address", "municipality", "number_of_families_in_dwelling", "number"],
  ],
  [
    "Archive and codes",
    ["archive_reference", "industry_of_head_code", "occupation_of_head_code"],
  ],
  ["Interview", ["date_of_interview", "signature_of_investigator"]],
  [
    "Dwelling",
    [
      "type_of_dwelling",
      "structural_material",
      "number_of_storeys",
      "probable_age",
    ],
  ],
  [
    "Yard and Garden",
    [
      "yard_or_uncultivated_space",
      "cultivated_garden",
      "weekly_value_fruit_and_vegetables_grown",
      "weekly_value_fruit_and_vegetables_sold",
      "other_commercial_activities_on_premises",
    ],
  ],
  [
    "Tenure",
    [
      "tenure",
      "weekly_rent_or_instalments",
      "furnished_or_unfurnished",
      "length_of_residence",
    ],
  ],
  ["Resident", []],
  [
    "Rooms",
    [
      "rooms.number_of_separate_bedrooms",
      "rooms.number_of_living_rooms",
      "rooms.state_if_used_as_bedrooms",
      "rooms.rooms_not_in_daily_use",
      "rooms.sleepouts",
    ],
  ],
  ["Bath", ["bath.location", "bath.shared", "bath.hot_water_service"]],
  ["W.C", ["wc.internal_or_external", "wc.shared"]],
  ["Wash-house", ["wash_house"]],
  [
    "Kitchen",
    [
      "kitchen.shared",
      "kitchen.ever_used_as_bedroom",
      "kitchen.meals_can_be_taken_there",
      "kitchen.sink_and_water_tap",
      "kitchen.hot_water_service",
      "kitchen.cooking_facilities",
      "kitchen.food_storage",
      "kitchen.facilities_for_cooking_and_water_supply_in_other_rooms",
    ],
  ],
  [
    "Kitchen",
    [
      "kitchen.shared",
      "kitchen.ever_used_as_bedroom",
      "kitchen.meals_can_be_taken_there",
      "kitchen.sink_and_water_tap",
      "kitchen.hot_water_service",
      "kitchen.cooking_facilities",
      "kitchen.food_storage",
      "kitchen.facilities_for_cooking_and_water_supply_in_other_rooms",
    ],
  ],
];

// Each resident uses the same field order; children belong to the survey,
// so they are shown once rather than assigned to a particular resident.
const residentFields = [
  ["relationship", "Personal: Relationship"],
  ["age", "Personal: Age"],
  ["earning_status", "Personal: Earning status"],
  ["unearned_income_weekly_amount", "Unearned Income: Weekly Amount"],
  ["unearned_income_source", "Unearned Income: Source"],
  ["industry", "Occupation: Industry"],
  ["craft", "Occupation: Craft"],
  ["regularity_of_work", "Occupation: Regularity of work"],
  ["employer", "Occupation: Employer"],
  ["employers_address", "Occupation: Employer's Address"],
  ["weekly_cost_transport", "Occupation: Weekly cost transport"],
  ["residential_preference", "Occupation: Residential preference"],
  ["earnings_last_week", "Earnings: Earnings last week"],
  [
    "full_time_earnings_excluding_overtime",
    "Earnings: Full time earnings excluding overtime",
  ],
  ["weekly_contribution_to_board", "Earnings: Weekly contribution to board"],
  [
    "weekly_payments_to_relatives_living_elsewhere",
    "Earnings: Weekly payments to relatives living elsewhere",
  ],
  ["prewar_occupation", "Pre-War: Occupation"],
  ["prewar_normal_weekly_earnings", "Pre-War: Normal weekly earnings"],
  [
    "prewar_place_of_work_if_outside_melbourne",
    "Pre-War: Place of work if outside Melbourne",
  ],
  ["prewar_occupational_preference", "Pre-War: Occupational preference"],
];

// Matches the coded scan's three columns, reading each from top to bottom.
const codedSections: [string, string[]][] = [
  [
    "Left column",
    [
      "municipality",
      "number_of_dwelling",
      "number_of_household",
      "type_of_family",
      "total_resident_members",
      "number_under_5",
      "number_5_to_10",
      "number_over_10_m",
      "number_over_10_f",
      "military_service",
      "boarders",
      "participating_members",
      "adult_m_breadwinners",
      "adult_f_breadwinners",
      "juvenile_breadwinners_under_21",
      "children_under_14",
      "retired_and_indep_persons",
      "home_duties",
      "other",
    ],
  ],
  [
    "Middle column",
    [
      "normal_household_income",
      "weekly_rent",
      "total_available_income",
      "earnings_of_head",
      "heads_unearned_income",
      "main_source_heads_unearned_income",
      "subsidiary_source_heads_income",
      "industry_of_head",
      "occupation_of_head",
      "grade_of_occupation_of_head",
      "place_of_work",
      "age_of_head",
      "sex_of_head",
      "regularity_of_work",
      "prewar_occupation",
      "removal",
      "type_of_dwelling",
      "structural_material",
      "age_of_house",
      "garden",
      "state_of_repair",
      "tenure",
    ],
  ],
  [
    "Right column",
    [
      "length_of_residence",
      "total_number_of_rooms",
      "number_of_bedrooms",
      "number_of_living_rooms",
      "whether_used_as_bedrooms",
      "rooms_not_in_daily_use",
      "number_of_sleepouts",
      "bathroom",
      "wc",
      "washhouse",
      "kitchen",
      "sink_and_water_service",
      "cooking_facilities",
      "food_storage",
      "rooms_shared",
      "persons_sharing",
      "children_other_than_those_at_home",
      "children_of_h_or_wife_living",
      "children_of_h_or_wife_dead",
      "children_of_h_or_wife_total",
    ],
  ],
];

// Orders known coded fields and assigns their matching scan column.
// Additional fields remain visible at the end; IDs and values stay unchanged.
function orderCodedFields(fields: Field[]): Field[] {
  const layout = new Map<string, { group: string; rank: number }>();

  for (const [group, ids] of codedSections) {
    for (const id of ids) {
      layout.set(id, { group, rank: layout.size });
    }
  }

  return fields
    .map((field, index) => {
      const position = layout.get(field.id);

      return {
        field: position ? { ...field, group: position.group } : field,
        rank: position?.rank ?? layout.size + index,
      };
    })
    .sort((a, b) => a.rank - b.rank)
    .map(({ field }) => field);
}

// Returns a separate display list; the source data used for saving stays intact.
// Notes and coded pages retain their existing layout and order.
export function orderFields(fields: Field[], type: PageType): Field[] {
  if (type === "coded") return orderCodedFields(fields);
  if (type !== "main") return fields;
  const unknownGroups = [...new Set(fields.map((field) => field.group))];
  const ranked = fields.map((field) => {
    for (const [sectionIndex, [group, ids]] of sections.entries()) {
      const position = ids.indexOf(field.id);
      if (position >= 0)
        return {
          field: { ...field, group },
          section: sectionIndex,
          position,
          person: 0,
        };
    }
    const resident = /^residents\.(\d+)\.(.+)$/.exec(field.id);

    if (resident) {
      const residentNumber = Number(resident[1]);
      const index = residentFields.findIndex(([id]) => id === resident[2]);

      return {
        field: {
          ...field,
          // Display numbering starts at 1; retain the original US8 field ID.
          group: `Resident ${residentNumber + 1}`,
          label: index < 0 ? field.label : residentFields[index][1],
        },
        section: 6,
        position: index < 0 ? residentFields.length : index,
        person: residentNumber,
      };
    }
    const child = /^other_children\.(died|living_elsewhere)\.(\d+)$/.exec(
      field.id,
    );

    if (child) {
      return {
        field: {
          ...field,
          group: "Other children of head",
          label:
            child[1] === "died"
              ? "Other children: Died"
              : "Other children: Living elsewhere",
        },
        section: 6,
        position: child[1] === "died" ? 0 : 1,
        person: Number.MAX_SAFE_INTEGER,
      };
    }

    // Preserve every additional field and its relative order within its group.
    return {
      field,
      section: sections.length + unknownGroups.indexOf(field.group),
      position: 0,
      person: 0,
    };
  });
  return ranked
    .sort(
      (a, b) =>
        a.section - b.section || a.person - b.person || a.position - b.position,
    )
    .map(({ field }) => field);
}
