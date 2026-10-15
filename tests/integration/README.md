# Integration tests

Multiple pieces of the pipeline wired together through their real entry points —
`run.main`, `step_split`, `process_image`, the shipped identification model, the
committed transcription results — instead of individual functions in isolation.
Fixture data (`identify/`, `preprocess/`, `group/`, `archive/`, `validate/`) lives alongside the test files
in this folder, and `backend.pipeline.identify.identify` reads its labelled pages
from here directly.

```bash
uv run pytest tests/integration
```

## `test_split.py`

PDF → page images (`step_split`). The theme is all-or-nothing publication: a failed
re-render must never leave a half-updated `pages/` folder.

| Test | What it checks |
|---|---|
| `test_shorter_pdf_replaces_old_page_images` | Re-splitting a now-shorter PDF removes stale page images instead of leaving them behind. |
| `test_failed_first_render_publishes_no_partial_images` | A render failure on a first run publishes no `pages/` folder at all. |
| `test_failed_rerender_preserves_all_previous_images` | A render failure on a re-run leaves the previous images byte-identical. |
| `test_failed_publication_restores_previous_images` | If the final rename fails, the previous images are restored. |
| `test_failed_publication_and_restore_retains_previous_images` | If the restore *also* fails, the old images are retained in a `.split-*/previous` staging dir and its path is attached to the raised error. |
| `test_image_folder_is_used_without_changes` | A folder of images as input is read in place: no output written, source untouched. |
| `test_pdf_not_on_this_computer_is_downloaded_from_the_archive_and_kept` | A PDF not on this computer is downloaded from the archive (faked here) after opening its bundle's download page, saved in `DATA` under the archive's name, then split as usual; no part-downloads are left behind. |
| `test_pdf_the_archive_cannot_send_stops_the_run_and_keeps_nothing` | A PDF the archive breaks off halfway (fewer bytes than it announced), or doesn't have, stops the run saying why; nothing is left in `DATA` and no `pages/` folder is published. |
| `test_a_long_pdf_is_split_on_every_core_in_page_order` | A 40-page PDF, more than one 16-page chunk so several processes draw it, gives all 40 pages named in page order, each the same image as drawing that page alone. |
| `test_a_page_that_fails_to_draw_is_named_in_an_error_a_worker_process_can_send_back` | A page that fails to draw gives a RuntimeError naming the PDF and page ("survey.pdf, page 1: ...") that survives pickling, the way a worker process sends its error back, even when the original error can't be pickled, as PyMuPDF's can't. |

## `test_preprocessing.py`

Preprocessing (the review screen's cleaned-up view) against the real fixture scans in `preprocess/`.

| Test | What it checks |
|---|---|
| `test_output_modes_preserve_original`  | Output pixels match the mode (colour, greyscale, or the app's black and white) and the source file is byte-identical afterwards. |
| `test_skewed_image_detection` | The real `skewed_image_1.jpg` fixture is detected confidently at 1.57° ± 0.3°. |
| `test_crop`  | Page crop on the real `crop.png`: output matches the independently measured paper size, the returned corners enclose all handwritten content, and dark scanner border pixels at least halve. |

## `test_run.py`

Resume and idempotency for `backend.pipeline.run`. The thread running through all of it: retry
unfinished work, never skip an unprocessed survey, never repeat a paid transcription
call that was already saved. The fixture stubs the two expensive boundaries —
`identify.identify_pages` and `transcribe.transcribe` — and **fails the test outright**
if a live transcription model is ever called; everything else runs for real.

| Test  | What it checks |
|---|---|
| `test_failed_identification_is_retried`  | After identification fails, the manifest records only `split` and the survey stays in `unprocessed()`; a later successful run completes it; a completed survey is then skipped even if identification would fail again. |
| `test_pdfs_in_bundle_folders_are_found` | `uv run survey` with no PDF named finds the PDFs in DATA's bundle folders (`DATA/216412/a.pdf`), not only ones directly in DATA, and ignores PDFs inside the output folder. |
| `test_transcription_is_selected_only_when_requested`  | Transcription runs only under `--transcribe`, and a second `--transcribe` run makes no further calls. |
| `test_failed_explicit_rerun_clears_old_completion`  | An explicitly requested rerun that fails clears the previous completion rather than leaving a stale "done" marker. |
| `test_invalid_manifest_does_not_hide_input`  | Truncated, `null`, malformed and non-UTF-8 manifests all leave the survey visible to `unprocessed()` instead of silently hiding it. |
| `test_interrupted_transcription_reuses_saved_pages`  | Pages are read in parallel: a `SystemExit` on page 2 keeps page 1's saved result; the retry re-calls only page 2, and page 1's file is byte-identical. No paid retry happens without the flag. |
| `test_failed_transcription_stops_without_reading_the_queued_pages` | With one reader, a `SystemExit` on page 1 stops the run with that error and the page still waiting is never read (paid). |
| `test_run_reports_each_step_and_transcription_progress`  | A run's `progress` callback hears each step start and every transcribed page (done / total), which the worker saves on the job. |
| `test_transcription_reuse_requires_matching_inputs_and_result`  | Cache invalidation: a changed image, label, model, effort, prompt, template, deleted result or edited result each force the right number of re-calls. |
| `test_legacy_completed_manifest_still_skips_input`  | An older manifest format still counts as complete. |
| `test_failed_json_publication_keeps_previous_progress`  | A failed atomic write leaves the old manifest byte-identical and drops no temp files. |
| `test_a_job_reads_each_page_with_its_texts_and_skips_a_page_type_with_no_template` | Given a job's texts (the db's newest prompt and templates), `step_transcribe` reads each page with them, skips a page type they have no template for, and records the prompt's hash for reuse. |
| `test_a_run_sorts_its_pages_with_its_sorting_model` | A run given a retrained model's weights sorts its pages with them. |
| `test_a_damaged_manifest_is_logged_before_the_run_starts_again` | A run's manifest.json that isn't JSON, or isn't a JSON object, reads as empty (the run starts again from the beginning) and logs one warning saying why; a run with no manifest yet logs nothing. |

## `test_identify.py`

Page-kind classification over every labelled page in `identify/pages/`.
**zero wrong answers**, and at least `MIN_COVERAGE` of pages answered, plus

| Test | What it checks |
|---|---|
| `test_shipped_weights` | The committed model scored against pages it was trained on. Catches a corrupted or mismatched weights file. |
| `test_held_out` | 5-fold: trains on 4/5 and scores the 1/5 never seen, so every page is judged by a model trained without it. This is the honest accuracy number. |

## `test_group.py`

Pages → surveys (`step_group`), from stored transcriptions: no model calls.

| Test | What it checks |
|---|---|
| `test_cards_join_the_main_form_with_their_number` | On a made-up bundle, each coded card joins the main form with its dwelling number (before or after it, or misfiled far away), second main sheets and flats (24A, 24B) stay separate surveys, and unreadable or reused numbers are flagged. |
| `test_real_bundles_group_like_ash` | 19 real bundles (`group/`, Opus 5.5 transcriptions + Ash's hand grouping of 589 surveys): at least `BASELINE` surveys match Ash exactly, and every one that does not is flagged for a human. |

## `test_scans.py`

The archive's real download page for Box Hill 00 (bundle 216412), saved as `archive/download_216412.html`, so the
code that reads it is checked against the archive's own markup, not only the tests' stand-in.

| Test | What it checks |
|---|---|
| `test_the_archives_real_download_page_gives_every_page_its_file` | Reading the real page finds all 227 pages in order, each with its file id (page 1 → 423448, page 227 → 425881). |
| `test_no_test_reaches_the_internet` | A plain `urllib` request to the archive fails during tests: `tests/conftest.py` blocks every internet lookup but this computer's own. |
| `test_a_scan_the_archive_cant_send_is_logged_with_the_reason` | A page scan the archive can't send comes back as none and logs one warning naming the bundle, the page and the error, and when the archive is asked again. |

## `test_migrations.py`

| Test | What it checks |
|---|---|
| `test_migrations_match_the_models` | The migrations in `backend/db/migrations/` build the same tables and columns as `backend/db/models.py` (Alembic's check). Fails if `models.py` changes a table or column without a migration. It does not compare CHECK constraints or server defaults, and the unit tests build their db from `models.py`, not from the migrations. |
| `test_a_table_change_keeps_the_edits_on_it_and_backs_the_db_up_first` | A later migration that rebuilds `fields` (how SQLite changes a column) keeps the reviewers' edits on it, and the db is copied to `<name>-backup-<revision>.db` before it runs. |
| `test_a_migration_that_breaks_a_link_is_undone` | A later migration that leaves rows pointing at nothing (deletes a bundle its pages belong to) stops with an error, and the db is left as it was before it. |
| `test_version_1_of_the_prompt_and_templates_is_the_files_byte_for_byte` | Migration 001 stores `prompt.txt` and each template as version 1 byte for byte, with the files' hashes, so transcripts already made from the files are reused, not read (and paid for) again. |

## `test_validate.py`

Survey consistency check (`validate_survey`) on the example main form and coded card, which agree: no model calls.

| Test | What it checks |
|---|---|
| `test_example_survey_has_no_flags` | The example main form and coded card give no flags, and the result carries the survey id. |
| `test_conflict_names_the_nested_field_and_changes_nothing` | A coded bedroom count of 4 against a main form saying 3 is flagged naming `Page 1: rooms.number_of_separate_bedrooms`, and the main form is left unchanged. |
| `test_native_age_derivation` | Residents aged 8 and 7 agree with the coded age counts; lowering the coded under-14 count to 1 is a page 1–3 conflict naming `Page 1: residents[2].age`. |
| `test_missing_native_location` | A coded bedroom count that isn't there is flagged as `Page 3: number_of_bedrooms`: `<missing>`. |
| `test_blank_upstream_template_is_not_zero_known_residents` | The blank main form template with the blank coded template gives no flags (its empty resident columns are unknown, not zero residents); with the example coded card it does. |
| `test_unrecognised_coded_card_is_not_silent_success` | A coded card reading without `number_of_dwelling` (empty, other fields only, wrapped in `fields`, or the old uppercase labels) raises a ValueError instead of passing. |
| `test_number_does_not_fallback_without_definition` | A main form without `number_of_dwelling` is flagged with it `<missing>`; the form's `number` field isn't used instead. |
| `test_unknown_fields_are_ignored` | An extra handwritten field on the main form raises no flags. |
| `test_other_children_list_not_guessed_count` | An entry in the main form's `other_children` list adds a warning and no flags: it isn't counted. |
| `test_missing_page_fails_before_output` | A survey without a coded card raises a ValueError. |
| `test_package_import` | `backend.pipeline.validate` exports `validate_survey`, which finds no flags on the example. |

## `test_validate_pipeline.py`

Survey consistency check run over a pipeline manifest (`validate_manifest`) with stored transcriptions, plus dwelling-number, margin-code and resident edge cases: no model calls.

| Test | What it checks |
|---|---|
| `test_group_manifest_uses_cached_json` | A grouped manifest is validated from the stored transcriptions as one survey with no flags, and the manifest's transcripts entry and the existing review file are left as they were. |
| `test_no_transcript_changes_and_idempotent_review` | A coded card with a different dwelling number adds a validate entry to the review file, running twice gives the same review file, and the transcript file is not changed. |
| `test_repeated_main_not_merged_silently` | A survey with two main forms is skipped rather than merged, giving a partial status, one skipped survey and none validated. |
| `test_missing_coded_reported_not_validated` | A survey with no coded card is counted as skipped. |
| `test_missing_transcript_reported` | A survey whose coded card transcript file is missing is counted as skipped. |
| `test_unassigned_page_reported` | A main page not assigned to any survey gives a partial status. |
| `test_letter_dwelling_numbers` | A main form dwelling number '024 a' matches a coded '24A', and a coded '24B' is flagged as a NUMBER OF DWELLING Page 1–3 conflict. |
| `test_actual_coded_all_null_schema` | The blank main form and coded card templates together give no flags. |
| `test_explicit_margin_codes_compare` | An industry-of-head code '0802' matches coded '802', and a coded '803' is flagged as an INDUSTRY OF HEAD CODE conflict. |
| `test_nonpersonal_metadata_not_resident` | A resident row holding only a stray annotation, with no relationship, age or earning status, is not counted as a resident and gives no flags. |
