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
| `test_answering_a_foreign_card_is_always_wrong` | Answering a page whose truth is `other` counts as wrong, while `REVIEW` is accepted. |
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


