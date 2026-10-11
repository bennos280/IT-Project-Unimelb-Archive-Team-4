# Integration tests

Multiple pieces of the pipeline wired together through their real entry points —
`run.main`, `step_split`, `process_image`, the shipped identification model, the
committed transcription results — instead of individual functions in isolation.
Fixture data (`identify/`, `preprocess/`, `transcribe/`) lives alongside the test files
in this folder, and `backend.pipeline.identify.identify` / `backend.pipeline.transcribe.score` read it
from here directly.

**69 test cases ~140s**

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

## `test_run.py` — 10 test functions / 21 cases

Resume and idempotency for `backend.pipeline.run`. The thread running through all of it: retry
unfinished work, never skip an unprocessed survey, never repeat a paid transcription
call that was already saved. The fixture stubs the two expensive boundaries —
`identify.identify_pages` and `transcribe.transcribe` — and **fails the test outright**
if a live transcription model is ever called; everything else runs for real.

| Test  | What it checks |
|---|---|
| `test_failed_identification_is_retried`  | After identification fails, the manifest records only `split` and the survey stays in `unprocessed()`; a later successful run completes it; a completed survey is then skipped even if identification would fail again. |
| `test_transcription_is_selected_only_when_requested`  | Transcription runs only under `--transcribe`, and a second `--transcribe` run makes no further calls. |
| `test_failed_explicit_rerun_clears_old_completion`  | An explicitly requested rerun that fails clears the previous completion rather than leaving a stale "done" marker. |
| `test_invalid_manifest_does_not_hide_input`  | Truncated, `null`, malformed and non-UTF-8 manifests all leave the survey visible to `unprocessed()` instead of silently hiding it. |
| `test_interrupted_transcription_reuses_saved_pages`  | A mid-transcription `SystemExit` keeps page 1's saved result; the retry re-calls only page 2, and page 1's file is byte-identical. No paid retry happens without the flag. |
| `test_transcription_reuse_requires_matching_inputs_and_result`  | Cache invalidation: a changed image, label, model, effort, prompt, template, deleted result or edited result each force the right number of re-calls. |
| `test_legacy_completed_manifest_still_skips_input`  | An older manifest format still counts as complete. |
| `test_failed_json_publication_keeps_previous_progress`  | A failed atomic write leaves the old manifest byte-identical and drops no temp files. |
| `test_pdfs_in_bundle_folders_are_found` | `uv run survey` with no PDF named finds the PDFs in DATA's bundle folders (`DATA/216412/a.pdf`), not only ones directly in DATA, and ignores PDFs inside the output folder. |
| `test_run_reports_each_step_and_transcription_progress`  | A run's `progress` callback hears each step start and every transcribed page (done / total), which the worker saves on the job. |

## `test_identify.py` — 2 tests

Page-kind classification over every labelled page in `identify/pages/`.
**zero wrong answers**, and at least `MIN_COVERAGE` of pages answered, plus

| Test | What it checks |
|---|---|
| `test_shipped_weights` | The committed model scored against pages it was trained on. Catches a corrupted or mismatched weights file. |
| `test_held_out` | 5-fold: trains on 4/5 and scores the 1/5 never seen, so every page is judged by a model trained without it. This is the honest accuracy number. |

## `test_transcribe.py` — 1 test

No test doubles — real committed model outputs, real scorer.

| Test | What it checks |
|---|---|
| `test_results_score` | Every committed model output under `results/transcribe/` is scored against its truth file in `transcribe/truth/`, asserting `0 <= hits <= total`. Also asserts truth files were found at all, so an empty glob fails loudly instead of vacuously passing. |

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
