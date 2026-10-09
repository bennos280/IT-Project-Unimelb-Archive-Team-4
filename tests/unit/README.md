# Unit tests

**158 tests. Runs in ~16s.**

```bash
uv run pytest tests/unit
```

## `test_preprocess.py` — 25 tests

preprocessing steps tests and CLI/config option handling for `backend.pipeline.preprocess`.

| Test  | What it checks |
|---|---|
| `test_estimate_skew_angle_detects_known_tilt`  | Synthetic lines tilted 4° are detected to within 1° (magnitude only). |
| `test_deskew_uses_agreeing_card_edges_and_corrects_direction`  | Detection uses the `card_edges` method, picks the right sign, and residual tilt after `deskew()` is under 0.25°. |
| `test_boundary_skew_rejects_blank_and_single_edge`  | A blank image and a single detected edge both return `None` — not enough evidence to guess. |
| `test_boundary_skew_rejects_disagreeing_edges`  | Two edges at conflicting angles return `None` rather than an unreliable average. |
| `test_defaults_and_cli_overrides`  | Precedence order: defaults < config values < command-line flags. |
| `test_invalid_cli_options`  | A bad number and conflicting colour modes both exit with argparse code 2. |
| `test_single_image_without_output_writes_beside_the_source` | Without `--output`, the preprocessed image is written beside the source with a `_preprocessed` suffix, while the original remains unchanged. |
| `test_single_image_with_output_keeps_the_original_filename` | With `--output`, the processed image keeps its original filename rather than adding the `_preprocessed` suffix. |
| `test_report_records_the_settings_that_were_actually_used` | The JSON report correctly records the selected grayscale, binarize, colour, crop, deskew, and adaptive-C settings, along with the report schema version and page mode. |
| `test_a_non_image_file_is_a_usage_error` | Unsupported single-file extensions such as `.txt`, `.pdf`, and `.zip` raise an argparse usage error with exit code 2. |
| `test_a_missing_input_path_is_a_usage_error` | A nonexistent input path is rejected as a usage error with exit code 2 before processing starts. |
| `test_folder_mode_processes_every_image_including_subfolders` | Folder input recursively processes images in subfolders and preserves the input directory structure in the output directory. |
| `test_folder_mode_ignores_files_it_has_already_produced` | Files ending in `_preprocessed` are skipped so previously generated outputs are not processed again. |
| `test_folder_mode_ignores_unsupported_file_types` | Unsupported files such as `.txt` and `.pdf` inside a folder are quietly ignored while supported images are processed. |
| `test_folder_with_no_supported_images_is_a_usage_error` | An empty or image-free folder raises a usage error with exit code 2 instead of producing an empty report. |
| `test_output_folder_inside_the_input_folder_is_rejected` | An output directory that is the input folder or nested inside it is rejected with exit code 2 to prevent outputs from being processed as new inputs. |
| `test_an_existing_report_stops_the_run_before_any_processing` | An existing preprocessing report prevents the run from overwriting it and ensures no output image is created. |
| `test_one_bad_image_does_not_stop_the_others_but_changes_the_exit_code` | A failed image does not stop the remaining images from processing; the failure is recorded in the report and the command returns exit code 1. |
| `test_invalid_config_value_becomes_a_usage_error` | An invalid `PREPROCESS_*` configuration value is converted into an argparse usage error with exit code 2 rather than producing a traceback. |
| `test_progress_lines_name_each_file_and_its_detected_skew` | Console progress output names each processed file, shows its mode and detected skew, and includes the final report location. |

## `test_identify.py` — 15 tests

Unit tests for scoring, bookkeeping, fingerprint storage, page identification, and model-result handling in `backend.pipeline.identify`.

| Test | What it checks |
|---|---|
| `test_score_counts_correct_wrong_and_abstained_separately` | Correctly separates answered pages, wrong answers, and `REVIEW` abstentions when calculating the score. |
| `test_abstaining_is_never_counted_as_wrong` | `REVIEW` answers are treated as abstentions rather than mistakes, reducing coverage but not increasing the wrong count. |
| `test_answering_a_other_card_is_always_wrong` | Answering a page whose truth is `other` counts as wrong, while `REVIEW` is accepted. |
| `test_per_class_counts_answered_out_of_total_for_each_truth` | `per_class` correctly records answered and total counts for each truth label and keeps the labels sorted. |
| `test_score_of_an_empty_set_is_safe` | An empty input produces zero total pages and zero coverage without causing a division-by-zero error. |
| `test_coverage_is_the_answered_fraction` | `Score.coverage` correctly calculates the fraction of pages that received an answer. |
| `test_passes_requires_zero_wrong_and_enough_coverage` | `Score.passes()` requires both zero wrong answers and coverage at or above `MIN_COVERAGE`, including the exact boundary. |
| `test_summary_lists_the_headline_numbers_and_every_mistake` | The score summary reports the main statistics, wrong pages, and relevant `REVIEW` pages while excluding acceptable abstentions on other pages. |
| `test_labelled_pages_takes_the_truth_from_the_top_folder` | Page labels are taken from the top-level class folder regardless of deeper subfolder structure, while non-image files are excluded. |
| `test_labelled_pages_is_deterministic_in_order` | `labelled_pages()` consistently returns pages in sorted order so page paths and their truth labels remain aligned. |
| `test_stored_tells_you_to_train_when_a_fingerprint_is_missing` | A missing fingerprint raises `FileNotFoundError` with a message identifying the missing pages and the required training command. |
| `test_stored_loads_fingerprints_by_image_content_not_filename` | Fingerprints are retrieved using image content hashes rather than filenames, with cached `float16` values converted to `float32`. |
|`test_stored_computes_and_saves_missing_fingerprints`| Missing fingerprint and compute=True then it should  correctly compute and save it |
| `test_identify_pages_on_an_empty_list_does_not_load_the_model` | An empty page list immediately returns an empty result without attempting to load the model. |
| `test_identify_pages_returns_plain_python_types` | Identification results use ordinary Python `str` and `float` values that can be serialized with `json.dumps`, rather than NumPy scalar types. |
| `test_min_coverage_is_the_documented_threshold` | `MIN_COVERAGE` remains fixed at 0.5 and the supported label set remains exactly `blank`, `coded`, `main`, and `notes`. |


## `test_model.py` — 19 tests

Unit tests for the classifier, prediction safety gates, model persistence, threshold selection, fitting, and cross-validation in `backend.pipeline.identify.classifier`.

| Test | What it checks |
|---|---|
| `test_unit_scales_every_row_to_length_one` | Each input row is independently normalised to unit length, preserving direction for cosine-distance calculations. |
| `test_unit_does_not_divide_by_zero_on_an_all_zero_row` | An all-zero input row remains zero and does not produce NaN values during normalisation. |
| `test_scores_returns_a_label_a_probability_and_a_distance_per_row` | `scores()` returns a predicted label, softmax confidence, and KNN distance for each input row. |
| `test_scores_distance_grows_as_a_page_moves_away_from_the_training_set` | A fingerprint farther from the training references receives a larger distance, allowing the distance gate to identify unfamiliar cards. |
| `test_scores_uses_at_most_knn_neighbours` | The distance calculation uses only the configured number of nearest neighbours rather than all training references. |
| `test_predict_answers_only_when_both_gates_pass` | A page is labelled only when both the confidence threshold and distance threshold are satisfied; otherwise it returns `REVIEW`. |
| `test_predict_treats_the_thresholds_as_inclusive_boundaries` | Confidence exactly equal to the probability threshold and distance exactly equal to the distance threshold are both accepted. |
| `test_predict_with_impossible_thresholds_abstains_on_everything` | Thresholds of probability 1.0 and distance 0.0 cause the model to return `REVIEW` for every page rather than guessing. |
| `test_save_and_load_round_trip_preserves_predictions` | Saving and loading a model preserves its predictions, classes, thresholds, and reference data types. |
| `test_save_returns_the_path_it_wrote` | `save()` returns the destination path and successfully creates the model weights file. |
| `test_load_missing_weights_names_the_fix` | Loading a missing weights file raises `FileNotFoundError` with instructions to run `survey train`. |
| `test_choose_thresholds_excludes_every_wrong_answer` | Threshold selection prevents rows that would be incorrectly classified from being answered while retaining confident, correct rows. |
| `test_choose_thresholds_treats_others_as_never_answerable` | Pages with truths outside the supported labels are treated as invalid answers and excluded by the selected thresholds. |
| `test_choose_thresholds_applies_the_distance_safety_margin` | The selected distance threshold is reduced by `DIST_MARGIN` before being returned. |
| `test_choose_thresholds_with_no_correct_rows_answers_nothing` | When every training row would be classified incorrectly, threshold selection keeps the safest values so that nothing is answered. |
| `test_fit_learns_separable_classes_and_stores_the_training_set` | `Model.fit()` correctly learns clearly separated classes and stores a unit-normalised reference for every training page. |
| `test_fit_trains_the_head_only_on_known_labels` | other cards are not added as a predictable class; instead, they are returned as `REVIEW`. |
| `test_cross_validate_scores_every_row_including_others` | Cross-validation produces scores for every row, including other cards, while known separable pages receive their correct labels. |
| `test_regularisation_constant_is_the_documented_value` | The configured model constants remain fixed at the documented values for regularisation, KNN neighbours, distance margin, supported labels, and `REVIEW`. |


## `test_common.py` — 12 tests

Unit tests for `.env` configuration parsing and page-image discovery in `backend/common.py`, including required settings, defaults, comment handling, duplicate keys, supported image formats, and directory traversal behaviour.

| Test | What it checks |
|---|---|
| `test_settings_reads_keys_and_defaults_output` | Reads the required `DATA`, `MODEL`, and `EFFORT` settings from `.env` and uses `"output"` as the default when `OUTPUT` is not provided. |
| `test_settings_strips_comments_whitespace_and_bom` | Removes surrounding whitespace, ignores comments and lines without `=`, and handles a UTF-8 BOM when reading `.env` files. |
| `test_settings_keeps_hash_when_not_preceded_by_space` | Preserves `#` characters inside values when they are not preceded by a space, rather than treating them as comments. |
| `test_settings_exits_when_env_file_is_missing` | Raises `SystemExit` with a clear message when the `.env` file does not exist. |
| `test_settings_exits_when_a_required_key_is_missing` | Verifies that each required setting (`DATA`, `MODEL`, and `EFFORT`) causes `SystemExit` when it is missing.(runs 3 times) |
| `test_settings_treats_an_empty_value_as_missing` | Treats a required setting with an empty value, such as `DATA=`, as missing and exits with an appropriate error. |
| `test_settings_last_duplicate_key_wins` | Confirms that when the same `.env` key appears multiple times, the final value overwrites the earlier value. |
| `test_find_images_returns_only_supported_suffixes_sorted` | Finds only `.jpg`, `.jpeg`, and `.png` files and returns them in sorted order. |
| `test_find_images_is_not_recursive_and_ignores_subfolders` | Only searches the specified directory and ignores images located inside subdirectories. |
| `test_find_images_returns_empty_list_for_a_folder_with_no_pages` | Returns an empty list rather than raising an error when a directory contains no supported page images. |


## `test_transcribe.py` — 27 tests

unit tests for `backend.pipeline.transcribe.transcribe`, covering schema generation, CLI handling, Claude/Codex engine behaviour, engine selection, response processing, and transcription metadata.

| Test | What it checks |
|---|---|
| `test_schemafor_turns_a_flat_template_into_an_object_schema` | Converts a flat template into an object schema where every field is required and accepts strings or null, with no additional properties. |
| `test_schemafor_preserves_key_order` | Preserves the original template key order in the schema's required fields. |
| `test_schemafor_handles_lists_by_describing_their_first_item` | Converts template lists into arrays whose item schema matches the first example element. |
| `test_schemafor_handles_an_empty_list_without_crashing` | Handles an empty template list without raising an `IndexError`, falling back to string-or-null items. |
| `test_schemafor_recurses_through_nested_structures` | Correctly builds schemas for nested objects and lists at multiple levels. |
| `test_schemafor_maps_every_scalar_to_string_or_null` | Maps every scalar template value, including `None`, strings, numbers, and booleans, to a string-or-null schema. |
| `test_schema_for_output_is_json_serialisable` | Ensures the generated schema can be serialised with `json.dumps()` before being passed to the CLI. |
| `test_run_cli_turns_a_hang_into_a_readable_exit` | Converts a CLI timeout into a readable exit message instead of exposing a raw `TimeoutExpired` traceback. |
| `test_run_cli_explains_a_missing_cli_instead_of_crashing` | Converts a missing Claude/Codex executable into a clear "CLI not found" message. |
| `test_run_cli_passes_capture_and_timeout_settings_through` | Verifies subprocess output capture, timeout, replacement-character decoding, working directory, and command arguments are passed correctly. |
| `test_run_claude_returns_the_structured_output_and_model_name` | Parses a successful Claude response and returns both the structured answer and the actual model version reported by the CLI. |
| `test_run_claude_builds_the_command_with_the_image_path_and_schema` | Builds the Claude command with the image path, selected model and effort, Read permission, and JSON schema arguments. |
| `test_run_claude_exits_when_the_reply_is_not_json` | Rejects non-JSON CLI output and exits with a useful message containing the raw response. |
| `test_run_claude_exits_when_the_reply_is_an_error_or_incomplete` | Rejects both explicit Claude errors and valid JSON responses missing `structured_output`. |
| `test_run_codex_reads_the_answer_from_the_output_file` | Reads and parses the JSON answer written by Codex to its `--output-last-message` file and returns the requested model name. |
| `test_run_codex_extracts_json_surrounded_by_chatter` | Extracts valid JSON from Codex output even when explanatory text appears before or after the JSON object. |
| `test_run_codex_runs_read_only_and_ephemeral` | Verifies Codex uses an ephemeral session, ignores user configuration, runs with a read-only sandbox, and receives the image path. |
| `test_run_codex_exits_on_a_bad_exit_code_or_a_missing_answer_file` | Rejects either a non-zero Codex exit code or a missing output file instead of treating the result as a valid empty transcription. |
| `test_run_codex_exits_when_the_answer_file_holds_no_json` | Rejects an output file containing prose without a JSON object and exits with a clear message. |
| `test_transcribe_picks_the_engine_from_the_model_name` | Selects Codex for `gpt-*` models and Claude for documented non-GPT models, recording the selected engine in the result. |
| `test_transcribe_honours_an_explicit_engine_override` | An explicit `engine="claude"` override takes precedence over the automatic engine selected from the model name. |
| `test_transcribe_rejects_an_unknown_engine` | Rejects an invalid engine name immediately and reports that the valid choices are Claude or Codex. |
| `test_transcribe_stamps_every_answer_with_provenance` | Adds engine, actual model version, effort, and elapsed seconds to every transcription result. |
| `test_transcribe_falls_back_to_the_requested_model_name` | Uses the requested model name when the selected engine does not report an actual model version. |
| `test_transcribe_unwraps_a_notes_answer_returned_as_a_json_string` | Repairs notes responses where the complete transcription object has incorrectly been returned as a JSON string inside the `text` field. |
| `test_transcribe_leaves_ordinary_text_untouched` | Leaves normal text and invalid JSON-looking text unchanged when the notes JSON-unwrapping repair does not apply. |
| `test_transcribe_sends_the_template_inside_the_prompt` | Includes the page template alongside `prompt.txt` in the model prompt and passes the same template to the transcription engine. |
| `test_transcribe_defaults_model_and_effort_from_env` | When model and effort are omitted, uses the corresponding `MODEL` and `EFFORT` values from the environment configuration. |


## `test_transcribe_score.py` — 31 tests

unit tests for `backend.pipeline.transcribe.score`, covering JSON flattening, value normalisation, scorable fields, page-level scoring, invented values, character similarity, and leaderboard reporting.

| Test | What it checks |
|---|---|
| `test_flatten_turns_nested_objects_into_dotted_paths` | Flattens nested objects into dotted paths so individual fields can be compared separately. |
| `test_flatten_indexes_list_items_by_position` | Flattens list items using positional paths such as `notes[0]` and `notes[1]`. |
| `test_flatten_handles_lists_of_objects` | Correctly combines list indexing and nested object paths, such as `annotations[0].raw`. |
| `test_flatten_keeps_none_and_empty_values` | Preserves `None` and empty-string values so blank fields can be distinguished from missing fields and invented values can be detected. |
| `test_flatten_of_a_bare_value_uses_an_empty_key` | Handles a scalar at the top level by representing it with an empty key rather than raising an error. |
| `test_norm_treats_these_as_the_same_answer` | Treats differences in case, surrounding whitespace, repeated spaces, newlines, and `None` versus an empty string as equivalent. |
| `test_norm_keeps_punctuation_because_it_carries_meaning` | Preserves meaningful punctuation so values such as `30/-` versus `30/` and `St.` versus `St` remain different. |
| `test_norm_converts_non_strings_before_comparing` | Converts non-string values such as numbers and booleans to strings before comparison. |
| `test_provenance_stamps_are_not_graded` | Excludes engine, model, effort, seconds, and other provenance stamps from scoring. |
| `test_annotation_paths_are_excluded_from_grading` | Excludes fields under `annotations[...]` from grading while still grading normal fields containing the word "annotation". |
| `test_ordinary_card_fields_are_graded` | Confirms ordinary card fields and nested household fields are included in scoring. |
| `test_score_page_counts_exact_matches_as_hits` | Counts fields whose normalised answers exactly match the truth as hits. |
| `test_score_page_lists_the_fields_that_were_missed` | Records the paths of fields where the transcription does not match the truth. |
| `test_score_page_only_grades_fields_the_card_actually_has` | Excludes blank truth fields from the graded total while tracking them separately as blanks. |
| `test_score_page_reports_invented_values_for_blank_fields` | Detects and records values supplied by the model for fields that were blank on the original card. |
| `test_score_page_does_not_count_a_blank_answer_as_invented` | Confirms that correctly leaving a blank field blank is not treated as an invented value. |
| `test_score_page_treats_a_missing_field_as_a_miss_not_a_crash` | Treats an omitted answer field as a miss rather than raising an exception. |
| `test_score_page_character_similarity_rewards_near_misses` | Records character-level similarity so exact matches, near-misses, and substantially different answers can be distinguished. |
| `test_score_page_ignores_stamps_and_annotations_end_to_end` | Verifies end-to-end that provenance stamps and annotation fields do not affect the graded totals while timing information is retained. |
| `test_score_page_grades_nested_structures_field_by_field` | Scores nested objects field by field, allowing partial credit when some nested fields are correct. |
| `test_score_page_of_an_empty_key_is_zero_not_an_error` | Handles a truth record with no gradeable fields by returning zero totals without dividing or crashing. |
| `test_main_exits_when_there_are_no_results_yet` | When no transcription results exist, exits with a clear message explaining that results must be generated first. |
| `test_main_prints_a_row_per_model_and_page_kind` | Prints a leaderboard row for each model and page type with the correct exact-match percentage and hit/total fraction. |
| `test_main_counts_pages_with_no_answer_as_missing` | Counts truth pages without corresponding model answers as missing rather than silently excluding them from the results. |
| `test_main_skips_a_kind_with_no_answers_at_all` | Omits page types that the model never attempted instead of displaying them as zero-score results. |


## `test_identify_fingerprint.py` — 3 tests

Unit tests for `backend.pipeline.identify.fingerprint`, covering empty input, view construction, and quadrant cropping. The CLIP encoder (`_clip`) is mocked throughout, so these run in milliseconds with no model loaded.

| Test | What it checks |
|---|---|
| `test_fingerprint_empty_list` | An empty input returns a `(0, 0)` array, and the CLIP encoder is never called. |
| `test_fingerprint_builds_5_correctly_sized_views` | Each input image produces exactly 5 views, all resized to `(SIZE, SIZE)` before being passed to CLIP. |
| `test_fingerprint_crops_correct_quadrants` | The four quadrant views are cropped from the correct regions of the source image, each preserving a uniform colour. |

## `test_backend_api.py` — 11 tests
|Test|What it checks|
|---|---|
|`test_get_survey_not_found`|Returns HTTP 404 if requested survey id is not in database.|
|`test_get_survey_success`|After seeding database with sample survey, successfully returns data from the requested survey.|
|`test_get_reviewers_empty`|Returns empty list without crashing if there are no reviewers in database.|
|`test_create_reviewer_success`|Successfully saves a reviewer into database.|
|`test_create_reviewer_empty_name`|Returns HTTP 404 if requested reviewer to save has no name given.|
|`test_get_reviews_empty_survey`|Returns empty list without crashing if there is no review data in database.
|`test_get_reviews_latest`|Returns latest review if there is more than one on the same field.|
|`test_save_reviews_outdated_revision`|Rejects request to save an outdated review on a page.|
|`test_save_reviews_missing_revision`|Rejects request to save a review with revision no >1 than current revision no of the page.|
|`test_save_reviews_no_reviewer`|Rejects request to save a review if reviewer is not in database.|
|`test_save_reviews_success`|Successfully saves a review into database.|