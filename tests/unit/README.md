# Unit tests

Pure functions and CLI/config option resolution, exercised directly — no orchestrator,
no fixture images, no disk I/O beyond argparse. Every image is generated in-memory
with numpy/cv2; nothing here reads a file.

**9 tests. Runs in ~3s.**

```bash
pytest tests-v2/unit
```

## `test_preprocess.py` — 9 tests

Skew estimation and CLI/config option handling for `pipeline.preprocess`.

| Test  | What it checks |
|---|---|
| `test_estimate_skew_angle_detects_known_tilt`  | Synthetic lines tilted 4° are detected to within 1° (magnitude only). |
| `test_deskew_uses_agreeing_card_edges_and_corrects_direction`  | Detection uses the `card_edges` method, picks the right sign, and residual tilt after `deskew()` is under 0.25°. |
| `test_boundary_skew_rejects_blank_and_single_edge`  | A blank image and a single detected edge both return `None` — not enough evidence to guess. |
| `test_boundary_skew_rejects_disagreeing_edges`  | Two edges at conflicting angles return `None` rather than an unreliable average. |
| `test_defaults_and_cli_overrides`  | Precedence order: defaults < config values < command-line flags. |
| `test_invalid_cli_options`  | A bad number and conflicting colour modes both exit with argparse code 2. |

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