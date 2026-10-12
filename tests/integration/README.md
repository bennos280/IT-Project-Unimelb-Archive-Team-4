# Integration tests

Multiple pieces of the pipeline wired together through their real entry points —
`run.main`, `step_split`, `process_image`, the shipped identification model, the
committed transcription results — instead of individual functions in isolation.
Fixture data (`identify/`, `preprocess/`, `group/`, `archive/`, `validate/`) lives alongside the test files
in this folder, and `backend.pipeline.identify.identify` reads its labelled pages
from here directly.

**96 test cases ~140s**

```bash
uv run pytest tests/integration
```

## `test_split.py` — 9 tests

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

## `test_preprocessing.py` — 28 tests

Preprocessing against the real fixture scans in `preprocess/`, plus its handoff into
`run.step_preprocess`.

| Test | What it checks |
|---|---|
| `test_output_modes_preserve_original`  | Output pixels match the requested mode (colour / greyscale / binary) and the source file is byte-identical afterwards. |
| `test_pipeline_failure_records_review_without_completion` | An unreadable page raises through `run.step_preprocess`, is logged to `review.json`, leaves the step incomplete, and keeps the original page path. |
| `test_skewed_image_detection` | The real `skewed_image_1.jpg` fixture is detected confidently at 1.57° ± 0.3°. |
| `test_crop`  | Page crop on the real `crop.png`: output matches the independently measured paper size, the returned corners enclose all handwritten content, and dark scanner border pixels at least halve. |

## `test_run.py` — 13 test functions / 24 cases

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

## `test_identify.py` — 2 tests

Page-kind classification over every labelled page in `identify/pages/`.
**zero wrong answers**, and at least `MIN_COVERAGE` of pages answered, plus

| Test | What it checks |
|---|---|
| `test_shipped_weights` | The committed model scored against pages it was trained on. Catches a corrupted or mismatched weights file. |
| `test_held_out` | 5-fold: trains on 4/5 and scores the 1/5 never seen, so every page is judged by a model trained without it. This is the honest accuracy number. |

## `test_group.py` — 2 tests

Pages → surveys (`step_group`), from stored transcriptions: no model calls.

| Test | What it checks |
|---|---|
| `test_cards_join_the_main_form_with_their_number` | On a made-up bundle, each coded card joins the main form with its dwelling number (before or after it, or misfiled far away), second main sheets and flats (24A, 24B) stay separate surveys, and unreadable or reused numbers are flagged. |
| `test_real_bundles_group_like_ash` | 19 real bundles (`group/`, Opus 5.5 transcriptions + Ash's hand grouping of 589 surveys): at least `BASELINE` surveys match Ash exactly, and every one that does not is flagged for a human. |

## `test_scans.py` — 2 tests

The archive's real download page for Box Hill 00 (bundle 216412), saved as `archive/download_216412.html`, so the
code that reads it is checked against the archive's own markup, not only the tests' stand-in.

| Test | What it checks |
|---|---|
| `test_the_archives_real_download_page_gives_every_page_its_file` | Reading the real page finds all 227 pages in order, each with its file id (page 1 → 423448, page 227 → 425881). |
| `test_no_test_reaches_the_internet` | A plain `urllib` request to the archive fails during tests: `tests/conftest.py` blocks every internet lookup but this computer's own. |

## `test_migrations.py` — 4 tests

| Test | What it checks |
|---|---|
| `test_migrations_match_the_models` | The migrations in `backend/db/migrations/` build the same tables and columns as `backend/db/models.py` (Alembic's check). Fails if `models.py` changes a table or column without a migration. It does not compare CHECK constraints or server defaults, and the unit tests build their db from `models.py`, not from the migrations. |
| `test_a_table_change_keeps_the_edits_on_it_and_backs_the_db_up_first` | A later migration that rebuilds `fields` (how SQLite changes a column) keeps the reviewers' edits on it, and the db is copied to `<name>-backup-<revision>.db` before it runs. |
| `test_a_migration_that_breaks_a_link_is_undone` | A later migration that leaves rows pointing at nothing (deletes a bundle its pages belong to) stops with an error, and the db is left as it was before it. |
| `test_version_1_of_the_prompt_and_templates_is_the_files_byte_for_byte` | Migration 001 stores `prompt.txt` and each template as version 1 byte for byte, with the files' hashes, so transcripts already made from the files are reused, not read (and paid for) again. |

## `test_validate.py` — 15 tests

Survey consistency check (`validate_survey`, `validate_document`, the CLI) on the example main form and coded card: no model calls.

| Test | What it checks |
|---|---|
| `test_real_main_schema_adapter` | The example main form and coded card, which agree, give no flags, and the dwelling number reads as '99'. |
| `test_native_nested_statuses_and_preserved_values` | A coded bedroom count of 4 against a main form saying 3 flags the field and marks it ToBeReviewed, keeps the main form's value of '3', and leaves the input unchanged. |
| `test_native_age_derivation` | Two children aged 8 and 7 agree with the coded age counts, and lowering the coded under-14 count to 1 raises a Page 1–3 conflict and marks the age ToBeReviewed. |
| `test_missing_native_location` | A coded card with no bedrooms field is flagged, with the Page 3 value shown as '<missing>'. |
| `test_blank_upstream_template_is_not_zero_known_residents` | A blank main form compared with an all-null coded card gives no flags, but the same blank form against the filled example card does. |
| `test_unrecognised_coded_schema_is_not_silent_success` | A coded card with no recognised fields raises a ValueError instead of passing. |
| `test_conflicting_coded_aliases_are_rejected` | A coded card giving the bedroom count under two names with different values raises a ValueError. |
| `test_number_does_not_fallback_without_definition` | A main form with no dwelling number is flagged with the Page 1 value shown as '<missing>'. |
| `test_notes_and_unknown_fields_preserved` | Notes and an extra handwritten field on the main form come through to the result unchanged and raise no flags. |
| `test_other_children_list_not_guessed_count` | Children who died written as free text ('two children') give a warning and no flag, because no count is guessed from the text. |
| `test_cli_two_page_files` | Running the command line with separate main and coded files exits cleanly and writes a flags-only file with the survey id and no flags. |
| `test_cli_grouped_file` | Running the command line on one grouped survey file exits cleanly, writes a full output with no flags, and keeps the notes text. |
| `test_batch_separates_surveys` | In a two-survey batch, the survey whose card has a different dwelling number is flagged and the other is not, and the flags-only output lists both. |
| `test_missing_page_fails_before_output` | A document with a main form but no coded card raises a ValueError. |
| `test_package_import` | The `backend.pipeline.validate` package exposes `validate_survey`, which gives no flags on the example pair. |

## `test_validate_pipeline.py` — 10 tests

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
| `test_actual_coded_all_null_schema` | The blank main form and the all-null coded schema together give no flags. |
| `test_explicit_margin_codes_compare` | An industry-of-head code '0802' matches coded '802', and a coded '803' is flagged as an INDUSTRY OF HEAD CODE conflict. |
| `test_nonpersonal_metadata_not_resident` | A resident row holding only a stray annotation, with no relationship, age or earning status, is not counted as a resident and gives no flags. |
