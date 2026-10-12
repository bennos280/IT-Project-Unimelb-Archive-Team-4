# US6 survey consistency validation

US6 checks structured Page 1 (`main`) and Page 3 (`coded`) transcripts belonging to one survey. It reports inconsistent or incomplete comparisons without correcting transcription values. Notes and unknown fields are preserved.

## Files

| File | Responsibility |
| --- | --- |
| `validator.py` | Numeric/unit normalization, relationship recognition, cross-page checks, internal arithmetic checks, and issue creation. |
| `input_adapter.py` | Maps upstream JSON paths to rule references and retains the reverse mapping to original fields. |
| `codebook.py` | Loads repository-root `data_dict.json`, validates declared code/range domains, resolves documented spelling aliases, and compares municipality labels. |
| `run_validation.py` | Public API, batch validation, original-field flags/review statuses, compact output, and standalone CLI. |
| `pipeline_step.py` | Runs validation after grouping, consumes cached transcripts, records review entries, and supports rerunning an existing manifest. |
| `__init__.py` | Exports the public API. |
| `example_*.json` | Synthetic, mutually consistent sample records for local testing; not real transcription results. |
| `*_schema.json` | Supplied upstream blank templates. Empty templates are unknown data, not zero residents. |
| `sample_input.json` | Legacy rule fixture used by unit tests. |

Tests are in `tests/unit/test_us6_rules.py`, `tests/unit/test_us6_review_regressions.py`, `tests/integration/test_us6_integration.py`, `tests/unit/test_us6_codebook.py`, and `tests/integration/test_us6_pipeline.py`, relative to the repository root. They use pytest assertions and fixtures/parameterization where needed; they do not require paid transcription.

### Why retain the adapter?

The public API already accepts the actual upstream snake_case fields. The adapter retains original nested/list locations for review flags while sharing one rule engine with the earlier uppercase fixture format. It also detects conflicting aliases rather than choosing one silently. It does not assume that the upstream schema will change, infer a codebook, or rewrite source values. Replacing it with native references is a possible future simplification, but it is not necessary to fix the reviewed behavior.

## Running validation

Run commands from the repository root. The validation module uses the Python standard library. Install pytest into the project's environment for tests: `python -m pip install pytest` (or use the repository's existing development dependency setup).

- Grouped example: `python pipeline/us6/run_validation.py pipeline/us6/example_survey.json --output-dir us6_outputs`
- Separate page transcripts: `python pipeline/us6/run_validation.py --main path/to/main.json --coded path/to/coded.json --survey-id survey-24A --output-dir us6_outputs`
- Existing grouped run: `python -m pipeline.us6.pipeline_step path/to/run/manifest.json`
- Through the supplied pipeline entry point: `python -m pipeline.run validate path/to/run/manifest.json`
- US6 tests: `python -m pytest tests/unit/test_us6_rules.py tests/unit/test_us6_review_regressions.py tests/unit/test_us6_codebook.py tests/integration/test_us6_integration.py tests/integration/test_us6_pipeline.py -q`

The integrated `pipeline/run.py` schedules `validate` after `group` when transcription is enabled. A standalone validation call does not need images, model weights, API credentials, or previous pipeline execution if the two page JSON objects are available. Manifest reruns require the referenced cached transcripts to exist.

## Output and missing values

`output_flagged.json` retains source values and adds `has_flags`, `validation_flags`, `review_statuses`, `validation_warnings`, and field-level `_flag` / `_review_status` keys. A flag marks the fields participating in a disputed relationship; it does not prove that every participating field is wrong.

`output_flags_only.json` contains `survey_id` and a flat `flags` list. Each issue records its type, reason, involved source fields, and a comparison expression when useful. The manifest mode wraps surveys in a summary and lists blocked records under `not_validated`. Pipeline outputs are in the run's `validation/` directory. `review.json` contains short per-page validation reasons. Existing non-validation review entries are preserved; reruns replace validation review entries instead of duplicating them. Cached transcripts are never edited.

Issue types distinguish `Page 1–3 conflict`, `Page 1 internal conflict`, `Page 3 internal conflict`, and comparison-incomplete issues for the corresponding pages. Affected fields receive `ToBeReviewed`.

A comparison with both corresponding values blank is skipped. If one value is present but its required counterpart is missing, `/`, `[?]`, blank, or unusable, the comparison is flagged as incomplete. For a formula, all operands blank means skip; only some missing means incomplete. Isolated unreadable or absent fields outside an implemented relationship are not flagged. Numeric zero is a value, not a missing marker. Whole-count equivalents such as `01`, `1`, and `1.0` compare equally; `none`, `nil`, `no`, and `zero` represent zero when used as a count.

## Cross-page checks

| Page 1 source | Page 3 source | Comparison |
| --- | --- | --- |
| `number_of_dwelling` | `number_of_dwelling` | Normalize leading zeros, whitespace, and optional letter suffix; `024 a` equals `24A` but not `24B`. Never substitute Page 1 `number`. |
| `rooms.number_of_separate_bedrooms` | `number_of_bedrooms` | Codes 1-11 are exact counts; code 0 accepts source counts >11. |
| `rooms.number_of_living_rooms` | `number_of_living_rooms` | Same exact-count/over-11 bucket comparison. |
| `rooms.rooms_not_in_daily_use` | `rooms_not_in_daily_use` | Equal whole counts. |
| `rooms.sleepouts` | `number_of_sleepouts` | Count 0 -> code 0; count 1 -> codes 1/2/3; count >=2 -> code 4. Explicit Verandah/Balcony/Outhouse text restricts the corresponding type code. |
| `length_of_residence` | `length_of_residence` | Accept year units with an optional period; code 00 means under one year, 01-98 exact years, and 99 unknown/vague (not exactly 99 years). |
| `industry_of_head_code` | `industry_of_head` | Equal explicit numeric codes, only if the Page 1 code key exists. No prose-to-code mapping. |
| `occupation_of_head_code` | `occupation_of_head` | Same explicit-code rule. |
| Populated `residents` | `total_resident_members` | Count entries containing relationship, age, or earning-status data; ignore blank template entries. |
| `residents[*].age` | `number_under_5`, `number_5_to_10`, `children_under_14` | Derive age counts: age < 5; 5 <= age <= 10; age < 14. Missing required ages make the comparison incomplete. |
| Resident ages and sex/relationships | `number_over_10_m`, `number_over_10_f` | Count age >10 by explicit sex/gender, annotations such as `Head (F)`, or unambiguous relationships. If sex is unknown, use minimum/maximum counts and verify coded M+F against the age-derived total. Do not flag merely because Head lacks sex. |
| Unique Head's age | `age_of_head` | Match `Head`, `H`, `H.`, including parenthesized M/F/male/female annotations. Do not select a Head by row position; coded 00 is unknown, not age zero. Multiple Heads, or a coded head age without a unique source Head, make the comparison incomplete. |
| Boarder/Lodger relationships | `boarders` | Count explicit relationships, including supported sex annotations, when the relationship column is complete. |
| Resident Son/Daughter relationships | `children_of_h_or_wife_living` | Resident children are a lower bound; flag if they exceed living children. |
| Resident Son/Daughter count plus coded `children_other_than_those_at_home` | `children_of_h_or_wife_living` | The combined count must not exceed living children. This assumes the children refer to the same Head or spouse; multi-family semantics need team confirmation. |
| `municipality` | `municipality` | Compare the literal Page 1 name with the dictionary label for the coded value. Leading-zero code equivalents are accepted; unknown/not-applicable codes are not town names. |
| `probable_age` | `age_of_house` | Exact equality, membership in a supplied interval, or agreement with a strict over/under bound. Accept final periods on year units. Codes 00 and 98 carry no exact age, and 99 means over 99. Do not invent a tolerance for approximations. |

For example, resident ages 8 and 7 imply two children under 14, even though Page 1 has no literal `children_under_14` field. Annotated Head recognition uses a full relationship match, so `headache` and `head boarder` are not accidentally treated as Head.

## Internal checks

Page 3 checks:

- `children_of_h_or_wife_living + children_of_h_or_wife_dead = children_of_h_or_wife_total`.
- `number_under_5 + number_5_to_10 + number_over_10_m + number_over_10_f = total_resident_members`.
- `adult_m_breadwinners + adult_f_breadwinners + juvenile_breadwinners_under_21 <= total_resident_members`.
- Each of `boarders`, `participating_members`, `children_under_14`, `persons_sharing`, `retired_and_indep_persons`, and `home_duties` must not exceed `total_resident_members`.
- `number_under_5 + number_5_to_10 <= children_under_14`.
- Each of `number_of_bedrooms`, `number_of_living_rooms`, and `rooms_not_in_daily_use` must not exceed `total_number_of_rooms`.
- `number_of_bedrooms + number_of_living_rooms <= total_number_of_rooms`; rooms not in daily use are not added as a distinct room category. With room code 0 (>11), compare bounds and flag only definite contradictions; an unknown upper bound is not treated as zero. `rooms_shared` is a facility-sharing category and has no numeric room-total inequality.
- `children_other_than_those_at_home <= children_of_h_or_wife_living`.

Page 1 checks `rooms.state_if_used_as_bedrooms = yes` against `rooms.number_of_living_rooms`. A zero living-room count conflicts; a missing count makes the comparison incomplete. This checks living rooms, not separate bedrooms.

## Deliberate limitations and pending work

- `main.other_children` contains survey-level raw-text arrays. Their entry and duplicate semantics have not been established. The obsolete per-Head `OTHER CHILDREN` comparison has been removed; array length is not treated as a child count. Populated arrays are preserved with an explanatory warning. This is not an implemented comparison with Page 3 died/elsewhere counts.
- Codebook domains are now checked against the supplied `data_dict.json`. Enumeration keys and inclusive ranges (e.g. 000-996) are supported. Reserved money codes such as 997/998/999 are valid categories, not exact amounts. INTEGER count fields require non-negative whole counts; definitions marked N/A are not guessed. Room codes allow 0-11, with 0 meaning over 11. Invalid nonblank values produce `Page 3 codebook conflict`; missing/unclear cells are still handled only by meaningful relationships, not isolated unreadable-value flags.
- The dictionary uses different spellings for several upstream fields. Explicit aliases cover `washouse`/`washhouse`, `no_of_boarders`/`boarders`, male/female age-band names, breadwinner names, and children-of-head-or-wife names. Conflicting alias values fail rather than silently choosing one. The adapter remains useful for source paths and these documented aliases.
- Dwelling/household identifiers are excluded from the dictionary's misleading plural INTEGER labels: the upstream dwelling identifier supports letters (24A). No meaning is inferred from similarly named fields. SQL CHAR/VARCHAR widths are not enforced as transcription-string padding requirements; leading zeros are normalized for code comparisons.
- Municipality now has an explicit mapping: Essendon corresponds to 08; 02 means Brunswick and conflicts with Essendon. Structural-material/tenure free text is not automatically matched to code descriptions. Industry and occupation have N/A definitions in this dictionary, so there is still no prose-to-code mapping for them.
- The default codebook path is the repository root, resolved from the module location, not the working directory. `--codebook path/to/data_dict.json` or the API's optional `codebook_path=` overrides it. Existing API calls and pipeline dispatch remain valid. If the default file is absent, validation continues with a clear `validation_warnings` entry; explicit missing paths and malformed dictionaries are input errors. Legacy `pages` input retains its existing rule API and does not run the native-codebook domain layer. Unknown/no-exact-value age/duration codes are preserved with warnings instead of being compared as literal ages.

- The two child lower-bound checks assume relationships refer to the same Head/spouse. Multi-family records require confirmation of those semantics before applying them without qualification.
- Multiple main sheets or coded cards are reported as `NotValidated` rather than silently merged or arbitrarily selected. Unassigned pages and missing/unreadable transcript files are also reported separately from value conflicts.
- These tests use synthetic records. They do not establish accuracy on real surveys or confirm the entire upstream pipeline against the latest repository branch. The reviewer-reported integration failure had no traceback in the supplied screenshots; the relocated replacement tests pass locally, but the original failure cause is not claimed to be known.

## Review revision validation

114 pytest cases pass in the revision workspace, including a repeat with GBK output encoding. Added regressions cover female Head annotations, false Head-prefix matches, trailing periods on year units, age ranges/bounds, annotated son/daughter relationships, unknown-sex feasible ranges, sleepout categories, dictionary domains/aliases, reserved codes, over-11 room buckets, and municipality mapping. Test text-file reads and writes explicitly use UTF-8. No cached Python bytecode belongs in the commit.

A separate smoke check using the supplied, unchanged pipeline entry point and supporting modules passed grouping followed by validation and `pipeline.run validate` manifest reruns. It verified native codebook flags, unchanged cached transcript bytes, and no duplicate review entries. The standalone consistent example also produces no flags. These checks do not execute image processing or paid transcription, or substitute for the repository's CI.
