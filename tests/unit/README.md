# Unit tests

```bash
uv run pytest tests/unit
```

## `test_preprocess.py`

The image steps of `backend.pipeline.preprocess` (skew detection, straightening, card edges), which make the review screen's cleaned-up view.

| Test                                                          | What it checks                                                                                                   |
| ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `test_estimate_skew_angle_detects_known_tilt`                 | Synthetic lines tilted 4° are detected to within 1° (magnitude only).                                            |
| `test_deskew_uses_agreeing_card_edges_and_corrects_direction` | Detection uses the `card_edges` method, picks the right sign, and residual tilt after `deskew()` is under 0.25°. |
| `test_boundary_skew_rejects_blank_and_single_edge`            | A blank image and a single detected edge both return `None` — not enough evidence to guess.                      |
| `test_boundary_skew_rejects_disagreeing_edges`                | Two edges at conflicting angles return `None` rather than an unreliable average.                                 |

## `test_identify.py`

Unit tests for scoring, bookkeeping, fingerprint storage, page identification, and model-result handling in `backend.pipeline.identify`.

| Test                                                           | What it checks                                                                                                                                 |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_identify_pages_sorts_with_the_weights_it_is_given`       | `identify_pages()` loads the weights it is given (a retrained model), or the shipped ones when given none.                                     |
| `test_score_counts_correct_wrong_and_abstained_separately`     | Correctly separates answered pages, wrong answers, and `REVIEW` abstentions when calculating the score.                                        |
| `test_abstaining_is_never_counted_as_wrong`                    | `REVIEW` answers are treated as abstentions rather than mistakes, reducing coverage but not increasing the wrong count.                        |
| `test_answering_a_other_card_is_always_wrong`                  | Answering a page whose truth is `other` counts as wrong, while `REVIEW` is accepted.                                                           |
| `test_per_class_counts_answered_out_of_total_for_each_truth`   | `per_class` correctly records answered and total counts for each truth label and keeps the labels sorted.                                      |
| `test_score_of_an_empty_set_is_safe`                           | An empty input produces zero total pages and zero coverage without causing a division-by-zero error.                                           |
| `test_coverage_is_the_answered_fraction`                       | `Score.coverage` correctly calculates the fraction of pages that received an answer.                                                           |
| `test_passes_requires_zero_wrong_and_enough_coverage`          | `Score.passes()` requires both zero wrong answers and coverage at or above `MIN_COVERAGE`, including the exact boundary.                       |
| `test_summary_lists_the_headline_numbers_and_every_mistake`    | The score summary reports the main statistics, wrong pages, and relevant `REVIEW` pages while excluding acceptable abstentions on other pages. |
| `test_labelled_pages_takes_the_truth_from_the_top_folder`      | Page labels are taken from the top-level class folder regardless of deeper subfolder structure, while non-image files are excluded.            |
| `test_labelled_pages_is_deterministic_in_order`                | `labelled_pages()` consistently returns pages in sorted order so page paths and their truth labels remain aligned.                             |
| `test_stored_tells_you_to_train_when_a_fingerprint_is_missing` | A missing fingerprint raises `FileNotFoundError` with a message identifying the missing pages and the required training command.               |
| `test_stored_loads_fingerprints_by_image_content_not_filename` | Fingerprints are retrieved using image content hashes rather than filenames, with cached `float16` values converted to `float32`.              |
| `test_stored_computes_and_saves_missing_fingerprints`          | With `compute=True`, a page whose fingerprint isn't stored yet is fingerprinted, returned, and saved as one `float16` `.npy` file.             |
| `test_identify_pages_on_an_empty_list_does_not_load_the_model` | An empty page list immediately returns an empty result without attempting to load the model.                                                   |
| `test_identify_pages_returns_plain_python_types`               | Identification results use ordinary Python `str` and `float` values that can be serialized with `json.dumps`, rather than NumPy scalar types.  |
| `test_min_coverage_is_the_documented_threshold`                | `MIN_COVERAGE` remains fixed at 0.5 and the supported label set remains exactly `blank`, `coded`, `main`, and `notes`.                         |

## `test_identify_classifier.py`

Unit tests for the classifier, prediction safety gates, model persistence, threshold selection, fitting, and cross-validation in `backend.pipeline.identify.classifier`.

| Test                                                                    | What it checks                                                                                                                                            |
| ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_unit_scales_every_row_to_length_one`                              | Each input row is independently normalised to unit length, preserving direction for cosine-distance calculations.                                         |
| `test_unit_does_not_divide_by_zero_on_an_all_zero_row`                  | An all-zero input row remains zero and does not produce NaN values during normalisation.                                                                  |
| `test_scores_returns_a_label_a_probability_and_a_distance_per_row`      | `scores()` returns a predicted label, softmax confidence, and KNN distance for each input row.                                                            |
| `test_scores_distance_grows_as_a_page_moves_away_from_the_training_set` | A fingerprint farther from the training references receives a larger distance, allowing the distance gate to identify unfamiliar cards.                   |
| `test_scores_uses_at_most_knn_neighbours`                               | The distance calculation uses only the configured number of nearest neighbours rather than all training references.                                       |
| `test_predict_answers_only_when_both_gates_pass`                        | A page is labelled only when both the confidence threshold and distance threshold are satisfied; otherwise it returns `REVIEW`.                           |
| `test_predict_treats_the_thresholds_as_inclusive_boundaries`            | Confidence exactly equal to the probability threshold and distance exactly equal to the distance threshold are both accepted.                             |
| `test_predict_with_impossible_thresholds_abstains_on_everything`        | Thresholds of probability 1.0 and distance 0.0 cause the model to return `REVIEW` for every page rather than guessing.                                    |
| `test_save_and_load_round_trip_preserves_predictions`                   | Saving and loading a model preserves its predictions, classes, thresholds, and reference data types.                                                      |
| `test_save_returns_the_path_it_wrote`                                   | `save()` returns the destination path and successfully creates the model weights file.                                                                    |
| `test_load_missing_weights_names_the_fix`                               | Loading a missing weights file raises `FileNotFoundError` with instructions to run `survey train`.                                                        |
| `test_choose_thresholds_excludes_every_wrong_answer`                    | Threshold selection prevents rows that would be incorrectly classified from being answered while retaining confident, correct rows.                       |
| `test_choose_thresholds_treats_others_as_never_answerable`              | Pages with truths outside the supported labels are treated as invalid answers and excluded by the selected thresholds.                                    |
| `test_choose_thresholds_applies_the_distance_safety_margin`             | The selected distance threshold is reduced by `DIST_MARGIN` before being returned.                                                                        |
| `test_choose_thresholds_with_no_correct_rows_answers_nothing`           | When every training row would be classified incorrectly, threshold selection keeps the safest values so that nothing is answered.                         |
| `test_fit_learns_separable_classes_and_stores_the_training_set`         | `Model.fit()` correctly learns clearly separated classes and stores a unit-normalised reference for every training page.                                  |
| `test_fit_trains_the_head_only_on_known_labels`                         | other cards are not added as a predictable class; instead, they are returned as `REVIEW`.                                                                 |
| `test_cross_validate_scores_every_row_including_others`                 | Cross-validation produces scores for every row, including other cards, while known separable pages receive their correct labels.                          |
| `test_regularisation_constant_is_the_documented_value`                  | The configured model constants remain fixed at the documented values for regularisation, KNN neighbours, distance margin, supported labels, and `REVIEW`. |

## `test_common.py`

Unit tests for the fixed data and output folders (`settings()`, which ignores any `.env`) and page-image discovery in `backend/common.py`, including supported image formats and directory traversal behaviour.

| Test                                                             | What it checks                                                                                                                                                                |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_settings_gives_the_fixed_folders`                          | `settings()` is always `{"DATA": "data", "OUTPUT": "output"}`.                                                                                                                |
| `test_settings_ignores_any_env_file`                             | A `.env` in the project (folders, model, effort, junk lines) changes nothing and never stops the app.                                                                         |
| `test_settings_works_with_no_env_file`                           | No `.env` is needed: `settings()` does not exit.                                                                                                                              |
| `test_find_images_returns_only_supported_suffixes_sorted`        | Finds only `.jpg`, `.jpeg`, and `.png` files and returns them in sorted order.                                                                                                |
| `test_find_images_is_not_recursive_and_ignores_subfolders`       | Only searches the specified directory and ignores images located inside subdirectories.                                                                                       |
| `test_find_images_returns_empty_list_for_a_folder_with_no_pages` | Returns an empty list rather than raising an error when a directory contains no supported page images.                                                                        |

## `test_transcribe.py`

unit tests for `backend.pipeline.transcribe.transcribe`, covering schema generation, CLI handling, Claude/Codex provider behaviour, response processing, and transcription metadata.

| Test                                                                | What it checks                                                                                                                                                                                                                         |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_transcribe_reads_with_the_texts_it_is_given`                  | Given a job's texts (the db's newest prompt and templates), `transcribe()` reads with them instead of the files, for any page type they have a template for; Windows line endings in the prompt reach the model as plain ones.         |
| `test_schemafor_turns_a_flat_template_into_an_object_schema`        | Converts a flat template into an object schema where every field is required and accepts strings or null, with no additional properties.                                                                                               |
| `test_schemafor_preserves_key_order`                                | Preserves the original template key order in the schema's required fields.                                                                                                                                                             |
| `test_schemafor_handles_lists_by_describing_their_first_item`       | Converts template lists into arrays whose item schema matches the first example element.                                                                                                                                               |
| `test_schemfor_handles_an_empty_list_without_crashing`              | Handles an empty template list without raising an `IndexError`, falling back to string-or-null items.                                                                                                                                  |
| `test_schemafor_recurses_through_nested_structures`                 | Correctly builds schemas for nested objects and lists at multiple levels.                                                                                                                                                              |
| `test_schemafor_maps_every_scalar_to_string_or_null`                | Maps every scalar template value, including `None`, strings, numbers, and booleans, to a string-or-null schema.                                                                                                                        |
| `test_schema_for_output_is_json_serialisable`                       | Ensures the generated schema can be serialised with `json.dumps()` before being passed to the CLI.                                                                                                                                     |
| `test_run_cli_turns_a_hang_into_a_readable_exit`                    | Converts a CLI timeout into a readable exit message instead of exposing a raw `TimeoutExpired` traceback.                                                                                                                              |
| `test_run_cli_explains_a_missing_cli_instead_of_crashing`           | Converts a missing Claude/Codex executable into a clear "CLI not found" message.                                                                                                                                                       |
| `test_run_cli_passes_capture_and_timeout_settings_through`          | Verifies subprocess output capture, timeout, replacement-character decoding, working directory, and command arguments are passed correctly.                                                                                            |
| `test_run_claude_returns_the_structured_output`                     | Parses a successful Claude response and returns the structured answer.                                                                                                                                                                 |
| `test_run_claude_builds_the_command_with_the_image_path_and_schema` | Builds the Claude command with the image path, selected model and effort, Read as the only tool, none of the user's MCP servers, `--safe-mode` (none of their CLAUDE.md, plugins, hooks, skills or memory), and JSON schema arguments. |
| `test_run_claude_exits_when_the_reply_is_not_json`                  | Rejects non-JSON CLI output and exits with a useful message containing the raw response.                                                                                                                                               |
| `test_run_claude_exits_when_the_reply_is_an_error_or_incomplete`    | Rejects both explicit Claude errors and valid JSON responses missing `structured_output`.                                                                                                                                              |
| `test_run_codex_reads_the_answer_from_the_output_file`              | Reads and parses the JSON answer written by Codex to its `--output-last-message` file.                                                                                                                                                 |
| `test_run_codex_extracts_json_surrounded_by_chatter`                | Extracts valid JSON from Codex output even when explanatory text appears before or after the JSON object.                                                                                                                              |
| `test_run_codex_runs_read_only_and_ephemeral`                       | Verifies Codex uses an ephemeral session, ignores user configuration, runs with a read-only sandbox, and receives the image path.                                                                                                      |
| `test_run_codex_exits_on_a_bad_exit_code_or_a_missing_answer_file`  | Rejects either a non-zero Codex exit code or a missing output file instead of treating the result as a valid empty transcription.                                                                                                      |
| `test_run_codex_exits_when_the_answer_file_holds_no_json`           | Rejects an output file containing prose without a JSON object and exits with a clear message.                                                                                                                                          |
| `test_transcribe_reads_with_the_provider_it_is_given`               | 2 cases: `PROVIDER` picks the CLI (`claude` or `codex`) whatever the model is called, and the answer is stamped with it; an OpenAI `o3` goes to Codex though it isn't named gpt-\*.                                                    |
| `test_transcribe_refuses_an_unknown_provider`                       | A provider other than `claude` or `codex` stops with "PROVIDER must be claude or codex".                                                                                                                                               |
| `test_transcribe_stamps_every_answer_with_provenance`               | Adds provider, model and effort (as given, else the choice saved on the Settings page) and elapsed seconds to every transcription result.                                                                                                                        |
| `test_transcribe_unwraps_a_notes_answer_returned_as_a_json_string`  | Repairs notes responses where the complete transcription object has incorrectly been returned as a JSON string inside the `text` field.                                                                                                |
| `test_transcribe_leaves_ordinary_text_untouched`                    | Leaves normal text and invalid JSON-looking text unchanged when the notes JSON-unwrapping repair does not apply.                                                                                                                       |
| `test_transcribe_sends_the_template_inside_the_prompt`              | Includes the page template alongside `prompt.txt` in the model prompt and passes the same template to the provider's model call.                                                                                                       |
| `test_transcribe_without_a_choice_uses_the_one_saved_on_the_settings_page` | When provider, model and effort are omitted, uses the choice saved in the database. |
| `test_transcribe_with_a_full_choice_needs_nothing_saved` | A full explicit choice never reads the database. |
| `test_transcribe_without_a_choice_and_nothing_saved_exits_with_the_message` | With nothing saved (or only part of a choice given) it exits with "Choose a transcription model on the Settings page first." and calls no model. |
| `test_transcribe_with_a_db_that_has_no_settings_table_yet_exits_with_the_message` | An older database without the `app_settings` table gives the same message. |

## `test_transcription_defaults.py`

The transcription choice saved on the Settings page (no default), and everything that starts a transcription without a choice of its own.

| Test | What it checks |
| --- | --- |
| `test_nothing_saved_is_none_and_so_is_part_of_a_choice` | The saved choice is `None` until all three of provider, model and effort are saved. |
| `test_nothing_is_configured_until_a_choice_is_saved` | `GET /transcription-models` gives `configured: null` until then. |
| `test_put_saves_all_three_trimmed_and_returns_the_choice` / `test_there_is_no_reset` | `PUT /transcription-defaults` saves and returns exactly provider, model and effort; `DELETE` no longer exists. |
| `test_folders_are_the_data_and_output_folders_inside_the_project` | `GET /folders` gives the absolute `data` and `output` folders under the project. |
| `test_a_job_without_a_full_choice_and_nothing_saved_is_refused` | `POST /jobs` without a full choice and nothing saved is 409 "Choose a transcription model on the Settings page first." and queues nothing. |
| `test_a_job_with_an_explicit_choice_works_with_nothing_saved` | An explicit choice in the payload needs nothing saved. |
| `test_a_job_started_without_a_choice_uses_the_saved_one` / `test_a_job_with_part_of_a_choice_takes_the_rest_from_the_saved_one` | The saved choice fills whatever the payload leaves out. |
| `test_a_page_transcription_cannot_leave_out_its_choice` | `POST /page-transcription` requires provider, model and effort (422). |
| `test_a_bundle_job_with_no_choice_runs_with_the_saved_one` | The worker gives the pipeline the job's own fields, else the saved choice. |
| `test_a_bundle_job_without_a_full_choice_and_nothing_saved_fails_with_the_message` / `test_a_page_job_with_no_choice_and_nothing_saved_fails_with_the_message` | A job with a missing field and nothing saved is marked failed with the message, and no model or pipeline runs. |

## `test_identify_fingerprint.py`

Unit tests for `backend.pipeline.identify.fingerprint`, covering empty input, view construction, and quadrant cropping. The CLIP encoder (`_clip`) is mocked throughout, so these run in milliseconds with no model loaded.

| Test                                              | What it checks                                                                                                      |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `test_fingerprint_empty_list`                     | An empty input returns a `(0, 0)` array, and the CLIP encoder is never called.                                      |
| `test_fingerprint_builds_5_correctly_sized_views` | Each input image produces exactly 5 views, all resized to `(SIZE, SIZE)` before being passed to CLIP.               |
| `test_fingerprint_crops_correct_quadrants`        | The four quadrant views are cropped from the correct regions of the source image, each preserving a uniform colour. |

## `test_backend_api.py`
|Test|What it checks|
|---|---|
|`test_get_survey_not_found`|Returns HTTP 404 ("No such record.") if the requested survey id is not in the database.|
|`test_get_survey_success`|A seeded survey comes back with its page in it, the page's field and a resident's field (`residents.20.relationship`) with their values, the page's `imageUrl` (`/pages/<page id>/image`) and no flags.|
|`test_get_reviewers_empty`|Returns an empty list without crashing if there are no reviewers in the database.|
|`test_create_reviewer_success`|Saves a reviewer and returns its id and name.|
|`test_create_reviewer_empty_name`|A name of only spaces returns HTTP 400, "Enter a reviewer name."|
|`test_create_reviewer_gives_the_next_id_and_a_known_name_its_reviewer`|A reviewer added by name gets the next free id; adding the same name again (spaces trimmed) returns that reviewer; a taken id is refused ("Reviewer id already exists."); `GET /reviewers` lists `{id, name}`.|
|`test_get_reviews_empty_survey`|A survey with no saved reviews returns `{"reviews": {}, "revisions": {}}` without crashing.|
|`test_save_reviews_outdated_revision`|Saving with revision 3 on a page already at revision 5 is refused with HTTP 409, "Revision number is outdated."; so is revision 7, more than one ahead.|
|`test_save_reviews_success`|Saving an edit made on revision 0 (sent as revision 1, the page's revision after the save) returns 200 with the page's new revision (1) and a `savedAt`; sending the same save again (a stale copy) is refused, "Revision number is outdated."|
|`test_saved_edits_come_back_with_what_they_replaced`|The page lists its fields in order (a field, a resident's field `residents.0.age`, an other child `other_children.living_elsewhere.0`, an annotation `annotations.0`). Edits to each are saved, including a field that was empty and a child cleared with `null`; a second save of the same field, by a reviewer known only by id, replaces the first; `GET /reviews` returns the latest value of each with the original it replaced, the reviewer and the same `savedAt` the save returned, and the page's revision.|
|`test_save_refuses_pages_and_fields_that_are_not_there`|Saving to a survey the page isn't in returns 404; no revision for the page, two pages in one save, or an unknown reviewer id with no name returns 400 with the reason; an edit on a field not on its page (`residents.3.age`, `annotations.²`, or one followed by an edit from a new reviewer) returns 400; nothing is saved.|
|`test_an_edited_code_comes_back_with_its_own_meaning`|A coded field edited from 1 to 2 comes back from `GET /reviews` with the meaning of 2 ("In kitchen"), not of what the model read.|
|`test_accuracy_counts_every_changed_field_on_saved_pages_against_the_model_that_read_them`|Each model's accuracy counts only pages a reviewer has saved (a save with no edits means all correct): any changed field, even just its capitals, counts as wrong, a field re-typed as it was doesn't, and an unsaved page isn't counted (opus 4 of 5 = 80%, sonnet 0 of 1 = 0%), and each row names its page type, so a coded card is counted apart from the main forms (opus coded 1 of 1 = 100%).|
|`test_a_page_scan_is_served_by_its_page_id`|`GET /pages/<page id>/image` returns the scan's bytes; an unknown page id returns 404.|
|`test_a_page_scan_not_on_this_computer_comes_from_the_archive_and_is_kept`|A page whose scan isn't on this computer is downloaded from the archive (faked here) once and kept; a page the archive hasn't got, returns 404.|
|`test_a_page_the_archive_breaks_off_is_not_kept_and_its_bundle_is_not_asked_again_for_a_while`|A page download the archive breaks off is not kept (404); the archive isn't asked about that bundle again for `RETRY` seconds, and after that the page is downloaded and served.|
|`test_a_page_scan_can_be_had_straightened_and_black_and_white`|`GET /pages/<id>/image?preprocessed=true` returns a real main form straightened, cropped and black and white (only black and white pixels), made once into `OUTPUT/preprocessed/<page id>.png` and served from there after; the plain `/image` still returns the scan unchanged.|
|`test_a_scan_that_cannot_be_cleaned_up_is_sent_as_it_is`|A scan the preprocessing can't read is returned as it is instead of an error.|
|`test_survey_flags_grouping_problems_unreadable_text_and_other_pages`|A stored grouping flag comes back as `inconsistency` on its field and a value containing `[?]` as `uncertain`; a page of type `other` is sent as `notes` with an `uncertain` flag on its empty text field.|

## `test_loader.py`
|Test|What it checks|
|---|---|
|`test_each_page_records_the_prompt_and_template_versions_that_read_it`|A page whose manifest entry has the hashes of a stored prompt and template version is stored with those versions; a hash no version has, or a page that wasn't read, leaves them empty.|
|`test_a_run_loads_into_the_series_its_manifest_names_reading_nothing_into_a_type_that_series_lacks`|A run whose manifest names series 2 loads its item into series 2, and a page labelled with a type series 2 doesn't have is stored as its Unknown type with no fields read into it.|
|`test_consistency_conflicts_become_flags_on_the_fields_they_name`|A conflict in the run's consistency check (validation/output_flagged.json) becomes an `inconsistency` flag ("Consistency: ...") on each field it names that the page has, on the main form and the coded card; a resident's field, which isn't a page field, is skipped, and a "comparison incomplete" result makes no flag.|
|`test_a_page_of_a_type_the_db_does_not_have_is_stored_as_other`|A page read as a page type the db has no record of is stored as `other`, not refused.|
|`test_run_loads_into_its_surveys`|A pipeline run (manifest.json + transcripts, Windows-style paths) loads into the database: each page in its survey, a page in no survey kept with none, a blank page left out, a page identify sent to review stored as category `other` with one empty `text` field, residents and each list of other children (`died`, `living_elsewhere`) numbered from 0, and the run's `group` problem in review.json saved as an `inconsistency` flag ("Grouping: ...") on its page's `number_of_dwelling` field, while an `identify` problem makes none. Coded values are decoded to their meaning, with an unreadable "1[?]" left undecoded. Loading the same run again leaves the database as it is. Transcripts from before the rename, which say `engine`, store it as the page's `provider`, not as a field, and an older model label listing every model Claude Code used (`claude-haiku-4-5-20251001+claude-opus-5-5`) is stored as the one the run asked for in its manifest (`opus`).|

## `test_schema.py`
The test db is built from `backend/db/models.py` with foreign keys checked, as in the real db.

| Test                                                     | What it checks                                                                                                                                                                   |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_a_row_must_belong_to_something_that_exists`        | A survey for a bundle that doesn't exist, a resident's field for a resident that doesn't exist, or a flag on a field that doesn't exist is refused.                              |
| `test_a_job_status_is_waiting_running_done_or_failed`    | Any other job status is refused.                                                                                                                                                 |
| `test_a_page_has_one_of_the_page_types`                  | A page whose type isn't in `page_types` is refused.                                                                                                                              |
| `test_a_flag_is_an_inconsistency_gibberish_or_uncertain` | A flag of any other kind is refused.                                                                                                                                             |
| `test_an_edit_fixes_exactly_one_thing`                   | An edit pointing at nothing, at two things (a field and an other child), at a resident's field without saying whose, or at an other child without saying which list, is refused. |

## `test_jobs_api.py`
|Test|What it checks|
|---|---|
|`test_bundles_list_each_pdf_whether_it_is_loaded_and_its_surveys`|`GET /bundles` lists every PDF under `DATA` by its bundle number, with whether it is loaded, its survey ids in scan order (by each survey's first page) and its latest job.|
|`test_a_pdf_is_listed_under_the_series_whose_archive_item_it_is_with_its_identifier_and_title`|`GET /bundles` lists a PDF not loaded yet under the series whose archive item its number is (else the Wilfred Prest Survey), with that item's identifier and title.|
|`test_started_job_waits_for_the_worker`|`POST /jobs` queues a waiting job (202), with its last update time in UTC, that `GET /bundles` and `GET /jobs/<id>` report (an unknown id is 404), and refuses a second one for the same PDF while it waits.|
|`test_pdfs_inside_the_repo_are_named_relative_to_it`|With `DATA` inside the repo (the usual setup), PDFs and jobs use a forward-slash path relative to the repo, so the db works on any checkout.|
|`test_jobs_only_for_unloaded_pdfs_in_data`|A PDF outside `DATA` is refused (404), and a bundle already loaded is refused (409) so its reviews can't be lost.|
|`test_the_archives_bundles_whose_pdf_is_not_here_are_listed_and_can_run`|`GET /bundles` also lists each of the archive's bundles (`backend/archive_pdfs.txt`, faked here) whose PDF isn't in `DATA`, as `DATA/<bundle number>/<its PDF>`, and a job can be queued for it; a PDF already here is listed once.|
|`test_the_real_archive_list_names_each_bundle_as_the_archive_does`|`backend/archive_pdfs.txt` lists the 45 bundles once each, as `<bundle number>/<file id>_<file name>.pdf`.|

## `test_serve.py`

The `uv run app` and `uv run api` commands (`backend/serve.py`), with the programs they start faked.

| Test                                                            | What it checks                                                                                                                                             |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_the_api_stopping_by_itself_stops_the_worker`              | It starts uvicorn on `backend.api.main:app` and `backend.worker`; when the API stops by itself (e.g. port 8000 in use), the worker is stopped too.         |
| `test_ctrl_c_waits_for_both_to_stop_themselves`                 | After Ctrl+C it waits for the API and the worker to stop themselves, and doesn't kill the worker, so a running job is marked failed and resumes next time. |
| `test_api_runs_just_the_api_restarting_on_backend_code_changes` | `uv run api` runs only the API, reloading when files under `backend/` change.                                                                              |
| `test_every_command_points_at_a_function`                       | Each command in `pyproject.toml` (`survey`, `app`, `api`, `worker`) names a function that exists, so a typo there fails here.                              |

## `test_worker.py`
The pipeline and loader are faked: no model calls. Job state is read through a second connection, as the API sees it.

|Test|What it checks|
|---|---|
|`test_a_job_reads_with_the_newest_prompt_and_templates`|A job hands the pipeline the newest version of the prompt and of each template, as the job starts.|
|`test_job_runs_the_pipeline_reports_progress_and_loads_its_surveys`|The worker runs the oldest waiting job, commits each step and page count while it runs, keeps the page count once the run moves on, loads the run's manifest.json and marks the job done.|
|`test_a_job_runs_every_step`|A job runs split, identify, transcribe, group and validate.|
|`test_failed_run_is_marked_failed_with_its_reason_and_loads_nothing`|A failed model call marks the job failed with its reason, and nothing is loaded.|
|`test_a_failed_job_is_logged_with_its_full_error`|The worker logs a job's start and, when it fails, the step it failed during with the full error and traceback (the job keeps just the message).|
|`test_pdf_with_no_pages_fails_instead_of_loading_nothing`|A PDF with no pages fails with a reason instead of ending done with nothing loaded.|
|`test_stopping_the_worker_marks_its_job_failed`|Ctrl+C during a job marks it failed, so it doesn't show as running forever.|
|`test_job_cut_off_by_a_stopped_worker_can_be_run_again`|A job still marked running when the worker starts (killed or crashed) is marked failed, so it can be run again.|
|`test_an_item_of_another_series_runs_with_that_series_page_types_and_rule`|A job for an item another series lists runs into that series, with its grouping rule, record name and page types only.|
|`test_an_item_on_no_series_list_runs_as_the_prest_surveys_keeping_its_blank_pages_out`|An item no series lists runs as the Wilfred Prest Survey's, sorting into its types and dropping blank pages.|
|`test_only_one_worker_runs_at_a_time`|A second worker exits while one is running (two would run a bundle into the same output folder), and can start once the first has stopped.|

## `test_instructions.py`

The transcription prompt and templates as versions in the db (`backend/db/instructions.py` and `/instructions`).

| Test                                                                               | What it checks                                                                                                                                                                                                                                                                                                                                                                        |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_a_prompt_saved_with_only_its_line_endings_changed_is_no_change`              | A prompt sent back with plain line endings instead of Windows ones (as a browser's text box does) is no change, so no new version makes jobs read pages again.                                                                                                                                                                                                                        |
| `test_todays_prompt_and_templates_pass_the_checks`                                 | Today's `prompt.txt` and templates pass every check.                                                                                                                                                                                                                                                                                                                                  |
| `test_a_template_that_would_break_the_pipeline_or_the_review_screen_is_refused`    | 14 cases: a template that isn't JSON or an object or has no fields, lacks `number_of_dwelling` (main, coded) or `text` (notes), has a field the pipeline fills in, `annotations`, `residents` or `other_children` in another shape, a name with a dot or capitals, a field that isn't null or an object, or makes the command line too long for Windows, is refused with that reason. |
| `test_an_empty_prompt_is_refused`                                                  | A blank prompt is refused.                                                                                                                                                                                                                                                                                                                                                            |
| `test_a_saved_template_becomes_the_newest_version_and_the_old_one_is_kept`         | `POST /instructions/main` saves a new version with its reviewer and note; it becomes the newest (what the next job reads with) and the history lists both, newest first.                                                                                                                                                                                                              |
| `test_a_save_is_refused_when_unknown_unchanged_invalid_or_based_on_an_old_version` | An unknown kind (404) or reviewer (400), no change, or a template with problems (400, listing them) is refused; a save based on a version that is no longer the newest is refused (409).                                                                                                                                                                                              |
| `test_accuracy_is_kept_apart_for_each_prompt_and_template_version`                 | `GET /accuracy` gives a row per prompt and template version, so versions can be compared.                                                                                                                                                                                                                                                                                             |

## `test_page_types.py`

Page types added from the review screen, and a page read again as another type.

| Test                                                                       | What it checks                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_a_read_that_fails_while_the_page_is_swapped_leaves_it_as_it_was`     | A model answer the db can't take fails the job, and the page keeps its fields, type and revision: the swap is all or nothing.                                                                                                                                                                     |
| `test_a_page_read_again_counts_for_accuracy_only_once_a_reviewer_saves_it` | A page read again isn't counted by `GET /accuracy` until a reviewer saves it.                                                                                                                                                                                                                     |
| `test_a_new_page_type_needs_a_template_before_pages_are_read_as_it`        | `GET /page-types` lists the built-in four with their templates; a new type needs a lower-case name that isn't taken or reserved (`blank`) and a known reviewer; a page can't be read as it until it has a template (`other` can't have one); then `PUT /pages/{id}/type` queues a page job, once. |
| `test_reading_a_page_again_without_a_choice_uses_the_saved_one_or_is_refused` | `PUT /pages/{id}/type` without a model, provider and effort is refused with 409 and the Settings message when nothing is saved, and queues the saved choice otherwise. |
| `test_a_part_of_a_choice_is_checked_like_a_whole_one` | A part given on its own (a bad effort, provider or model) is refused with 400 even when the rest comes from the saved choice. |
| `test_a_page_made_other_is_emptied_at_once`                                | Making a page `other` empties it to one blank text field at once and moves its revision on.                                                                                                                                                                                                       |
| `test_a_page_keeps_its_type_once_reviewed_or_when_the_change_is_unknown`   | An unknown page (404), page type (400) or the type it already has (400) is refused, and so is any change once the page has a saved review (409).                                                                                                                                                  |
| `test_the_worker_reads_the_page_again_and_swaps_what_was_read`             | The worker reads the page's scan (a WebP converted to JPEG) with the new type's newest template, then swaps the page's fields, type, model, template version and revision in one go.                                                                                                              |
| `test_a_page_reviewed_while_it_is_read_again_is_left_as_it_was`            | If a review is saved while the page is being read, the job fails with that reason and the page is left as it was.                                                                                                                                                                                 |

## `test_add_items.py`

A series' items listed from the archive (a fake archive here) and added to its list, one by one or the whole list, then run into that series.

|Test|What it checks|
|---|---|
|`test_a_series_items_are_listed_from_the_archive_saying_which_have_scans_and_which_are_listed_already`|A page of a series' list comes back with each item's title, identifier and number; an item with no scans or for the Reading Room only can't be downloaded; one a series lists is marked; the search and page are asked for oldest first.|
|`test_listing_needs_a_series_linked_to_an_archive_that_answers`|A series with no archive series can't list items (400), and an archive that can't be reached says so (502).|
|`test_chosen_items_are_added_once_the_archive_shows_them_in_this_series`|Chosen items are added once the archive's page shows each in this series; one of another series, one a series lists already, and a number the archive doesn't know are refused with the reason; no download page is read.|
|`test_an_added_item_is_listed_and_run_under_its_series_only`|An added item is listed under its series, not the Prest survey's, can be run, and its job counts on its series only.|
|`test_the_whole_list_is_added_at_once_but_for_items_it_cant_download_or_a_series_lists`|Adding the whole list (or a search's) reads every page of it and adds each downloadable item no series lists, with its title.|
|`test_a_series_linked_without_its_identifier_checks_items_against_the_archives`|A series stored without its archive identifier checks items against the identifier the archive shows for it, and refuses to add when the archive shows none.|
|`test_an_item_number_out_of_range_is_refused`|An item number below 1 or too big for the db is refused with the reason.|
|`test_adding_a_list_from_an_archive_that_cant_be_reached_says_so`|Adding a whole list when the archive can't be reached says so (502).|
|`test_a_run_saves_the_series_it_is_loaded_into`|A run's manifest names the series its item is loaded into.|
|`test_a_list_of_over_a_thousand_items_is_left_for_a_search_to_narrow`|A list of over 1,000 items is refused after reading its first page, with the count and what to do.|
|`test_an_added_items_pdf_is_its_newest_original_looked_up_when_it_is_downloaded`|An added item's PDF is its newest original, found on its download page when it is downloaded; an item with none says so.|
|`test_a_page_takes_only_a_page_type_of_its_own_series`|Changing a page's type to another series' type is refused.|
|`test_sorting_gives_only_the_series_own_page_types_and_sends_the_rest_to_review`|Sorting's label outside the series' page types becomes review, and is flagged.|
|`test_an_upload_cant_take_the_number_of_an_item_added_from_the_archive`|An upload can't use the number of an item added from the archive, nor give another number a PDF named as that item's.|

## `test_record_name.py`

Each series names its records (the Wilfred Prest Survey's are surveys), and where no page type starts a record each page is one.

|Test|What it checks|
|---|---|
|`test_a_series_names_its_records_in_lower_case_and_an_empty_name_is_record`|`PATCH /collections` stores the record name in lower case with single spaces and keeps it when left out; an empty one reads as "record"; anything but a word or two of letters (40 at most) is refused with the reason.|
|`test_a_series_is_grouped_while_one_of_its_page_types_starts_a_record`|A new series isn't `grouped`; once one of its page types starts a record it is, on the series and on its records.|
|`test_an_ungrouped_series_names_its_record_its_own_way`|A record of an ungrouped "letter" series says so, puts its free text under "Letter details", tells a reviewer to check an Unknown page without calling it part of a bigger record, and words page type refusals with "letter".|
|`test_an_unknown_page_grouped_with_others_is_flagged_as_part_of_their_survey`|An Unknown page in a Prest survey with other pages is flagged as in that survey because it follows the survey's first page, with its free text under "Survey details".|

## `test_sorting_models.py`

Page sorting retrained from the review screen; page fingerprints are made up, so no model is loaded.

| Test                                                                             | What it checks                                                                                                                                                                                                                                                                         |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_a_new_page_type_is_left_out_when_too_few_of_its_settled_pages_have_a_scan` | A new type's 10 pages are counted among the settled pages that have a scan; the note says which types were left out and how many pages had no scan.                                                                                                                                    |
| `test_retraining_keeps_its_fingerprints_apart_from_the_committed_ones`           | The real `retrain()` and `stored()` (page fingerprints made up) write the settled pages' fingerprints to their own folder, never touch the committed ones, and reuse them next time.                                                                                                   |
| `test_a_model_learns_a_page_type_beyond_the_four`                                | Given labels beyond the four, the model learns the new type and sorts its pages into it (or review).                                                                                                                                                                                   |
| `test_retraining_learns_a_settled_page_type_and_keeps_the_model`                 | `retrain()` on the labelled pages plus settled pages of a new type passes its held-out check, writes the model, and the model sorts the new type.                                                                                                                                      |
| `test_a_retraining_that_fails_its_check_is_not_kept`                             | Settled pages a model can't tell from main forms fail the check, and no model is written.                                                                                                                                                                                              |
| `test_the_worker_trains_on_settled_pages_and_uses_a_model_that_passes`           | A training job uses the pages reviewers settled (not other or unchecked pages, nor a new type with fewer than 10), records the model with its reviewer and a note of what was left out, and makes it the only active one.                                                              |
| `test_a_model_that_fails_its_check_is_recorded_but_not_used`                     | A model that fails is recorded with its check, but not kept or used.                                                                                                                                                                                                                   |
| `test_a_bundle_job_sorts_with_the_active_model`                                  | A bundle job sorts pages with the active model's weights; if that file is gone, the job fails saying so.                                                                                                                                                                               |
| `test_sorting_models_are_trained_listed_and_chosen_through_the_api`              | `POST /sorting-models` queues one training (409 while waiting; 400 for an unknown reviewer); the list is newest first; `PUT /sorting-models/active` refuses an unknown (404) or failed (400) model, makes a passed one the only active one, and `null` goes back to the shipped model. |
|`test_moves_do_not_make_unreviewed_pages_training_examples` — 2 tests|Repeated moves increase revisions and reject stale requests without making an unreviewed page eligible for sorting training. A previously reviewed page stays eligible after moving.|

## `test_page_transcription.py`

|Test|What it checks|
|---|---|
|`test_classification_is_immediate_preserves_reviews_and_does_not_queue`|Changing page type preserves existing content and reviews, records a history snapshot, and does not queue transcription.|
|`test_same_type_transcription_preserves_old_reviews_in_history`|Retranscription replaces the current content while preserving previous content and reviews in history.|
|`test_failed_transcription_keeps_old_content`|A failed transcription keeps the existing content and reviews.|
|`test_concurrent_review_prevents_replacement`|A page changed after transcription was queued is protected from replacement.|
|`test_classification_rejects_invalid_type_reviewer_and_stale_revision`|Rejects unsupported types, unknown reviewers, outdated revisions, and selecting the existing type.|
|`test_transcription_requires_template_and_valid_model_details`|Rejects invalid model settings and transcription of a page type without a template.|
|`test_other_does_not_require_transcription_but_main_does`|Changing Main → Other → Main updates the transcription requirement correctly in both the API response and database.|

## `test_page_history.py`

It checks read-only, page-scoped history, archived reviews, moves, empty history, and missing pages.

## `test_uploads.py`

`POST /bundles/upload`: a bundle is one PDF, or a folder of page images that share a bundle number. Duplicates are refused without changing existing files or database records.

| Test                                                              | What it checks                                                                                                                                                                                          |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_loaded_pdf_cannot_be_uploaded_under_another_bundle`         | Rejects a PDF whose filename already identifies a loaded bundle, reports the original bundle number, and preserves the database record.                                                                 |
| `test_local_pdf_identity_is_unique_across_folders`                | Rejects the same PDF filename under a different bundle folder and preserves the original file.                                                                                                          |
| `test_archive_pdf_requires_original_bundle_number`                | Rejects an archive PDF under the wrong bundle number and accepts it under its registered number when not already loaded or uploaded.                                                                    |
| `test_different_pdf_cannot_reuse_bundle_number` — 3 tests         | Rejects a different PDF when its proposed bundle number is already used in the database, local storage, or archive list.                                                                                |
| `test_new_bundle_number_accepts_upload`                           | Accepts a new PDF under an unused bundle number and saves its contents unchanged.                                                                                                                       |
| `test_page_images_make_one_bundle_named_after_it`                 | Several page images share a bundle number and are saved as `<bundle>_<name>`, so their page IDs stay unique; the same image twice, or a PDF, is refused; `GET /bundles` lists the folder as one bundle. |
| `test_an_image_cannot_join_a_pdf_bundle`                          | A page image under a PDF's bundle number is refused and the folder keeps only the PDF.                                                                                                                  |
| `test_a_damaged_pdf_is_refused_and_leaves_nothing_behind`         | A damaged PDF gets a 400 saying so, with no bundle folder and no temporary file left.                                                                                                                   |
| `test_a_file_over_the_limit_is_refused_and_leaves_nothing_behind` | A file over the size limit gets a 413, with no bundle folder and no temporary file left.                                                                                                                |
| `test_names_windows_cannot_store_are_refused` — 6 tests           | Names with `? : | "` or a trailing dot or space are refused with a 400 before anything is saved.                                                                                                        |
| `test_pdf_names_that_differ_only_by_case_are_the_same_bundle`     | A PDF name that differs from an uploaded, loaded or archive PDF only by case counts as the same bundle; an archive PDF is accepted under its own number whatever the case.                              |

## `api.test.ts` — 19 tests

Tests the frontend review API adapter using Vitest and mocked fetch responses.
Each test uses fresh sample data; no running backend or database is needed.

| Test                                                                                                                                           | What it checks                                                                                             |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `it("requests the selected survey and preserves main/notes/coded data", async () => ...)`                                                      | Requests the correct survey with the supplied abort signal and preserves all three page types.             |
| `it("fills missing flags and unavailable image paths without changing field values", async () => ...)`                                         | Missing flags become an empty list and unsupported image paths get a placeholder, preserving field values. |
| `it("rejects data for a different survey", async () => ...)`                                                                                   | A response belonging to another survey is rejected.                                                        |
| `it("rejects duplicate page IDs", async () => ...)`                                                                                            | Duplicate page IDs in a survey response are rejected.                                                      |
| `it("shows backend not-found errors", async () => ...)`                                                                                        | The backend's not-found explanation reaches the caller.                                                    |
| `it("shows a useful message for non-JSON server errors", async () => ...)`                                                                     | A non-JSON error response produces a message containing the HTTP status.                                   |
| `it("propagates cancellation", async () => ...)`                                                                                               | A simulated request cancellation reaches the caller as an AbortError.                                      |
| `it("maps id into the frontend id", async () => ...)`                                                                                          | Reviewer IDs and names from the backend response are returned correctly.                                   |
| `it("reuses an existing reviewer without creating another", async () => ...)`                                                                  | Surrounding whitespace is trimmed and an existing reviewer is reused.                                      |
| `it("rejects an empty reviewer name without a request", async () => ...)`                                                                      | A blank reviewer name is rejected without calling the API.                                                 |
| `it("loads saved reviews and revisions unchanged", async () => ...)`                                                                           | Saved reviews and page revisions are returned unchanged.                                                   |
| `it.each(["Corrected address", "/", "[?]", null])("sends the selected value %j without changing its meaning", async (value) => ...)` — 4 tests | Each value is sent unchanged with its original value, reviewer details and next page revision.             |
| `it("does not send an empty save", async () => ...)`                                                                                           | Empty changes are rejected without making an API request.                                                  |
| `it("does not submit an unknown field", async () => ...)`                                                                                      | A field missing from the selected page is rejected before posting a save.                                  |
| `it("does not submit an unknown reviewer", async () => ...)`                                                                                   | An unregistered reviewer is rejected before posting a save.                                                |
| `it("uses the backend-assigned reviewer ID and sends only the name", async () => ...)`                                                         | Creating a reviewer sends only the trimmed name and uses the ID returned by the backend.                   |

## `test_export_api.py` — 9 test cases

checks the export endpoints using the test client and database fixtures.

| Test                                                    | What it checks                                                                                                            |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `test_export_latest_saved_value_and_source` — 5 cases   | Exports the latest saved correction, including empty strings, `/`, `[?]` and null values, with the correct review status. |
| `test_bundle_includes_all_surveys_and_unassigned_pages` | Bundle exports include all surveys, empty surveys and unassigned pages. The bundle list returns its ID and display name.  |
| `test_export_rejects_invalid_selection`                 | Missing, blank or conflicting selections return 400; unknown survey or bundle IDs return 404.                             |
| `test_bundle_export_uses_id_and_excludes_other_bundles` | Bundle selection uses the database ID, trims whitespace and excludes other bundles even when their display names match.   |
| `test_review_survey_identifies_current_bundle`          | The survey response includes the bundle ID needed by the Current bundle export option.                                    |

## `export.test.ts` — 7 test cases

Test checks the frontend export service using mocked fetch responses.

| Test                                            | What it checks                                                                                                                          |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Returns the backend export unchanged — 5 cases  | Preserves correction text, empty strings, `/`, `[?]` and null values. Trims and URL-encodes the survey ID before requesting the export. |
| Reports backend export errors                   | Displays the error returned by the backend.                                                                                             |
| Rejects blank survey IDs before requesting data | Rejects a whitespace-only survey ID without making a request.                                                                           |

These frontend tests run separately from `uv run pytest tests/unit`.
They check request construction and response handling; the integration runner
checks the adapter against the real backend and database.

## `test_validate_rules.py`
Covers the page 1 / page 3 consistency rules on the sample survey, with a consistent baseline that each test then breaks in one place. No model calls.

|Test|What it checks|
|---|---|
|`test_consistent_sample_no_flags`|The unmodified consistent sample survey produces no issues.|
|`test_isolated_unreadable_ignored`|An unreadable `[?]` in a field that has no counterpart on the other page is not flagged.|
|`test_no_codebook_mapping_guessed`|With no codebook supplied, a municipality name on page 1 and a code on page 3 are not compared, so no issue is raised.|
|`test_children_from_ages_8_and_7`|Children aged 8 and 7 count towards "children under 14", and a page 3 value of 1 instead of 2 is flagged as a page 1-3 conflict.|
|`test_age_boundaries`|Ages 4, 5, 10, 11, 13 and 14 fall into the correct under-5, 5-10, over-10 and under-14 counts, and the matching page 3 values raise no issue.|
|`test_corresponding_missing_markers`|A missing bedrooms value on page 3 (None, empty, space, `/` or `[?]`) while page 1 has one is flagged as an incomplete comparison.|
|`test_absent_field_has_location`|A field deleted from the coded card is flagged with its location and the value `<missing>` (`Page 3: number_of_bedrooms`).|
|`test_both_corresponding_blank_no_crosspage_issue`|When the dwelling number is blank on page 1 and `/` on page 3, no cross-page issue is raised.|
|`test_unknown_age_not_silently_zero`|A resident age of `[?]` is not counted as 0, and "children under 14" is flagged as incomplete.|
|`test_unknown_sex_not_guessed_from_head`|A head with no sex recorded is not assumed to be male or female, so the residents-over-10 check raises nothing.|
|`test_empty_template_columns_not_residents`|A resident column with no age and a `/` relationship is not counted as a resident.|
|`test_page3_age_sum_reason`|A page 3 resident total of 5 that disagrees with the age-band counts is flagged as a page 3 internal conflict that mentions age bands.|
|`test_children_arithmetic`|A children total of 3 against 2 living and 0 dead is flagged as a page 3 conflict about living plus dead.|
|`test_combined_rooms`|A total room count of 4 that is smaller than separate bedrooms plus living rooms is flagged.|
|`test_page1_conflict`|Bedrooms used as living rooms combined with zero living rooms on page 1 is flagged as a page 1 internal conflict.|
|`test_equivalent_count_text`|"None" and 0 for rooms not in daily use, and "01" and 1 for the dwelling number, are treated as equal.|
|`test_probable_age_range`|A page 3 house age of 61 outside the page 1 probable-age interval is flagged.|
|`test_children_elsewhere_bound`|Resident children plus children elsewhere that exceed the children total are flagged.|
|`test_legacy_other_children_is_not_used`|An other-children count on a resident, or a died entry in the main form's `other_children` list, raises no head's-other-children issue.|
|`test_negative_only_flagged_in_relationship`|A negative value is flagged only in a field that is part of a cross-page relationship (bedrooms), not in an unrelated one (removal).|
|`test_preserves_input_and_deterministic_batch`|Checking a survey twice gives the same result and leaves both readings unchanged, and the consistent sample has no rule issues.|
|`test_missing_page_is_input_error`|A survey with no coded page raises `ValueError`.|

## `test_validate_codebook.py`
Covers codebook value ranges, special codes, municipality mapping, house-age and residence codes, and codebook file loading, using the example main and coded surveys. No model calls.

|Test|What it checks|
|---|---|
|`test_unspecified_head_sex_accepts_feasible_assignments`|With an unspecified head sex and a 71-year-old head and 69-year-old wife, male/female counts of 1/1 and 0/2 are accepted.|
|`test_unspecified_head_sex_still_rejects_impossible_assignments`|For the same couple, counts of 2/0, 1/2 and 0/0 are flagged as a page 1-3 conflict on residents over 10.|
|`test_sleepout_count_and_category_compatible`|Sleepout counts and page 3 categories that fit together (0 with 0, 1 with 1/2/3, 2 or 9 with 4, "Balcony" with 2) raise no sleepouts issue.|
|`test_sleepout_count_and_category_conflict`|Sleepout counts and categories that do not fit (0 with 1, 1 with 4, 2 with 2, "Balcony" with 1) are flagged as a page 1-3 conflict.|
|`test_shared_facility_code_is_not_a_room_count`|A rooms-shared code of 7 is accepted as a facility code, and 8 is flagged as a codebook conflict.|
|`test_declared_codebook_domains`|For each listed field, a value inside the codebook range raises no codebook conflict and a value just outside it does.|
|`test_municipality_uses_actual_mapping`|Essendon with code 08, Brunswick with 2 and Box Hill with 00 match the codebook mapping and raise no flags.|
|`test_municipality_mismatch_is_explained`|Essendon on page 1 with code 2 (Brunswick) is flagged with a reason saying the code means Brunswick, naming `Page 3: municipality`, and both readings are left unchanged.|
|`test_municipality_ignores_punctuation_and_suburbs`|"Brighton." (01), "N. Fitzroy." (09), "South Yarra SE 1." (21), "St Kilda" (26) and "Glen Iris" (03) raise no flags; with code 02 (Brunswick) only the two that name a council are flagged; with `suburb_coded_as_council` off, the three suburbs are flagged against their own codes.|
|`test_missing_municipality_counterpart_is_incomplete`|A page 3 municipality of None, `/` or `[?]` against a named page 1 municipality is flagged as an incomplete comparison.|
|`test_no_reference_fields_and_special_money_codes_not_reinterpreted`|Industry and occupation codes, an unreadable removal, unmapped military-service text and an income code of 997 are not checked or reinterpreted, so no flags result.|
|`test_zero_room_code_accepts_over_eleven`|With bedrooms coded 0 and total rooms coded 0, an exact page 1 bedroom count of 12 or 18 is accepted.|
|`test_zero_room_code_also_means_none`|No living rooms on page 1, coded 0, with 3 rooms in total raises no flags; with `zero_rooms_means_none` off it's flagged.|
|`test_house_special_codes_not_treated_as_exact_ages`|House-age codes 00, 98 and 99 against "55", "old", "105 years." and "over 99 years." are not compared as exact ages.|
|`test_over_ninety_nine_house_code_conflicts_with_fifteen`|A house-age code of 99 (over 99 years) against a page 1 age of 15 years is flagged as a page 1-3 conflict.|
|`test_residence_special_codes`|Length of residence "0.5 years" with code 00 and "22 years" with code 99 raise no residence issue.|
|`test_explicit_missing_dictionary_fails`|An explicitly supplied codebook path that does not exist raises `FileNotFoundError`.|
|`test_malformed_dictionary_fails_before_validation`|A codebook file with no usable content raises `ValueError` before any validation runs.|
|`test_missing_default_dictionary_preserves_standalone_api`|When the default codebook file cannot be found, validation still runs with no flags and returns a warning that codebook checks were not run.|

## `test_validate_regressions.py`
Covers relationship parsing, year-unit punctuation, age ranges, annotated child relationships and the 1940s coders' conventions (each accepted when switched on and flagged when off), using the example main and coded surveys. No model calls.

|Test|What it checks|
|---|---|
|`test_female_head_is_identified_and_sex_is_explicit`|A head written as "Head (F)", "head (female)", "H. (F)", "H (f)" or " Head ( F ) " is recognised as the head and taken as female, and an age of head of 75 is then flagged as a conflict.|
|`test_head_prefix_does_not_identify_unrelated_labels`|"headache", "head boarder" and "head of son" are not recognised as the head.|
|`test_period_after_year_unit_is_accepted`|"15 years.", "15 year.", "15 yrs." and "15 y." are all read as 15 years for house age and length of residence, with no flags.|
|`test_age_ranges_and_bounds_allow_period`|"50-60 years.", "over 50 years." and "under 60 years." are accepted as probable-age values with a trailing period, with no flags.|
|`test_annotated_son_and_daughter_count_as_resident_children`|"Son (M)" and "Daughter (F)" count as resident children, and a page 3 living-children total of 1 is flagged because the resident sons and daughters exceed it.|
|`test_conventions_file`|`conventions.json` sets every convention; a file with a value that isn't true/false, a missing convention or a misspelt one is refused.|
|`test_checks_file`|`checks.json` names every check; a file with a value that isn't true/false, a missing check or a misspelt one is refused.|
|`test_switched_off_check_gives_no_flags`|A coded bedroom count of 5 against 3 on page 1 is flagged by `bedrooms`, and gives no `bedrooms` flag with that check switched off.|
|`test_relationship_with_full_stops`|"Son.", "Head (F).", "H. (F.)", "Head (R.S.)" and "daughter." are read as son, female head, female head, head and daughter.|
|`test_sleepout_marks`|Beside the printed B V O, "B 1" is one sleepout, two ticks are two, "B yes. V O" and a lone "V" are one, "none." is none; the bare letters misread as "B Y O" or "B V 9" are unknown.|
|`test_another_resident_may_stand_in_as_head`|An age of head of 70 matches the 70-year-old wife when Sex of Head is coded 1 (female); coded 0 (male), or with `another_resident_as_head` off, it's flagged against the 76-year-old head.|
|`test_sleepout_may_be_counted_as_a_bedroom`|With "V yes." for sleepouts, 4 bedrooms and sleepouts 0 on the coded card raise no flags (3 bedrooms + the sleepout); 3 bedrooms with sleepouts 0 flags the sleepouts, and 5 bedrooms flags the bedrooms. With `sleepout_counted_as_bedroom` off, 4 bedrooms is flagged.|
|`test_living_rooms_may_leave_out_the_kitchen`|Against 2 living rooms on page 1 (3 bedrooms), code 2 raises no living-room flag; code 1 raises none only when the coded total of 5 counts the kitchen apart (7 doesn't) and the convention is on; 0 and 3 are flagged.|
|`test_residents_serving_in_the_forces_may_be_left_out`|A son with earning status M., or marked A.I.F., R.A.A.F, "in Army." or "In camp", may be left out of the resident total and the over-10 count and counted as a child away; written as a clerk, the same codes flag all three. With `serving_residents_left_out` off, all three are flagged too.|
|`test_ten_year_old_may_be_counted_over_10`|A 10-year-old daughter may be coded in 5–10 or over 10 (only 5–10 with the convention off); left out of both, the survey is flagged.|
|`test_part_years_of_residence_may_be_dropped_or_rounded_up`|"4½ yrs." matches codes 04 and 05; 03 and 06 are flagged, and all four with the convention off.|

## `test_validate_fields.py`
The consistency check reads fields by their template names: a field renamed in a template fails here instead of
switching a check off quietly. No model calls.

|Test|What it checks|
|---|---|
|`test_every_field_the_rules_read_is_in_the_templates`|Running every rule on readings with every template field filled in, each field the rules look up (residents' optional `sex`/`gender` aside) is in `main.json` or `coded.json`. Every convention is switched on, so every rule runs.|
|`test_every_codebook_field_is_a_coded_template_field`|Every field in the codebook (`data_dict.json` page 3) is a field of the coded card's template.|
