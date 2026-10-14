# Integration tests

Multiple pieces of the pipeline wired together through their real entry points —
`run.main`, `step_split`, `process_image`, the shipped identification model, the
committed transcription results — instead of individual functions in isolation.
Fixture data (`identify/`, `preprocess/`, `group/`, `archive/`) lives alongside the test files
in this folder, and `backend.pipeline.identify.identify` reads its labelled pages
from here directly.

```bash
uv run pytest tests/integration
```

## `test_split.py` — 10 tests

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

## `test_preprocessing.py` — 17 tests

Preprocessing (the review screen's cleaned-up view) against the real fixture scans in `preprocess/`.

| Test | What it checks |
|---|---|
| `test_output_modes_preserve_original`  | Output pixels match the mode (colour, greyscale, or the app's black and white) and the source file is byte-identical afterwards. |
| `test_skewed_image_detection` | The real `skewed_image_1.jpg` fixture is detected confidently at 1.57° ± 0.3°. |
| `test_crop`  | Page crop on the real `crop.png`: output matches the independently measured paper size, the returned corners enclose all handwritten content, and dark scanner border pixels at least halve. |

## `test_run.py` — 14 test functions / 26 cases

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

## `test_identify.py` — 2 tests

Page-kind classification over every labelled page in `identify/pages/`.
**zero wrong answers**, and at least `MIN_COVERAGE` of pages answered, plus

| Test                   | What it checks                                                                                                                                  |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_shipped_weights` | The committed model scored against pages it was trained on. Catches a corrupted or mismatched weights file.                                     |
| `test_held_out`        | 5-fold: trains on 4/5 and scores the 1/5 never seen, so every page is judged by a model trained without it. This is the honest accuracy number. |

## `test_group.py` — 2 tests

Pages → surveys (`step_group`), from stored transcriptions: no model calls.

| Test                                              | What it checks                                                                                                                                                                                                                             |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `test_cards_join_the_main_form_with_their_number` | On a made-up bundle, each coded card joins the main form with its dwelling number (before or after it, or misfiled far away), second main sheets and flats (24A, 24B) stay separate surveys, and unreadable or reused numbers are flagged. |
| `test_real_bundles_group_like_ash`                | 19 real bundles (`group/`, Opus 5.5 transcriptions + Ash's hand grouping of 589 surveys): at least `BASELINE` surveys match Ash exactly, and every one that does not is flagged for a human.                                               |

## `test_scans.py` — 3 tests

The archive's real download page for Box Hill 00 (bundle 216412), saved as `archive/download_216412.html`, so the
code that reads it is checked against the archive's own markup, not only the tests' stand-in.

| Test | What it checks |
|---|---|
| `test_the_archives_real_download_page_gives_every_page_its_file` | Reading the real page finds all 227 pages in order, each with its file id (page 1 → 423448, page 227 → 425881). |
| `test_no_test_reaches_the_internet` | A plain `urllib` request to the archive fails during tests: `tests/conftest.py` blocks every internet lookup but this computer's own. |
| `test_a_scan_the_archive_cant_send_is_logged_with_the_reason` | A page scan the archive can't send comes back as none and logs one warning naming the bundle, the page and the error, and when the archive is asked again. |

## `test_migrations.py` — 4 tests

| Test                                                                    | What it checks                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `test_migrations_match_the_models`                                      | The migrations in `backend/db/migrations/` build the same tables and columns as `backend/db/models.py` (Alembic's check). Fails if `models.py` changes a table or column without a migration. It does not compare CHECK constraints or server defaults, and the unit tests build their db from `models.py`, not from the migrations. |
| `test_a_table_change_keeps_the_edits_on_it_and_backs_the_db_up_first`   | A later migration that rebuilds `fields` (how SQLite changes a column) keeps the reviewers' edits on it, and the db is copied to `<name>-backup-<revision>.db` before it runs.                                                                                                                                                       |
| `test_a_migration_that_breaks_a_link_is_undone`                         | A later migration that leaves rows pointing at nothing (deletes a bundle its pages belong to) stops with an error, and the db is left as it was before it.                                                                                                                                                                           |
| `test_version_1_of_the_prompt_and_templates_is_the_files_byte_for_byte` | Migration 001 stores `prompt.txt` and each template as version 1 byte for byte, with the files' hashes, so transcripts already made from the files are reused, not read (and paid for) again.                                                                                                                                        |

## Review UI/API integration — 15 checks

Tests the real frontend review adapter against the FastAPI backend using a
temporary copy of `backend/db/wilfprestsurvey.db`. The source database stays
unchanged. Results appear in the terminal, and the temporary copy is deleted
afterwards.V

Run from the project folder:

```bash
npm --prefix tests run test:integration
```

| Test                                                                                       | What it checks                                                                                |
| ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| `test("Load database survey through frontend getSurvey and parseSurvey", async () => ...)` | Page types, image URLs, field counts and non-child field values match the database.           |
| `test("Child field IDs returned by backend match database copy", async () => ...)`         | Child field IDs match the database, including residence groups and child numbers.             |
| `test("Reviewer list uses backend id", async () => ...)`                                   | The reviewer list contains the expected backend ID and name.                                  |
| `test("Create a reviewer through current frontend request", async () => ...)`              | Creating a reviewer returns an integer ID and the reviewer appears in a subsequent request.   |
| `test("Save and reload ordinary field", () => ...)`                                        | A correction survives reloading with its original value, reviewer ID, timestamp and revision. |
| `test("Second correction returns latest value", () => ...)`                                | A second correction becomes the latest saved value.                                           |
| `test("Reject outdated save and retain latest correction", async () => ...)`               | An outdated save is rejected and the latest correction remains unchanged.                     |
| ``test(`Preserve marker ${JSON.stringify(value)}`, () => ...)`` — 3 checks                 | `/`, `[?]` and `null` survive saving and reloading.                                           |
| `test("Correct a field whose original value is null", () => ...)`                          | A field with an original blank value accepts a correction.                                    |
| `test("Save and reload notes", () => ...)`                                                 | A notes field correction survives reloading.                                                  |
| `test("Save and reload child field including index zero", () => ...)`                      | A child field with index zero can be corrected and reloaded.                                  |
| ``test(`Save and reload resident ${index}`, () => ...)`` — 2 checks                        | Fields for residents zero and one can be corrected and reloaded.                              |

These checks run separately from pytest. They test adapter/API/database
integration; browser behaviour and image loading are covered separately.

## Review UI browser tests — 17 tests

`review.spec.ts` test the review screen in a real browser using Playwright.
Each test uses a sample survey, mock images and an isolated mock API.
No running backend or database is needed.

Run from the project folder:

```bash
npm --prefix tests run test:e2e
```

| Test                                                                                                 | What it checks                                                                                  |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `test("Next/Previous show matching page data and image", async ({ page }) => ...)`                   | Navigation shows matching fields and images, with buttons disabled at the first and last pages. |
| `test("Search and Clear filters return expected rows", async ({ page }) => ...)`                     | Search finds fields, shows an empty state and clears correctly.                                 |
| `test("Flag filter and disclosure show the reason", async ({ page }) => ...)`                        | Flagged fields can be filtered and their explanations expanded.                                 |
| `test("Zoom and Fit to Page change the image scale", async ({ page }) => ...)`                       | Zoom changes the scale and Fit to Page fits the image inside the viewer.                        |
| `test("Clicking Address highlights its scan area", async ({ page }) => ...)`                         | Selecting Address displays its named highlight and zooms in.                                    |
| `test("Cancel discards draft text and reviewer is required", async ({ page, api }) => ...)`          | A reviewer is required, and cancelling leaves the original value unchanged.                     |
| `test("Apply creates draft; Save persists and reload restores it", async ({ page, api }) => ...)`    | Applying creates a draft; saving stores it in the mock API and refreshing restores it.          |
| `test("Rejected save displays reason and retains unsaved correction", async ({ page, api }) => ...)` | A rejected save displays the error and preserves the draft.                                     |
| `test("Review all preserves correction and saves all fields", async ({ page, api }) => ...)`         | Reviewing all fields preserves existing corrections and saves every field.                      |
| `test("Try again recovers from a failed survey request", async ({ page, api }) => ...)`              | Retrying restores the screen after a failed request.                                            |
| `test("Add reviewer makes the new reviewer selectable", async ({ page }) => ...)`                    | A newly added reviewer becomes selected.                                                        |
| `test("Stay here and Escape retain the unsaved review", async ({ page, api }) => ...)`               | Dismissing the navigation warning retains the draft without saving.                             |
| `test("Save and continue saves before switching pages", async ({ page, api }) => ...)`               | Changes are saved before navigation and remain visible when returning.                          |
| `test("Discard restores the previous saved correction", async ({ page, api }) => ...)`               | Discarding a draft restores the earlier saved correction without another save.                  |
| `test("Failed save keeps the current page and unsaved review", async ({ page, api }) => ...)`        | A failed save keeps the warning open, displays the error and preserves the draft.               |
| `test("Leaving the website warns about unsaved reviews", async ({ page }) => ...)`                   | Leaving with unsaved changes triggers the browser warning.                                      |
| `test("adds a reviewer inside the field editor without losing the draft", async ({ page }) => ...)`  | Adding a reviewer inside the editor preserves the draft value.                                  |

These tests use mocked API responses. The integration runner separately
checks the real frontend adapter, backend and database.
The highlight test checks visibility and zoom, not coordinate accuracy.

## `progress.spec.ts` — 21 tests (US9: track progress)

Located in `tests/integration/ui-reviewscreen/progress.spec.ts`. Run only these tests from the project folder:

```bash
npm --prefix tests run test:e2e -- progress.spec.ts
```

| Test                                                                     | What it checks                                                                                                                                                                    |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `searches bundles and clears an empty result`                            | Bundle search finds a match; an unmatched search shows an empty state; Clear filters restores the list.                                                                           |
| `disables pagination for one bundle and filters by status`               | Next is disabled for a single bundle, and Reviewed/Ready to review filters return the expected results.                                                                           |
| `opens bundle pages with matching review targets`                        | Opening a bundle shows its pages and the correct survey/page review link; Back returns to all bundles.                                                                            |
| `Import and Export remain disabled placeholders`                    | Import and Export buttons remain visible and disabled pending implementation.                                                                                              |
| `Pg 1/2/3 opens its matching US7 page` — 3 tests                         | Each page's Review link opens the matching page in the review screen.                                                                                                             |
| `page table keeps actions visible at 936/640/375px` — 3 tests            | Flags and review actions remain visible without horizontal table overflow at desktop, tablet and phone widths.                                                                    |
| `untouched bundle prompts Transcribe and shows zero progress`            | A bundle without pages or a job shows 0% progress, the not-started message and an enabled Transcribe button beside the filters.                                                   |
| `partial bundle shows model and completion action without review access` | A failed partial bundle offers Retry transcription and error details; its page list shows the incomplete notice, Complete transcription and the saved model, with no Review link. |
| `waiting job disables duplicate transcription`                           | A queued job disables the transcription button and keeps the incomplete notice visible.                                                                                           |
| `running job disables duplicate transcription`                           | A running job disables the transcription button and keeps the incomplete notice visible.                                                                                          |
| `loaded bundle shows model or dash and hides incomplete notice`          | The Model column shows saved model information or a dash; completed bundles hide the incomplete notice and transcription action.                                                  |
| `pagination changes rows and searching resets to first page`             | Eleven pages span two table pages; searching from the second page resets pagination and shows matching rows.                                                                      |
| `failed progress request can be retried`                                 | A failed request displays its error; Try again restores the dashboard after the API recovers.                                                                                     |
| `polling updates review counts without a reload`                         | Updated API data changes the displayed reviewed count and percentage automatically.                                                                                               |

Related backend coverage lives in `tests/unit/test_progress.py` (3 tests): model/status/flag response data and review targets, saved versus unsaved reviews, and reviews of resident, child and annotation fields. Run it with `uv run pytest tests/unit/test_progress.py`.

### US7 → US9 review round trip — 3 browser tests

`review round trip: saved/unsaved/failed save updates progress only after persistence` opens a page from US9, reviews each flagged field individually in US7, and returns through Back to all bundles. An accepted save updates the reviewed count, ready count, percentage, page status, flags and View action, including after refresh. Unsaved drafts and rejected saves leave progress unchanged. These tests use a stateful mock API; they verify the screen-to-screen flow, not real database persistence.
