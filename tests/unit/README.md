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
| `test_schemafor_maps_every_scalar_to_string_or_null`                | Maps a blank template value (`None`, a number or a boolean) to a string-or-null schema.                                                                                                                        |
| `test_a_field_given_as_text_is_described_by_it_in_the_schema_and_the_prompt` | A field given as text (its description) keeps string-or-null with that text as its schema description, and the prompt tells the model the text describes the field; a template without descriptions adds nothing to the prompt. |
| `test_schema_for_output_is_json_serialisable`                       | Ensures the generated schema can be serialised with `json.dumps()` before being passed to the CLI.                                                                                                                                     |
| `test_run_cli_turns_a_hang_into_a_readable_exit`                    | Converts a CLI timeout into a readable exit message instead of exposing a raw `TimeoutExpired` traceback.                                                                                                                              |
| `test_run_cli_explains_a_missing_cli_instead_of_crashing`           | Converts a missing Claude/Codex executable into a clear "CLI not found" message.                                                                                                                                                       |
| `test_run_cli_passes_capture_and_timeout_settings_through`          | Verifies subprocess output capture, timeout, replacement-character decoding, working directory, and command arguments are passed correctly.                                                                                            |
| `test_cli_runs_with_stdin_closed` | The CLI is started with its standard input closed (`subprocess.DEVNULL`), so it never waits for input. |
| `test_a_full_model_name_runs_itself_without_asking_claude` | `model_of("claude-...")` is the name itself: no claude session is started, so saved answers need no claude. |
| `test_claude_model_is_the_one_claudes_session_starts_with_asked_once_per_name` | An alias ("haiku") runs the model named by the first event of a one-word claude session, asked once per name. |
| `test_when_claude_cant_say_model_of_raises_claude_model_is_the_name_and_it_is_asked_again` — 5 cases | A timeout, a first line that isn't JSON or isn't an object, or no model in it: `model_of` raises LookupError, `claude_model` gives the name itself, and nothing is kept, so it is asked again. |
| `test_reads_at_once_ask_claude_once_which_model_a_name_runs` | Eight reads at once start one claude session for the same name. |
| `test_the_same_page_and_question_is_answered_from_the_saved_answer_with_its_seconds` | The same page image, prompt, template, provider, model and effort asked again is answered from the saved answer, without the model, keeping the seconds the model took. |
| `test_a_change_to_what_is_asked_asks_the_model_again` — 5 cases | A changed image, prompt, template, effort, or model behind the alias asks the model again. |
| `test_a_fresh_read_asks_the_model_and_replaces_the_saved_answer` | `fresh=True` asks the model even with an answer saved, and its answer replaces the saved one. |
| `test_nothing_is_saved_or_given_while_the_model_an_alias_runs_is_unknown` | When claude can't say which model an alias runs, every read asks the model and nothing is saved. |
| `test_answers_are_saved_in_the_db_and_one_it_cant_take_is_neither_kept_nor_an_error` | Answers are kept in the db's `saved_answers` (the newer replacing the older under one key); a db without the table neither gives nor keeps one, and raises nothing. |
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
| `test_transcribe_refuses_an_unknown_provider`                       | A provider that isn't one of `claude`, `codex`, `anthropic`, `openai`, `gemini`, `openrouter` or `ollama` stops with "PROVIDER must be one of claude, codex, anthropic, openai, gemini, openrouter, ollama, not '<provider>'".                                                                                                                                               |
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
| `test_saving_again_replaces_and_leaves_other_settings` | Saving a choice again replaces the earlier one and leaves other saved settings alone. |
| `test_nothing_is_configured_until_a_choice_is_saved` | `GET /transcription-models` gives `configured: null` until then. |
| `test_put_saves_all_three_trimmed_and_returns_the_choice` / `test_there_is_no_reset` | `PUT /transcription-defaults` saves and returns exactly provider, model and effort; `DELETE` no longer exists. |
| `test_folders_are_the_data_and_output_folders_inside_the_project` | `GET /folders` gives the absolute `data` and `output` folders under the project. |
| `test_put_and_post_jobs_reject_the_same_values_with_the_same_message` — 10 cases | A blank, multi-word, option-like, too long or odd model, an unknown provider, or a blank, multi-word, option-like or too long effort is refused with the same 400 and message by `PUT /transcription-defaults` and `POST /jobs`; nothing is saved or queued. |
| `test_put_needs_all_three_fields` | `PUT /transcription-defaults` without all of provider, model and effort is 422 and saves nothing. |
| `test_put_rejects_a_body_that_is_not_json` | A `PUT` whose body isn't JSON is 422. |
| `test_a_job_without_a_full_choice_and_nothing_saved_is_refused` | `POST /jobs` without a full choice and nothing saved is 409 "Choose a transcription model on the Settings page first." and queues nothing. |
| `test_a_job_with_an_explicit_choice_works_with_nothing_saved` | An explicit choice in the payload needs nothing saved. |
| `test_a_job_started_without_a_choice_uses_the_saved_one` / `test_a_job_with_part_of_a_choice_takes_the_rest_from_the_saved_one` | The saved choice fills whatever the payload leaves out. |
| `test_a_page_transcription_cannot_leave_out_its_choice` | `POST /page-transcription` requires provider, model and effort (422). |
| `test_a_bundle_job_with_no_choice_runs_with_the_saved_one` | The worker gives the pipeline the job's own fields, else the saved choice. |
| `test_a_bundle_job_without_a_full_choice_and_nothing_saved_fails_with_the_message` / `test_a_page_job_with_no_choice_and_nothing_saved_fails_with_the_message` | A job with a missing field and nothing saved is marked failed with the message, and no model or pipeline runs. |
| `test_a_page_job_with_no_choice_reads_with_the_saved_one` / `test_a_page_job_with_a_choice_keeps_it` | A page job with no choice reads the page with the saved one; a page job with its own choice keeps it whatever is saved. |

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
|`test_a_surveys_title_is_its_collections_name`|A survey's `title` is the name of the series (collection) it belongs to.|
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
Each test starts from a new database made by the migration, holding the Prest series (its page types, its survey level) and an item 216412 it lists with its PDF, as the app is set up.

|Test|What it checks|
|---|---|
|`test_each_page_records_the_prompt_and_template_versions_that_read_it`|A page whose manifest entry has the hashes of a stored prompt version (of its series) and template version is stored with those versions; a hash no version has, or a page that wasn't read, leaves them empty.|
|`test_a_page_records_its_own_series_prompt_version_when_two_series_have_the_same_prompt`|Two series with the same prompt text each have their own prompt version; a page of series 2 records series 2's, not the older version of series 1.|
|`test_a_run_loads_its_records_inside_one_another_parents_first`|The records a run's grouping made are loaded with the record each sits in, each page into its own, and a grouping problem flagged on the field it names.|
|`test_a_run_loads_into_the_series_its_manifest_names_reading_nothing_into_a_type_that_series_lacks`|A run whose manifest names series 2 loads its item into series 2, and a page labelled with a type series 2 doesn't have is stored as its Unknown type with no fields read into it.|
|`test_a_page_of_a_type_the_db_does_not_have_is_stored_as_other`|A page read as a page type the db has no record of is stored as `other`, not refused.|
|`test_a_page_sorting_was_unsure_about_is_stored_as_the_collections_unknown_type`|A page sorting sent to review is stored as its series' Unknown page type, whatever that is called.|
|`test_a_collection_has_at_most_one_unknown_type_and_without_one_the_bundle_is_refused_by_name`|A series can't have a second Unknown page type (UNIQUE); with none, loading is refused with a message naming the item and the page, and nothing is loaded.|
|`test_an_annotation_is_stored_with_its_area_when_the_page_type_has_it`|An annotation is stored with its area only when the page's type has that area (right margin on a main form, bottom left on a coded card); another type's area, a blank area and a transcript from before areas store none.|
|`test_a_run_no_series_lists_is_refused_by_name`|A run of an item no series lists is refused with "No series lists <pdf>: add it to one from the app first." and nothing is loaded.|
|`test_a_run_of_an_item_uploaded_to_a_series_loads_into_it`|A run of an item that was uploaded to a series (no series lists it from the archive) loads into that series.|
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
|`test_a_pdf_is_listed_under_the_series_whose_archive_item_it_is_with_its_identifier_and_title`|`GET /bundles` lists a PDF not loaded yet under the series whose archive item its number is, with that item's identifier and title; `?collection=` lists another series' PDFs.|
|`test_started_job_waits_for_the_worker`|`POST /jobs` queues a waiting job (202), with its last update time in UTC, that `GET /bundles` and `GET /jobs/<id>` report (an unknown id is 404), and refuses a second one for the same PDF while it waits.|
|`test_pdfs_inside_the_repo_are_named_relative_to_it`|With `DATA` inside the repo (the usual setup), PDFs and jobs use a forward-slash path relative to the repo, so the db works on any checkout.|
|`test_jobs_only_for_unloaded_pdfs_in_data`|A PDF outside `DATA` is refused (404), and a bundle already loaded is refused (409) so its reviews can't be lost.|
|`test_the_archives_bundles_whose_pdf_is_not_here_are_listed_and_can_run`|`GET /bundles` also lists each archive item a series lists with a PDF (`ArchiveItem.pdf`) that isn't in `DATA`, as `DATA/<bundle number>/<its PDF>`, and a job can be queued for it; a PDF already here is listed once.|
|`test_the_prest_setup_names_each_archive_pdf_as_the_archive_does`|The Prest survey's setup file (`setups/wilfred-prest-survey.prestcribe`) lists the 45 archive PDFs once each, as `<bundle number>/<file id>_<file name>.pdf`.|
|`test_job_persists_model_choices_and_defaults` — 4 cases|`POST /jobs` saves the model, provider and effort given (trimmed), and the saved choice for any left out or null, on a waiting job a second connection (the worker's) can read.|
|`test_invalid_model_settings_do_not_queue_a_job` — 6 cases|An empty, multi-word, option-like or 201-character model, an unknown provider or a blank effort is refused (400) and queues nothing, so a valid retry for the same PDF works.|
|`test_model_list_includes_configuration_without_history`|`GET /transcription-models` gives the saved choice and no models when no page has been transcribed.|
|`test_model_history_groups_versions_and_averages_available_runtimes`|The model history keeps template versions apart and averages the runtimes there are (pages with none still count); pages with no recorded model are left out.|
|`test_model_history_can_be_limited_to_one_series`|`GET /transcription-models?collection=` lists only the models that read pages of that series' items (none gives all, an unknown series no models) and still gives the saved choice.|
|`test_transcripts_require_an_existing_job`|`GET /jobs/{id}/transcripts` for an unknown job is 404.|
|`test_transcripts_reject_jobs_without_a_bundle` — 3 cases|A page job, a training job and a bundle job with no PDF are refused (400).|
|`test_transcripts_before_output_exists_are_empty`|A queued job whose output isn't there yet gives no pages, not an error.|
|`test_partial_transcripts_show_sorted_pages_and_only_verified_data`|A running job's pages come in page order with their progress (transcribed, not required, awaiting transcription, needing identification); only a page whose saved result matches its checksum has its data.|
|`test_unusable_transcripts_are_not_exposed` — 5 cases|A transcript that is missing, changed since it was saved, not JSON, named outside the transcript folder or from an unfinished manifest entry is left out.|

## `test_serve.py`

The `uv run app` and `uv run api` commands, and the installed app on Windows (`uv run prestcribe`, in `backend/serve.py`), with the programs they start, the API's answers, WebView2, pywebview and Windows' job objects faked: no window and no process opens.

| Test                                                                                           | What it checks                                                                                                                                                                                                                                              |
| ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_the_api_stopping_by_itself_stops_the_worker`                                             | It starts uvicorn on `backend.api.main:app` and `backend.worker`; when the API stops by itself (e.g. port 8000 in use), the worker is stopped too.                                                                                                          |
| `test_ctrl_c_waits_for_both_to_stop_themselves`                                                | After Ctrl+C it waits for the API and the worker to stop themselves, and doesn't kill the worker, so a running job is marked failed and resumes next time.                                                                                                  |
| `test_api_runs_just_the_api_restarting_on_backend_code_changes`                                | `uv run api` runs only the API, reloading when files under `backend/` change.                                                                                                                                                                               |
| `test_every_command_points_at_a_function`                                                      | Each command in `pyproject.toml` (`survey`, `app`, `api`, `worker`, `prestcribe`) names a function that exists, so a typo there fails here.                                                                                                                 |
| `test_the_installed_app_starts_the_api_and_worker_with_no_console_logging_to_a_file`           | The installed app starts `backend.site:site` and `backend.worker` with `CREATE_NO_WINDOW`, no stdin, and stdout and stderr in `output/prestcribe.log`.                                                                                                      |
| `test_the_window_opens_on_pywebview_edge_once_the_api_answers`                                 | A window titled PrestCribe opens on the app's address with `gui="edgechromium"` only after the API answers, with downloads allowed (the exports); the browser isn't opened.                                                                                 |
| `test_the_window_keeps_its_storage_between_launches_in_the_output_folder`                      | `webview.start` gets `private_mode=False` and `storage_path=output/webview` (made), so the chosen reviewer kept in localStorage survives a restart.                                                                                                         |
| `test_a_window_that_fails_falls_back_to_the_browser_only_if_it_never_opened` — 2 cases         | `webview.start` raising before the window is shown opens the default browser and the app runs on; raising after it was shown does not. Both are logged with the traceback and the programs are stopped when the API stops.                                  |
| `test_pywebview_failing_to_import_falls_back_to_the_browser`                                   | An import that fails opens the browser instead of a window.                                                                                                                                                                                                 |
| `test_closing_with_a_running_job_asks_and_no_keeps_the_window_open`                            | Closing with a running job asks "A job is still running (...). Quit anyway?"; No keeps the window open, Yes closes it.                                                                                                                                      |
| `test_closing_with_nothing_running_does_not_ask`                                               | Closing with no running job doesn't ask.                                                                                                                                                                                                                    |
| `test_closing_the_window_stops_the_api_and_the_worker`                                         | When the window is gone both programs are terminated, not killed.                                                                                                                                                                                           |
| `test_a_program_that_will_not_stop_is_killed`                                                  | A program still running after being asked to stop is killed.                                                                                                                                                                                                |
| `test_the_api_stopping_by_itself_closes_the_window_and_stops_the_worker`                       | When the API exits (an update), the window is destroyed (within 2 s) without asking and the worker is stopped.                                                                                                                                              |
| `test_an_app_already_running_gets_a_window_but_no_second_server_and_is_left_running`           | If PrestCribe already answers, a window opens on it and nothing is migrated or started; closing it doesn't ask and leaves the app alone.                                                                                                                    |
| `test_without_webview2_the_browser_opens_and_the_app_runs_until_the_api_stops`                 | With no WebView2 the default browser opens instead of a window, the log says so, and the programs are stopped when the API stops.                                                                                                                           |
| `test_an_api_that_never_starts_is_not_shown`                                                   | If the API exits at start (e.g. port 8000 is taken), no window or browser opens, the worker is stopped and a message box tells the user.                                                                                                                    |
| `test_the_log_is_opened_first_appended_to_and_started_again_only_when_over_a_megabyte`         | `output/prestcribe.log` keeps what an earlier launch wrote, and is started again only when it is over `LOG_LIMIT` (1 MB).                                                                                                                                   |
| `test_a_startup_failure_is_logged_with_its_traceback_and_tells_the_user_where_the_log_is`      | A failing `migrate()` is logged with its traceback, nothing starts, and a message box says PrestCribe couldn't start and names the log.                                                                                                                     |
| `test_the_job_is_made_after_the_tables_and_before_the_programs`                                | The job object is made after the tables are set up and before the API and the worker start, so they are in it.                                                                                                                                              |
| `test_a_launch_holds_the_startup_lock_while_the_app_runs_and_gives_it_back`                    | `output/prestcribe.lock` is held while the app runs and free afterwards.                                                                                                                                                                                    |
| `test_a_second_launch_waits_for_the_first_ones_app_then_opens_a_window_on_it`                  | A launch that can't get the lock waits (a second at a time) until the app answers, then opens a window on it and starts nothing.                                                                                                                            |
| `test_a_second_launch_that_the_first_never_answers_for_gives_up_after_a_minute_with_a_message` | If the app never answers, it gives up after 60 s with a message box and no window.                                                                                                                                                                          |
| `test_the_app_is_asked_about_without_going_through_a_proxy`                                    | `answering()` and `running_jobs()` reach a local server with `HTTP_PROXY` pointing nowhere, and `running_jobs()` lists only the running ones.                                                                                                               |
| `test_this_process_goes_in_a_job_that_kills_its_members_when_it_ends`                          | With kernel32 faked: the job is created, given `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and this process assigned to it, in that order; the handle is kept.                                                                                                    |
| `test_a_job_that_cannot_be_made_or_joined_is_logged_and_the_app_carries_on` — 3 cases          | Creating, setting or joining the job failing is logged and nothing is raised.                                                                                                                                                                               |
| `test_the_installed_command_opens_a_window_on_windows_and_the_terminal_app_elsewhere`          | `installed()` opens the window flow on Windows and keeps the Terminal flow with the browser on other systems.                                                                                                                                               |
| `test_the_installer_starts_the_app_with_uvw_and_checks_for_webview2`                           | `install.ps1` points the shortcuts and the final start at `uvw.exe` (no console), installs the WebView2 runtime when its registry key is missing (`-Wait -PassThru`), and warns that PrestCribe will open in the browser if it is still missing afterwards. |

## `test_worker.py`
The pipeline and loader are faked: no model calls. Job state is read through a second connection, as the API sees it.

|Test|What it checks|
|---|---|
|`test_a_job_reads_with_the_newest_prompt_and_templates`|A job hands the pipeline the newest version of its series' prompt and of each template, as the job starts.|
|`test_a_job_reads_with_its_own_series_prompt_and_templates`|A job for an item of series 2 is read with series 2's prompt and its page types' templates only, not series 1's prompt or main template.|
|`test_a_job_of_a_series_with_no_prompt_stops_before_reading_anything`|A job for a series that has templates but no prompt fails with "this series has no prompt: add one in its Setup first", and the pipeline is never run.|
|`test_job_runs_the_pipeline_reports_progress_and_loads_its_surveys`|The worker runs the oldest waiting job, commits each step and page count while it runs, keeps the page count once the run moves on, loads the run's manifest.json and marks the job done.|
|`test_a_job_runs_every_step`|A job runs split, identify, transcribe and group.|
|`test_failed_run_is_marked_failed_with_its_reason_and_loads_nothing`|A failed model call marks the job failed with its reason, and nothing is loaded.|
|`test_a_failed_job_is_logged_with_its_full_error`|The worker logs a job's start and, when it fails, the step it failed during with the full error and traceback (the job keeps just the message).|
|`test_pdf_with_no_pages_fails_instead_of_loading_nothing`|A PDF with no pages fails with a reason instead of ending done with nothing loaded.|
|`test_stopping_the_worker_marks_its_job_failed`|Ctrl+C during a job marks it failed, so it doesn't show as running forever.|
|`test_job_cut_off_by_a_stopped_worker_can_be_run_again`|A job still marked running when the worker starts (killed or crashed) is marked failed, so it can be run again.|
|`test_an_item_of_another_series_runs_with_that_series_page_types_and_rule`|A job for an item another series lists runs into that series, with its grouping rule, record name and page types only.|
|`test_a_series_without_the_built_in_types_may_have_blank_pages_whenever_the_reading_model_sorts`|A series with no built-in page types may have blank pages when the reading model sorts or takes what this computer is unsure of, and not otherwise.|
|`test_the_retrained_weights_are_only_needed_when_the_model_on_this_computer_runs`|The active retrained model's weights file is looked up only when sorting is on this computer: with the reading model a missing file is no matter, and on this computer the job fails saying it is missing.|
|`test_local_sorting_without_pytorch_says_where_to_install_it`|Sorting on this computer without PyTorch fails the job saying to install it from Settings, then Page sorting, and runs nothing.|
|`test_an_item_of_the_prest_survey_runs_keeping_its_blank_pages_out`|An item the Wilfred Prest Survey lists runs as its, sorting into its types and dropping blank pages.|
|`test_an_item_no_series_lists_fails_without_running`|A job for an item no series lists is marked failed ("no series lists this item: add it to one first") and the pipeline is never run.|
|`test_only_one_worker_runs_at_a_time`|A second worker exits while one is running (two would run a bundle into the same output folder), and can start once the first has stopped.|

## `test_instructions.py`

Each series' transcription prompt and each page type's template as versions in the db (`backend/db/instructions.py`, `/instructions` and `/collections/{id}/prompt`).

| Test                                                                                      | What it checks                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_a_prompt_saved_with_only_its_line_endings_changed_is_no_change`                     | A series' prompt sent back with plain line endings instead of Windows ones (as a browser's text box does) is no change, so no new version makes jobs read pages again.                                                                                                                                                                                                                                        |
| `test_todays_prompt_and_templates_pass_the_checks`                                        | Today's `prompt.txt` and templates pass every check.                                                                                                                                                                                                                                                                                                                                                          |
| `test_a_template_that_would_break_the_pipeline_or_the_review_screen_is_refused`           | 14 cases: a template that isn't JSON or an object or has no fields, lacks `number_of_dwelling` (main, coded) or `text` (notes), has a field the pipeline fills in, `annotations`, `residents` or `other_children` in another shape, a name with a dot or capitals, a field that isn't null, its description (text) or an object, or makes the command line too long for Windows, is refused with that reason. |
| `test_an_empty_prompt_is_refused`                                                         | A blank prompt is refused.                                                                                                                                                                                                                                                                                                                                                                                    |
| `test_a_saved_template_becomes_the_newest_version_and_the_old_one_is_kept`                | `POST /instructions/main` saves a new version with its reviewer and note; it becomes the newest (what the next job reads with) and the history lists both, newest first.                                                                                                                                                                                                                                      |
| `test_versions_are_numbered_within_their_kind_and_only_the_newest_is_current`             | `GET /instruction-versions` lists every version oldest first, numbered from 1 within its kind (each template starts at 1; a prompt within its series), labelled "Prompt" or with its page type's label, with only the newest of each current; `GET /instructions/main` numbers its history newest first (2, 1); the prompt's is `GET /collections/1/prompt`, and `GET /instructions/prompt` is 404.           |
| `test_a_save_is_refused_when_unknown_unchanged_invalid_or_based_on_an_old_version`        | An unknown kind (404) or reviewer (400), no change, or a template with problems (400, listing them) is refused; a save based on a version that is no longer the newest is refused (409).                                                                                                                                                                                                                      |
| `test_accuracy_is_kept_apart_for_each_prompt_and_template_version`                        | `GET /accuracy` gives a row per prompt and template version, so versions can be compared.                                                                                                                                                                                                                                                                                                                     |
| `test_accuracy_can_be_limited_to_one_series`                                              | `GET /accuracy?collection=` counts only the pages of that series' items (two series each with a reviewed page: each gets its own, none gives both), and an unknown series gives nothing.                                                                                                                                                                                                                      |
| `test_each_series_has_its_own_prompt_history_and_a_save_changes_that_series_only`         | `POST /collections/{id}/prompt` saves a new version with its reviewer and note, numbered within its series; the other series' history, newest prompt and numbering are unchanged.                                                                                                                                                                                                                             |
| `test_a_series_is_read_with_its_own_prompt_and_page_types_templates_only`                 | What a job of a series reads with is that series' newest prompt and its page types' templates; a series with no prompt has none.                                                                                                                                                                                                                                                                              |
| `test_a_prompt_save_is_refused_when_unknown_unchanged_invalid_or_based_on_an_old_version` | An unknown series (404) or reviewer (400), no change, an empty prompt or one too long for the series' templates (400, listing them) is refused; a save based on a version that is no longer the series' newest, or on another series' prompt, is refused (409).                                                                                                                                               |
| `test_a_save_is_checked_with_its_own_series_only`                                         | A prompt is checked against its own series' templates (another series' broken template doesn't refuse it), and a template against its own series' prompt (too long for one series' prompt, fine with another's).                                                                                                                                                                                              |
| `test_a_new_series_starts_with_the_general_prompt_and_series_1_is_left_as_it_was`         | `POST /collections` gives the new series a version 1 of the general starting prompt (no reviewer): none of the Prest survey's page types, areas or fields, ending with the line the template follows; it can be edited, and series 1's history is as it was.                                                                                                                                                  |
| `test_instruction_versions_number_each_series_prompt_from_1`                              | `GET /instruction-versions` numbers each series' prompt from 1 with its own newest current and gives each version its `collectionId`; `?collection=` lists that series' prompt versions and every template.                                                                                                                                                                                                   |

## `test_field_rules.py`

A page type's field rules (`backend/db/checks.py`): saved with its template version, and a page's values that break them flagged for review (kind `invalid`).

| Test | What it checks |
| --- | --- |
| `test_a_value_breaking_its_rule_says_why` | 35 cases: required but blank or `/` (crossed out); `[?]` left alone (flagged as unreadable already); a number with thousands separators, out of its range or not a number; dates as 12 March 1917, 12/3/17 and Sept. 1917, an impossible or unreadable date, a date outside its range (a two-digit year has no century, so no range; a month in range as far as it goes); yes or no; one of a list by its code or its meaning, and a range of codes (000-996); several of a list, and an allowed value holding a comma; a pattern, said with its example; a number code as a number (1 is 01); an odd digit (①) without crashing; the card's own full stop, and a list's values with their own (Mrs.); a range saved as a number. |
| `test_rules_that_dont_fit_the_template_or_make_no_sense_are_refused` | 17 cases: a rule on a field the template lacks, on a group, or in a list (residents); an unknown type or key; required not true or false; a range that isn't numbers or dates, or runs backwards, or on a type with no range; a list with no values; a pattern missing, invalid, not text, repeating a repeat (which can take forever), or not matching its example; a range that isn't a number or a date. |
| `test_sensible_rules_pass` | Rules of each kind that fit the template pass. |
| `test_a_templates_rules_are_saved_with_it_changed_alone_and_refused_when_they_dont_fit` | `POST /instructions/main` saves rules with the template, and rules changed alone are a new version; rules for a field the template lacks are refused (400); versions list their rules (version 1 none); a prompt saved with rules is saved without them. |
| `test_a_loaded_items_values_that_break_their_rules_are_flagged_and_a_new_check_replaces_the_last` | Loading an item checks its pages against their types' newest rules and flags what breaks them; checking again replaces those flags and leaves other kinds of flag alone. |
| `test_a_page_read_again_is_checked_against_its_types_rules` | A page the worker reads again is checked against its type's newest rules. |

## `test_series_checks.py`

A series' checks across fields (`backend/db/checks.py`): saved as versions, and a record's values that fail one flagged for review (kind `check`).

| Test | What it checks |
| --- | --- |
| `test_a_check_says_why_it_fails` | 25 cases: fields added up against a field (pass and fail, with its own message); a crossed-out, unreadable or missing value can't be told; a field against a value; dates, to the precision both have; words only as the same or different; if a field is a value then another must be filled (the card's full stop ignored), and if one is filled another must be empty; a date with its full stop the same as without; a two-digit year can't be told; decimals that add up; nil as none; a check's own value (N/A) never unsure; words in brackets compared; a decimal point and ticks count. |
| `test_checks_that_name_no_field_of_the_series_or_make_no_sense_are_refused` | 11 cases: no id, an unknown kind, a field the series' templates lack, an unknown comparison, nothing to compare, fields and a value both or neither (or a blank value), an if with no value to be, on not true or false, a field that isn't a name. |
| `test_sensible_checks_pass_and_ids_are_their_own` | Sensible checks pass; two with one id, or checks not in a list, are refused. |
| `test_a_records_values_failing_a_check_are_flagged_on_each_field_it_names_and_checked_again_as_reviewers_left_them` | Checking a page checks its whole record: a failing check flags each field it names; a check across page types needs one page of each; a switched-off check isn't run; checking again uses a reviewer's saved correction and leaves other kinds of flag alone. |
| `test_a_series_checks_are_saved_as_versions_refused_when_they_dont_fit_and_an_old_one_can_come_back` | `/collections/{id}/checks` lists versions newest first, numbered; saves one with its reviewer and note; refuses checks naming a field the series lacks (400), no change (400) or an old base (409); an older version saved again is the newest; no checks at all is a version too; an unknown series is a 404. |
| `test_checking_a_series_again_is_a_task_that_flags_its_pages_and_logs_how_many` | `POST /collections/{id}/check` queues a task (one at a time per series), listed as "Checking …"; the worker checks every page, counting them, and logs the version of the checks and how many fields it flagged. |
| `test_a_page_waiting_to_be_read_again_isnt_checked_and_its_last_flags_go` | A page waiting to be read again isn't checked, its flags go, and its record's checks across page types wait for it. |
| `test_a_page_moved_to_another_record_is_checked_there_and_the_record_it_left_again` | Moving a page re-checks its new record and the one it left. |
| `test_a_page_changed_to_another_type_is_checked_against_that_types_rules` | Changing a page's type re-checks it: the old type's rule flags go. |
| `test_the_prest_surveys_checks_flag_what_its_validation_did` | 14 cases: Prest's checks, as its setup file (`setups/wilfred-prest-survey.prestcribe`) has them, with values as transcribed: dwelling numbers alike but for case, spaces and leading zeros (24A, 24 a), a missing letter or a stray full stop flagged, a value marked unsure (10/, 45(1)) not compared; industry and occupation codes compared as codes, digits only (013.3, 17?, 4309m can't be told); a municipality named by its code, a suburb not a council can't be told. |
| `test_the_prest_surveys_children_living_and_dead_add_up_to_the_total` | Living plus dead children must be the total. |
| `test_names_and_codes_are_checked_when_saved` | A names check needs one field each side; as is values or codes. |

## `test_page_sorting.py`

How pages are sorted into page types: on this computer (PyTorch) or by the reading model, as the Settings page says.

|Test|What it checks|
|---|---|
|`test_the_reading_model_names_each_pages_type_or_says_blank_and_anything_else_waits_for_review`|The reading model is shown each page with the series' page types by name and label, blank and unsure; a name of one of them (in any case) or blank is the page's label, anything else waits for review; progress is told each page.|
|`test_a_run_set_to_the_reading_model_sorts_with_it_and_flags_what_it_cant_place`|A run set to sort by the reading model asks it with the series' page types and the transcription choice, and flags a page it can't place for review.|
|`test_pages_are_asked_of_the_reading_model_at_once_and_come_back_in_order`|Pages are asked of the reading model several at a time (up to `READERS`), come back in page order, and progress is told after each page.|
|`test_a_page_whose_request_fails_waits_for_review_unless_every_request_fails`|A page whose request fails waits for review with no confidence; if every request fails, the first error is raised.|
|`test_page_sorting_is_by_the_reading_model_until_this_computer_is_chosen`|Unsaved, pages are sorted by the reading model; this computer can be chosen and is kept; any other choice is refused.|
|`test_without_pytorch_pages_are_sorted_by_the_reading_model_and_this_computer_cant_be_chosen`|Without PyTorch, pages are sorted by the reading model and choosing this computer is refused with why.|
|`test_a_cheaper_reading_model_can_sort_and_what_this_computer_isnt_sure_of_can_go_to_it`|A reading model for sorting, apart from the transcription one, and sending what this computer isn't sure of to it, are saved without changing the method; an unknown provider is refused.|
|`test_pages_this_computer_isnt_sure_of_are_asked_of_the_reading_model_when_set`|With that set, the pages this computer is unsure of, or sorts into a type the series hasn't, are asked of the reading model with the saved choice.|
|`test_checks_asked_for_at_once_load_the_sorting_model_once_and_its_pass_is_remembered`|Several `POST /page-sorting/check` at once load the sorting model once, and a pass is remembered.|

## `test_settings_api.py`

What the Settings page's Updates card and Open folder buttons and the home page's Save a PrestCribe file ask of the API: `GET /version`, `POST /update`, `POST /folders/{which}/open` and `GET /state`. Nothing is fetched from GitHub, no installer is started, no folder is opened (what would open one is only recorded, under each platform in turn, inside a temporary folder), and the timer that stops this copy after an update is only recorded: the real one would end the test run.

|Test|What it checks|
|---|---|
|`test_a_copy_not_installed_from_a_release_has_no_version_and_isnt_updatable`|With no `VERSION` file, the current version is none, the latest release is GitHub's (asked once, with a time limit), and it isn't updatable.|
|`test_an_installed_copy_is_updatable_only_when_the_latest_release_is_another_version`|The version is read from `VERSION`, trimmed; it is updatable when the latest release differs, not when it is the same.|
|`test_when_github_cant_be_reached_or_understood_the_error_is_said_and_nothing_is_updatable` — 3 cases|A failed request, a reply with no release, or one that isn't JSON gives no latest release, no notes, "Couldn't reach GitHub to check for updates." and not updatable.|
|`test_the_latest_releases_notes_are_its_body_trimmed_and_cut_to_5000_characters_or_none` — 8 cases|`notes` is the latest release's body with the space around it trimmed, then cut to 5000 characters; none when the body is missing, null or not text (a number, a list, an object).|
|`test_the_time_it_was_checked_is_now_in_utc`|`checkedAt` is an ISO time in UTC between just before and just after the request.|
|`test_the_computer_it_runs_on_is_given_with_whether_pages_can_be_sorted_on_it` — 2 cases|`system` holds `os` (ending in the chip), this Python's version and `pytorch`, whether PyTorch is installed here (true or false).|
|`test_the_system_is_named_with_its_version_and_chip` — 3 cases|`system_info()` names Windows and Linux by system, release and chip, and a Mac as "macOS" with its macOS version (not the kernel's) and chip.|
|`test_a_copy_not_installed_from_a_release_cant_be_updated_and_is_told_to_use_git`|`POST /update` on such a copy is a 400 saying to update it with git pull, and starts nothing.|
|`test_updating_starts_the_installer_in_its_own_process_for_this_folder_then_stops_this_copy`|On an installed copy it answers 202, fetches the installer from the latest release (with a 10 second limit), starts it in its own process (a new console on Windows) for this folder, and sets a one-second timer to stop this copy.|
|`test_tasks_waiting_or_running_hold_an_update_back_and_nothing_is_started`|With a task waiting or running, `POST /update` is a 409 ("Wait for the tasks to finish before updating.") and starts nothing.|
|`test_an_installer_that_cant_be_downloaded_is_a_502_and_nothing_is_started`|An installer that can't be fetched is a 502 ("Couldn't download the installer: ...") and starts nothing.|
|`test_an_installer_that_cant_leave_the_apps_job_is_started_in_it`|On Windows the installer is started out of the app window's job, so it outlives the app it replaces; if the job doesn't allow that, it is started in it instead.|
|`test_a_folder_with_an_apostrophe_is_escaped_in_the_windows_installer_command_which_waits_for_enter_if_it_fails`|On Windows a folder name with an apostrophe is escaped in the PowerShell command, which prints the failure and waits for Enter.|
|`test_a_folder_with_an_apostrophe_is_quoted_in_the_installer_command_on_a_mac_or_linux_which_runs_only_a_downloaded_script`|On a Mac or Linux the folder is shell-quoted and the installer is run only once downloaded to a file, never piped as it arrives.|
|`test_a_saved_file_holds_everything_unless_only_the_setup_is_asked_for`|`GET /state` has every table's rows, saved model answers included, named `.prestcribe`; `?content=everything` is the same.|
|`test_a_setup_only_file_keeps_the_series_and_how_theyre_read_but_no_pages_or_this_computers_choices`|`?content=setup` keeps the series, page types, record levels and people, leaves out bundles, pages, fields, saved model answers and this computer's settings, is named "PrestCribe setup", and leaves what is here as it was.|
|`test_a_file_can_be_saved_as_only_everything_or_the_setup`|Any other `content` is refused (422).|
|`test_a_folder_is_made_and_opened_the_way_this_computer_opens_folders` — 6 cases|`POST /folders/data/open` and `/folders/output/open` make the folder (and the ones above it) and answer 204 with nothing; it is opened with `os.startfile` on Windows, `open` on a Mac and `xdg-open` elsewhere, with the folder's full path.|
|`test_a_folder_already_there_is_opened_as_it_is`|A folder that is there is not made again, what is in it is kept, and it can be opened again.|
|`test_only_the_data_and_output_folders_can_be_opened` — 3 cases|Any other `which` (`elsewhere`, `DATA`, `scans`) is refused (422): nothing is made or opened.|
|`test_a_folder_that_cant_be_opened_is_a_500_saying_why` — 3 cases|An `OSError` from `os.startfile` (Windows) or from starting `open` or `xdg-open` is a 500, "The folder couldn't be opened: ..." with the error.|
|`test_a_folder_that_cant_be_made_is_a_500_and_nothing_is_opened`|A file where the folder should be is a 500 with the same message, and nothing is opened.|
|`test_the_reason_a_folder_couldnt_be_opened_is_cut_to_300_characters`|The whole message, "The folder couldn't be opened: ..." included, is cut to 300 characters.|
|`test_a_setup_only_file_opened_here_keeps_this_computers_own_choices_and_saved_answers_and_what_was_here_is_backed_up`|`POST /state` with a setup-only file (no app settings) keeps this computer's own settings, such as page sorting, and its saved model answers alongside the file's, takes the rest from the file, and backs up what was here.|
|`test_a_check_that_cant_download_the_sorting_model_says_to_check_the_internet` — 5 cases|`POST /page-sorting/check` failing with a URL, connection, name lookup or `requests`-style connection error, or one caused by such an error, says to check the internet.|
|`test_a_check_that_fails_any_other_way_doesnt_blame_the_internet` — 3 cases|Any other failure (a DLL that won't load, a missing file, a bad value) is "Page sorting on this computer failed: ..." with the error.|

## `test_local_sorting.py`

`GET` and `POST /page-sorting/install`, which installs PyTorch with `uv sync`. `uv` is faked: nothing real is run.

|Test|What it checks|
|---|---|
|`test_installable`|Where `uv` is found, the install can be started, with nothing running yet.|
|`test_not_installable_without_uv`|Without `uv` it is not installable, says why, and `POST` is a 400 that starts nothing.|
|`test_not_installable_on_intel_mac`|An Intel Mac can't install PyTorch (said, and `POST` is a 400); an Apple chip can.|
|`test_post_runs_uv_then_reports_ok`|`POST` answers 202 and runs `uv sync` with the local sorting extra, `GET` reports running and then ok with the seconds taken, and import caches are refreshed.|
|`test_failure_detail_is_the_last_lines`|A failed install is not ok and its detail is the last 20 lines of `uv`'s output.|
|`test_second_post_while_running_is_409`|A second `POST` while one runs is a 409 and starts nothing.|
|`test_already_installed_runs_nothing`|With PyTorch already installed, `POST` answers ok without running `uv`.|

## `test_page_types.py`

Page types added from the review screen, and a page read again as another type.

| Test                                                                       | What it checks                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_a_read_that_fails_while_the_page_is_swapped_leaves_it_as_it_was`     | A model answer the db can't take fails the job, and the page keeps its fields, type and revision: the swap is all or nothing.                                                                                                                                                                     |
| `test_a_page_read_again_counts_for_accuracy_only_once_a_reviewer_saves_it` | A page read again isn't counted by `GET /accuracy` until a reviewer saves it.                                                                                                                                                                                                                     |
| `test_a_new_page_type_needs_a_template_before_pages_are_read_as_it`        | `GET /page-types` lists the built-in four with their templates; a new type needs a lower-case name that isn't taken or reserved (`blank`) and a known reviewer; a page can't be read as it until it has a template (`other` can't have one); then `PUT /pages/{id}/type` queues a page job, once. |
| `test_a_page_types_label_is_what_people_see_and_is_unique_in_its_collection` | A new page type's label is what people see (its name when none is given); a blank label is refused (400), and one a type in the series has already, built-in labels included, is refused (409) saying so. |
| `test_reading_a_page_again_without_a_choice_uses_the_saved_one_or_is_refused` | `PUT /pages/{id}/type` without a model, provider and effort is refused with 409 and the Settings message when nothing is saved, and queues the saved choice otherwise. |
| `test_a_part_of_a_choice_is_checked_like_a_whole_one` | A part given on its own (a bad effort, provider or model) is refused with 400 even when the rest comes from the saved choice. |
| `test_the_unknown_setting_decides_not_the_name_other` | The page type a series marks Unknown, whatever its name, can't have a template, empties a page changed to it at once and flags it; `other`, no longer Unknown, needs a template like any type. |
| `test_page_type_job_records_selected_transcription_model` | A page read again as another type queues a job with the model, provider and effort given (a blank model is refused). |
| `test_a_page_made_other_is_emptied_at_once`                                | Making a page `other` empties it to one blank text field at once and moves its revision on.                                                                                                                                                                                                       |
| `test_a_page_keeps_its_type_once_reviewed_or_when_the_change_is_unknown`   | An unknown page (404), page type (400) or the type it already has (400) is refused, and so is any change once the page has a saved review (409).                                                                                                                                                  |
| `test_the_worker_reads_the_page_again_and_swaps_what_was_read`             | The worker reads the page's scan (a WebP converted to JPEG) with the new type's newest template, then swaps the page's fields, type, model, prompt and template versions and revision in one go.                                                                                                              |
|`test_a_page_is_read_again_with_its_own_series_prompt_and_records_that_version`|A page of series 2 read again is read with series 2's prompt and records that prompt version and its template's, not series 1's.|
|`test_a_page_of_a_series_with_no_prompt_is_not_read_again`|A page of a series with no prompt is not sent to the model: its job fails saying the series has no prompt, and the page keeps its fields.|
| `test_a_page_reviewed_while_it_is_read_again_is_left_as_it_was`            | If a review is saved while the page is being read, the job fails with that reason and the page is left as it was.                                                                                                                                                                                 |

## `test_suggest_types.py` — 41 test cases

Page types suggested from an item's pages: pages picked, laid on a contact sheet and shown to the chosen model, which proposes page types for the series to add.

|Test|What it checks|
|---|---|
|`test_pages_are_spread_evenly_starting_with_the_first`|`pick` spreads the pages evenly over the item, starting with its first.|
|`test_random_pages_are_in_order_without_repeats_and_the_same_for_the_same_seed`|Random pages come back in page order without repeats, the same for the same seed.|
|`test_a_range_is_clamped_to_the_item_and_the_pages_are_spread_over_what_is_left_of_it`|A range is clamped to the item and the pages are spread over what is left of it.|
|`test_an_item_with_no_more_pages_than_asked_for_gives_all_of_them`|An item with no more pages than asked for gives all of them.|
|`test_no_more_than_30_pages_are_picked_and_at_least_one`|No more than 30 pages are picked, and at least one.|
|`test_a_contact_sheet_is_one_jpeg_with_a_numbered_tile_for_each_page_in_the_order_given`|A contact sheet is one JPEG with a numbered tile for each page, in the order given.|
|`test_pages_of_different_shapes_are_each_drawn_as_wide_as_a_tile_in_a_row_as_high_as_the_tallest`|Pages of different shapes are each drawn as wide as a tile, in a row as high as its tallest.|
|`test_a_very_tall_page_is_shrunk_to_fit_and_each_row_is_as_tall_as_its_own_tallest_tile`|A page far taller than a tile is shrunk to fit (the sheet stays bounded), and each row is as tall as its own tallest tile.|
|`test_a_contact_sheet_of_one_page_is_that_page_and_its_number`|A sheet of one page is that page and its number.|
|`test_the_model_is_asked_once_about_a_sheet_of_the_pages_and_its_tiles_are_taken_for_their_page_numbers`|The model is asked once about the sheet, and the tiles it names are taken as their page numbers.|
|`test_tiles_that_are_not_on_the_sheet_are_ignored_and_a_kind_with_none_left_has_no_pages`|Tiles not on the sheet are ignored, and a kind with none left has no pages.|
|`test_a_kind_named_again_or_with_no_name_is_dropped_and_names_and_descriptions_are_tidied`|A kind named again or with no name is dropped; names and descriptions are tidied.|
|`test_an_answer_with_no_kinds_gives_none` — 4 tests|An answer with no kinds (empty, null, an empty list, or another key) gives none.|
|`test_the_prompt_counts_the_pages_and_names_the_page_types_the_series_has_and_what_the_person_said`|The prompt counts the pages, names the series' page types and carries the person's hint.|
|`test_a_request_the_model_cant_answer_is_not_caught_here`|`suggest` lets the model's error through.|
|`test_suggesting_asks_the_chosen_model_once_about_the_picked_pages_and_adds_nothing`|`POST /collections/{id}/page-types/suggest` asks the chosen model once about the picked pages and adds no page type.|
|`test_the_pages_can_be_picked_at_random_or_from_a_range_and_are_16_unless_asked_otherwise`|Pages are picked at random or from a range, and are 16 unless asked otherwise.|
|`test_a_range_with_no_pages_in_it_is_400_and_the_model_isnt_asked` — 3 tests|A range starting past the item's end, or ending before it starts, is a 400 saying how many pages the item has, and the model isn't asked.|
|`test_the_400_for_an_empty_range_counts_a_one_page_item_in_the_singular`|The 400 for an empty range says "1 page" for a one-page item.|
|`test_suggesting_with_no_transcription_model_chosen_is_refused_before_anything_is_asked`|With no transcription model chosen it is refused with 409 before the model is asked.|
|`test_a_request_the_endpoint_cant_make_sense_of_is_422` — 7 tests|A count outside 1-30, a hint over 1000 characters, an unknown pick, a range end below 1 or a count that isn't a number is a 422.|
|`test_a_request_with_no_item_is_422_and_the_most_it_allows_is_30_pages_and_a_1000_character_hint`|No item is a 422; 30 pages and a 1000-character hint are the most allowed.|
|`test_a_model_that_cant_answer_is_a_502_with_what_it_said`|Any failure (the model's, or drawing the sheet) is a 502 "Page types couldn't be suggested" carrying what was said.|
|`test_an_item_the_series_doesnt_list_or_has_no_pdf_for_is_404_and_the_model_isnt_asked` — 6 tests|An item the series doesn't list, or has no PDF for, is a 404 and the model isn't asked.|
|`test_an_items_pdf_not_here_yet_is_downloaded_first_and_an_archive_that_cant_send_it_is_a_502`|An item's PDF not here yet is downloaded first; an archive that can't send it is a 502.|

## `test_add_items.py`

A series' items listed from the archive (a fake archive here) and added to its list, one by one or the whole list as a queued task, then run into that series.

|Test|What it checks|
|---|---|
|`test_a_series_items_are_listed_from_the_archive_saying_which_have_scans_and_which_are_listed_already`|A page of a series' list comes back with each item's title, identifier and number; an item with no scans or for the Reading Room only can't be downloaded; one a series lists is marked; the search and page are asked for oldest first.|
|`test_listing_needs_a_series_linked_to_an_archive_that_answers`|A series with no archive series can't list items (400), and an archive that can't be reached says so (502).|
|`test_chosen_items_are_added_once_the_archive_shows_them_in_this_series`|Chosen items are added once the archive's page shows each in this series; one of another series, one a series lists already, and a number the archive doesn't know are refused with the reason; no download page is read.|
|`test_an_added_item_is_listed_and_run_under_its_series_only`|An added item is listed under its series, not the Prest survey's, can be run, and its job counts on its series only.|
|`test_a_series_linked_without_its_identifier_checks_items_against_the_archives`|A series stored without its archive identifier checks items against the identifier the archive shows for it, and refuses to add when the archive shows none.|
|`test_an_item_number_out_of_range_is_refused`|An item number below 1 or too big for the db is refused with the reason.|
|`test_adding_a_series_whole_list_is_queued_and_the_worker_adds_each_downloadable_item_no_series_lists`|Adding a whole list (or a search's) queues a task, once per series at a time; the worker goes through every page of it, saving each downloadable item no series lists, and its progress counts the items gone through of those listed.|
|`test_a_list_too_long_for_the_archive_to_show_is_added_a_box_at_a_time_and_logged`|A list the archive can't show whole (10,000 or more) is gone through a unit (box) at a time, without paging the capped list, and counted against the series' item count. Each page it reads is logged with its box, how many it has read and added, and the end with how many it skipped. An item listed by hand while the task runs isn't counted as added by it.|
|`test_adding_a_list_from_an_archive_that_cant_be_reached_fails_the_task_with_the_reason`|A task that can't reach the archive, even when asked again, fails with the reason.|
|`test_tasks_say_what_each_job_is_how_far_it_has_got_and_where_to_see_it`|The Tasks list gives running tasks first, then finished ones newest first, each with what it is, its progress in items or pages, its error, its series and where to see it.|
|`test_a_task_comes_with_its_log_oldest_first_when_it_started_what_it_has_added_and_whether_a_worker_runs`|One task comes with its own lines in the worker's log and the files it rotated to, oldest first, from its last "started" line on (not an older db's job with its id, and none for a waiting task), and when it started (the log's local time as UTC); what its latest count line says it has added and skipped; an items task's series' items now; and whether a worker is running, from its heartbeat file (unknown with none, no after a minute without a beat). A task not yet started has no log, and one that isn't there is a 404.|
|`test_a_run_saves_the_series_it_is_loaded_into`|A run's manifest names the series its item is loaded into.|
|`test_an_added_items_pdf_is_its_newest_original_looked_up_when_it_is_downloaded`|An added item's PDF is its newest original, found on its download page when it is downloaded; an item with none says so.|
|`test_a_page_takes_only_a_page_type_of_its_own_series`|Changing a page's type to another series' type is refused.|
|`test_sorting_gives_only_the_series_own_page_types_and_sends_the_rest_to_review`|Sorting's label outside the series' page types becomes review, and is flagged.|
|`test_an_upload_cant_take_the_number_of_an_item_added_from_the_archive`|An upload can't use the number of an item added from the archive, nor give another number a PDF named as that item's.|
|`test_an_items_pages_can_be_seen_before_it_is_read_its_pdf_downloaded_once_to_where_reading_it_looks`|An item's count of pages and each page as a scan can be had before it is read, its PDF downloaded from the archive once into the place reading it looks, the item still listed once and unread; a page it hasn't, another series' item, and one the archive has no PDF of are refused (404, 404, 502).|
|`test_an_item_of_the_archives_known_pdfs_is_seen_from_its_pdf_there`|An item whose archive PDF is recorded (`ArchiveItem.pdf`) is downloaded as that PDF and seen from it; a page asked for wider than the large size comes at that size.|
|`test_an_items_pages_are_said_to_be_its_series_page_types_before_it_is_read`|A page of an item not yet read is said to be one of its series' page types, said again as another, or unsaid; another series' type, its Unknown one, a type that isn't there and page 0 are refused, and another series can't see the item's labels.|

## `test_series_items.py`

A series' dashboard asks for a page of its items at a time, searched, filtered and counted on the server.

|Test|What it checks|
|---|---|
|`test_items_come_a_page_at_a_time_in_order_of_their_numbers_with_their_counts_and_the_series`|Items come a page at a time in order of their numbers (2, 9, 10, 100), each with its pages' counts and records (an item being transcribed, those so far), with how many match and how many there are, the counts of all the series' pages, the most pages and records any item has, and a page past the end gives the last.|
|`test_items_are_found_by_number_title_or_identifier_and_by_status`|Search finds an item by its number, title or identifier, any case; each status filter finds the items the dashboard always showed for it.|
|`test_an_item_is_given_by_its_number_or_bundle_id_with_its_pages`|One item comes with its pages; an item not loaded has none; an unknown item or series is 404.|
|`test_a_record_names_its_item_as_the_dashboard_does`|A record's response names its item and its archive title, for the review screen's crumb.|
|`test_an_item_gives_its_records_and_a_record_the_ones_it_sits_inside_top_first`|An item comes with its records, each with the one it sits in, and a record with the records it sits inside, top first, each named by its level (not one holding just it and no pages, which the item's page opens past), itself named by its own.|
|`test_an_item_that_is_one_record_gives_it_so_the_dashboard_opens_it_straight_away`|An item's row gives its record only once all its pages are in it (a page in none, or another item: none), and the record then says it is its whole item.|
|`test_an_item_found_in_two_places_under_the_data_folder_is_listed_once_and_its_pages_counted_once`|An item whose PDF is found twice under the data folder (the same file name in two folders) is listed once, from the first copy in order, in the items and in the series' bundles; the series counts it once and its pages once.|
|`test_the_items_transcribed_are_all_the_loaded_ones_whatever_page_search_or_status_is_asked_for`|The count of a series' items transcribed (loaded) is of all its items, whichever page, search or status is asked for, as the count of all its items is.|

## `test_record_levels.py`

A series' levels of record (`PUT /collections/{id}/levels`), each with its name and what one is made of, in order, which the
pipeline's group step reads; a series with none has each item as one record.

|Test|What it checks|
|---|---|
|`test_prest_has_one_level_its_surveys_and_a_new_series_none`|The Prest survey has one level, its surveys (main pages start one, coded cards join by `number_of_dwelling`), and is grouped; a new series has none, its records are called "record", and each item is one.|
|`test_a_level_is_named_in_lower_case_and_made_of_its_series_page_types_in_order`|A level's name is stored in lower case with single spaces and what one is made of in order; a bad name, another series' or an Unknown page type, a page type twice, a first one that doesn't start one or a later one that does, one matched by number with no number field, a number field with no page types to read it from, a bad field name, or a number field missing from a type's template (or a list or group of fields there) is refused with the reason, and nothing refused is saved.|
|`test_the_number_field_must_stay_in_the_templates_of_the_page_types_that_group_by_it`|A template that drops a level's number field is refused while a type of that level groups by it, and saved once the level groups by page order.|
|`test_with_no_levels_each_item_is_one_record_and_with_one_its_page_types_start_them`|A record of a series with no levels is a "record" with its free text under "Record details" and an Unknown page just to be checked; with a level its type starts, the series is grouped and its records take the level's name; with none again each item is one record.|
|`test_an_unknown_page_grouped_with_others_is_flagged_as_part_of_their_survey`|An Unknown page in a Prest survey with other pages is flagged as in that survey because it follows the survey's first page, with its free text under "Survey details".|
|`test_a_record_with_too_many_or_too_few_of_a_part_or_a_page_type_it_isnt_made_of_is_flagged`|Grouping flags a record with more of a part than it may have (at most one notes page, exactly one coded card), fewer (no coded card, or no notes page where there must be at least one), or a page type it isn't made of, but not an Unknown page, which is flagged as unread.|
|`test_a_level_isnt_flagged_for_the_page_types_of_the_levels_below_and_its_problems_are_its_own`|A box holding surveys isn't flagged for their coded cards, which it isn't made of, and what it lacks is said of the box, though its first page is also its first survey's.|
|`test_a_page_is_shown_small_from_its_items_pdf_or_its_scan_here_and_never_fetched`|`GET /pages/{id}/thumbnail` draws a page 240 pixels wide, as a JPEG, from its item's PDF on this computer, else from its own scan here whatever the page is called, else from the one the archive sent before (kept in `OUTPUT/scans`); a page past the PDF's end, of an item with no PDF or scan here, unknown or called by no number with no scan of its own is 404, and one whose scan arrives later is drawn then; the archive is never asked.|
|`test_levels_tried_on_an_item_read_show_its_records_by_the_numbers_reviewers_saved_and_save_nothing`|`POST /collections/{id}/levels/preview` groups an item already read by levels not yet saved, from its page types and the numbers reviewers last saved (a corrected coded card joins its survey without a flag), with each record's pages, each page's type and each problem on a page with the record it's about; nested too, a box made of notes not flagged for its surveys' pages; saving nothing; an unknown item is 404 and a bad level refused as saving would.|
|`test_levels_nest_top_first_and_a_page_type_can_need_a_number_field_for_each_level_it_groups`|A series' levels are saved top first, the bottom one naming its records; a page type grouping in several levels needs each one's number field; two levels can't share a name, and a refused save keeps the levels there were.|
|`test_a_record_inside_another_says_so_is_named_by_its_level_and_its_export_keeps_it`|A record inside another gives its parent (none at the top) and is called by its own level's name (folder, letter), on its own and in its item's export; a record holding only records isn't exported; a record goes when the record it sits in goes.|
|`test_an_unknown_page_of_an_item_that_is_one_record_isnt_said_to_follow_its_first_page`|In a series with no levels, an Unknown page sharing the item's record with others is just to be checked, not said to follow the record's first page.|

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
| `test_a_bundle_job_sorts_with_the_active_model`                                  | With sorting on this computer, a bundle job sorts pages with the active model's weights; if that file is gone, the job fails saying so.                                                                                                                                                                               |
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
|`test_a_page_can_be_changed_to_any_type_of_its_collection_which_are_listed_by_label`|A page's actions list its series' page types by label; another series' type is refused (400), and one of its own is accepted.|
|`test_transcription_requires_template_and_valid_model_details`|Rejects invalid model settings and transcription of a page type without a template.|
|`test_other_does_not_require_transcription_but_main_does`|Changing Main → Other → Main updates the transcription requirement correctly in both the API response and database.|

## `test_page_history.py`

It checks read-only, page-scoped history, archived reviews, moves, empty history, and missing pages.

## `test_uploads.py`

`POST /bundles/upload`: each upload says which series it is for. A bundle is one PDF, or a folder of page images that share a bundle number. Duplicates are refused without changing existing files or database records.

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
| `test_an_upload_needs_a_series_and_an_item_number_stays_with_its_first` | An upload for a series that isn't there is refused ("Choose the series these files are for.") and one with no series is 422; the first upload of an item number records its series, and later files for that number under another series are refused (409) without recording another. |

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

## `test_export_api.py` — 18 test cases

checks the export endpoints using the test client and database fixtures.

| Test                                                    | What it checks                                                                                                            |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `test_export_latest_saved_value_and_source` — 5 cases   | Exports the latest saved correction, including empty strings, `/`, `[?]` and null values, with the correct review status. |
| `test_bundle_includes_all_surveys_and_unassigned_pages` | Bundle exports include all surveys, empty surveys and unassigned pages. The bundle list returns its ID and display name.  |
| `test_export_rejects_invalid_selection`                 | Missing, blank or conflicting selections return 400; unknown survey or bundle IDs return 404.                             |
| `test_bundle_export_uses_id_and_excludes_other_bundles` | Bundle selection uses the database ID, trims whitespace and excludes other bundles even when their display names match.   |
| `test_review_survey_identifies_current_bundle`          | The survey response includes the bundle ID needed by the Current bundle export option.                                    |
| `test_series_export_names_and_orders_the_items`         | A series export is a zip named for the series: a file per item in numeric item order, with its series and item objects.   |
| `test_series_export_numbers_pages_and_records`          | Pages are in page-number order; records are numbered by first page, not by ID; a page in no record has null.              |
| `test_series_export_reviewed_values_and_decoded`        | Reviewed values replace the model's; reviewed is true only when every field is; decoded appears only for meanings.        |
| `test_series_export_folder_without_identifier`          | A series with no archive identifier is named from its name, with every other character turned into an underscore.         |
| `test_series_export_refuses_unknown_or_untranscribed`   | An unknown series, or one with nothing transcribed (even if another series has items), returns 404 with the reason.       |
| `test_series_export_build_reports_progress_then_the_zip` | POST answers 202 with the build's id and item count; polling counts the items done, never down, up to the total, then gives a zip with the same files as the synchronous export. |
| `test_series_export_build_is_forgotten_once_collected`  | An unknown build, one asked about under another series, and one already collected all return 404 "No such export."; a collected build is forgotten. |
| `test_series_export_build_that_fails`                   | A build that raises answers 500 "The export failed: <reason>" and is forgotten.                                           |
| `test_series_export_build_refuses_unknown_or_untranscribed` | Starting a build for an unknown or untranscribed series returns the same 404 reasons as the synchronous export.       |

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

