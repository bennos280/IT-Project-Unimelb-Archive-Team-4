# Survey consistency checks (US6)

Compares a survey's main form (page 1) with its coded card (page 3), and checks the coded card's own sums and codes.
It flags contradictions for a reviewer; it never changes a reading. The pipeline runs it after `group`, and the loader
saves its conflicts as flags on the fields involved, so they show in the review screen.

| File | Does |
| --- | --- |
| `validator.py` | The rules: reads messy values (`5 yrs.`, `24A`, `Head (f)`) and compares page 1 with page 3 |
| `codebook.py` | Checks coded values against `backend/db/data_dict.json` (allowed codes, ranges, municipality names) |
| `run_validation.py` | `validate_survey(main, coded)`: one survey's readings to its flags |
| `pipeline_step.py` | The pipeline's `validate` step, and `uv run survey validate <run>/manifest.json` to re-check a run without reading any page again |

The rules read the transcription templates' field names (`backend/pipeline/transcribe/templates/`) directly;
`tests/unit/test_validate_fields.py` fails if a rule reads a field the templates don't have.

## Output

`validation/output_flagged.json` in the run's folder lists each survey's flags: a type, a reason, the fields involved
(`"Page 1: rooms.number_of_living_rooms": "2"`, `<missing>` for an absent field) and, where useful, the comparison made.
A flag marks the fields in a disputed relationship; it doesn't say which of them is wrong. Surveys without exactly one
main form and one coded card, or whose coded reading has no `number_of_dwelling` (not a coded card reading), are listed
under `not_validated`. `review.json` gets a short line per flagged page.

Flag types: `Page 1–3 conflict`, `Page 1 internal conflict`, `Page 3 internal conflict`, `Page 3 codebook conflict`,
and `… comparison incomplete` when one side is missing, `/`, `[?]` or can't be read. Only conflicts become flags in the
database. A comparison with both sides blank is skipped. Zero is a value; `01`, `1` and `1.0` are equal; `none`, `nil`,
`no` and `zero` count as 0.

## Page 1 against page 3

| Page 1 | Page 3 | Check |
| --- | --- | --- |
| `number_of_dwelling` | `number_of_dwelling` | Equal after removing leading zeros and spaces; a letter suffix counts (`024 a` = `24A`, not `24B`) |
| `rooms.number_of_separate_bedrooms` | `number_of_bedrooms` | Codes 1–11 are exact counts; 0 means over 11 |
| `rooms.number_of_living_rooms` | `number_of_living_rooms` | As above |
| `rooms.rooms_not_in_daily_use` | `rooms_not_in_daily_use` | Equal counts |
| `rooms.number_of_sleepouts` | `number_of_sleepouts` | Count 0 → code 0; 1 → 1/2/3; 2 or more → 4; "verandah", "balcony", "outhouse" → 1, 2, 3 |
| `length_of_residence` | `length_of_residence` | 00 under a year, 01–98 exact years, 99 unknown |
| `industry_of_head_code`, `occupation_of_head_code` | `industry_of_head`, `occupation_of_head` | Equal codes, only when page 1 has a code |
| Residents with anything written | `total_number_resident_members` | Count; blank template columns don't count |
| Residents' ages | `number_under_5`, `number_5_to_10`, `children_under_14` | Under 5; 5 to 10 inclusive; under 14 |
| Residents' ages and sex | `number_over_10_male`, `number_over_10_female` | Sex from a sex column, `Head (F)`-style notes or the relationship (son, wife, ...); unknown sex gives a range, never a guess |
| The one Head's age | `age_of_head` | Equal; 00 is unknown; no Head or several Heads can't be compared |
| Boarders and lodgers | `number_of_boarders` | Count, when every relationship is filled in |
| Sons and daughters at home (+ `children_other_than_those_at_home`) | `children_of_head_or_wife_living` | Can't exceed living children |
| `municipality` | `municipality` | Page 1's name against the codebook's name for the code |
| `probable_age` | `age_of_house` | Equal, inside a range, or agreeing with "over/under N"; 00 and 98 have no age, 99 means over 99 |

## Page 3 and page 1 sums

- `children_of_head_or_wife_living + _dead = _total`
- `number_under_5 + number_5_to_10 + number_over_10_male + number_over_10_female = total_number_resident_members`
- Adult male, adult female and juvenile breadwinners together ≤ residents
- Each of boarders, participating members, children under 14, persons sharing, retired and independent persons, and
  home duties ≤ residents
- `number_under_5 + number_5_to_10 ≤ children_under_14`
- Bedrooms, living rooms and rooms not in daily use each ≤ `total_number_of_rooms`; bedrooms + living rooms ≤ total
  (code 0, over 11, as a lower bound); `rooms_shared` is a sharing category, not a count
- Page 1: living rooms "used as bedrooms" with a living-room count of 0

## Not checked

- `other_children` on page 1 is free text, so it isn't counted (a warning notes it's there).
- Industry and occupation prose isn't matched to codes; neither are structural material or tenure.
- The children checks assume one family per survey.
