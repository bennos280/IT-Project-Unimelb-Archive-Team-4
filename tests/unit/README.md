# Unit tests

Pure functions and CLI/config option resolution, exercised directly — no orchestrator,
no fixture images, no disk I/O beyond argparse. Every image is generated in-memory
with numpy/cv2; nothing here reads a file.

**9 tests. Runs in ~3s.**

```bash
pytest tests-v2/unit
```

## `test_preprocess.py` — 23 tests

preprocessing steps tests and CLI/config option handling for `pipeline.preprocess`.

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

Unit tests for scoring, bookkeeping, fingerprint storage, page identification, and model-result handling in `pipeline.identify`.

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
| `test_identify_pages_on_an_empty_list_does_not_load_the_model` | An empty page list immediately returns an empty result without attempting to load the model. |
| `test_identify_pages_returns_plain_python_types` | Identification results use ordinary Python `str` and `float` values that can be serialized with `json.dumps`, rather than NumPy scalar types. |
| `test_min_coverage_is_the_documented_threshold` | `MIN_COVERAGE` remains fixed at 0.5 and the supported label set remains exactly `blank`, `coded`, `main`, and `notes`. |


## `test_model.py` — 19 tests

Unit tests for the classifier, prediction safety gates, model persistence, threshold selection, fitting, and cross-validation in `pipeline.identify.model`.

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

Unit tests for `.env` configuration parsing and page-image discovery in `pipeline/common.py`, including required settings, defaults, comment handling, duplicate keys, supported image formats, and directory traversal behaviour.

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