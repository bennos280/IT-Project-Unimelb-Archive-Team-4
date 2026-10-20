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

| Test                                                                                 | What it checks                                                                                                                                                                                                                               |
| ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_shorter_pdf_replaces_old_page_images`                                          | Re-splitting a now-shorter PDF removes stale page images instead of leaving them behind.                                                                                                                                                     |
| `test_failed_first_render_publishes_no_partial_images`                               | A render failure on a first run publishes no `pages/` folder at all.                                                                                                                                                                         |
| `test_failed_rerender_preserves_all_previous_images`                                 | A render failure on a re-run leaves the previous images byte-identical.                                                                                                                                                                      |
| `test_failed_publication_restores_previous_images`                                   | If the final rename fails, the previous images are restored.                                                                                                                                                                                 |
| `test_failed_publication_and_restore_retains_previous_images`                        | If the restore _also_ fails, the old images are retained in a `.split-*/previous` staging dir and its path is attached to the raised error.                                                                                                  |
| `test_image_folder_is_used_without_changes`                                          | A folder of images as input is read in place: no output written, source untouched.                                                                                                                                                           |
| `test_pdf_not_on_this_computer_is_downloaded_from_the_archive_and_kept`              | A PDF not on this computer is downloaded from the archive (faked here) after opening its bundle's download page, saved in `DATA` under the archive's name, then split as usual; no part-downloads are left behind.                           |
| `test_pdf_the_archive_cannot_send_stops_the_run_and_keeps_nothing`                   | A PDF the archive breaks off halfway (fewer bytes than it announced), or doesn't have, stops the run saying why; nothing is left in `DATA` and no `pages/` folder is published.                                                              |
| `test_a_long_pdf_is_split_on_every_core_in_page_order`                               | A 40-page PDF, more than one 16-page chunk so several processes draw it, gives all 40 pages named in page order, each the same image as drawing that page alone.                                                                             |
| `test_a_page_that_fails_to_draw_is_named_in_an_error_a_worker_process_can_send_back` | A page that fails to draw gives a RuntimeError naming the PDF and page ("survey.pdf, page 1: ...") that survives pickling, the way a worker process sends its error back, even when the original error can't be pickled, as PyMuPDF's can't. |

## `test_preprocessing.py`

Preprocessing (the review screen's cleaned-up view) against the real fixture scans in `preprocess/`.

| Test                                  | What it checks                                                                                                                                                                               |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_output_modes_preserve_original` | Output pixels match the mode (colour, greyscale, or the app's black and white) and the source file is byte-identical afterwards.                                                             |
| `test_skewed_image_detection`         | The real `skewed_image_1.jpg` fixture is detected confidently at 1.57° ± 0.3°.                                                                                                               |
| `test_crop`                           | Page crop on the real `crop.png`: output matches the independently measured paper size, the returned corners enclose all handwritten content, and dark scanner border pixels at least halve. |

## `test_run.py`

Resume and idempotency for `backend.pipeline.run`. The thread running through all of it: retry
unfinished work, never skip an unprocessed survey, never repeat a paid transcription
call that was already saved. The fixture stubs the two expensive boundaries —
`identify.identify_pages` and `transcribe.transcribe` — and **fails the test outright**
if a live transcription model is ever called; everything else runs for real.

| Test                                                                               | What it checks                                                                                                                                                                                                          |
| ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_failed_identification_is_retried`                                            | After identification fails, the manifest records only `split` and the survey stays in `unprocessed()`; a later successful run completes it; a completed survey is then skipped even if identification would fail again. |
| `test_pdfs_in_bundle_folders_are_found`                                            | `uv run survey` with no PDF named finds the PDFs in DATA's bundle folders (`DATA/216412/a.pdf`), not only ones directly in DATA, and ignores PDFs inside the output folder.                                             |
| `test_transcription_is_selected_only_when_requested`                               | Transcription runs only under `--transcribe`, and a second `--transcribe` run makes no further calls.                                                                                                                   |
| `test_failed_explicit_rerun_clears_old_completion`                                 | An explicitly requested rerun that fails clears the previous completion rather than leaving a stale "done" marker.                                                                                                      |
| `test_invalid_manifest_does_not_hide_input`                                        | Truncated, `null`, malformed and non-UTF-8 manifests all leave the survey visible to `unprocessed()` instead of silently hiding it.                                                                                     |
| `test_interrupted_transcription_reuses_saved_pages`                                | Pages are read in parallel: a `SystemExit` on page 2 keeps page 1's saved result; the retry re-calls only page 2, and page 1's file is byte-identical. No paid retry happens without the flag.                          |
| `test_failed_transcription_stops_without_reading_the_queued_pages`                 | With one reader, a `SystemExit` on page 1 stops the run with that error and the page still waiting is never read (paid).                                                                                                |
| `test_run_reports_each_step_and_transcription_progress`                            | A run's `progress` callback hears each step start and every transcribed page (done / total), which the worker saves on the job.                                                                                         |
| `test_transcription_reuse_requires_matching_inputs_and_result`                     | Cache invalidation: a changed image, label, model, effort, prompt, template, deleted result or edited result each force the right number of re-calls.                                                                   |
| `test_the_command_line_transcribes_with_the_saved_choice_and_exits_without_one` | `--transcribe` reads the provider, model and effort saved on the Settings page; with none saved it exits with "Choose a transcription model on the Settings page first.", and without `--transcribe` no model is needed. |
| `test_a_choice_with_a_blank_part_takes_that_part_from_the_saved_one` | A blank part of a given choice is filled from the saved choice, never overwritten by the blank. |
| `test_the_command_line_skips_an_input_no_series_lists` | With no series listing a PDF, `run.main([])` returns 0, prints "skipped <name>: no series lists it; add it to one from the app first" and writes no output folder for it. |
| `test_legacy_completed_manifest_still_skips_input`                                 | An older manifest format still counts as complete.                                                                                                                                                                      |
| `test_failed_json_publication_keeps_previous_progress`                             | A failed atomic write leaves the old manifest byte-identical and drops no temp files.                                                                                                                                   |
| `test_a_job_reads_each_page_with_its_texts_and_skips_a_page_type_with_no_template` | Given a job's texts (the db's newest prompt and templates), `step_transcribe` reads each page with them, skips a page type they have no template for, and records the prompt's hash for reuse.                          |
| `test_a_run_sorts_its_pages_with_its_sorting_model`                                | A run given a retrained model's weights sorts its pages with them.                                                                                                                                                      |
| `test_a_damaged_manifest_is_logged_before_the_run_starts_again`                    | A run's manifest.json that isn't JSON, or isn't a JSON object, reads as empty (the run starts again from the beginning) and logs one warning saying why; a run with no manifest yet logs nothing.                       |

## `test_identify.py`

Page-kind classification over every labelled page in `identify/pages/`.
**zero wrong answers**, and at least `MIN_COVERAGE` of pages answered, plus

| Test                   | What it checks                                                                                                                                  |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_shipped_weights` | The committed model scored against pages it was trained on. Catches a corrupted or mismatched weights file.                                     |
| `test_held_out`        | 5-fold: trains on 4/5 and scores the 1/5 never seen, so every page is judged by a model trained without it. This is the honest accuracy number. |

## `test_group.py`

Pages → surveys (`step_group`), from stored transcriptions: no model calls.

| Test                                              | What it checks                                                                                                                                                                                                                             |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `test_cards_join_the_main_form_with_their_number` | On a made-up bundle, each coded card joins the main form with its dwelling number (before or after it, or misfiled far away), second main sheets and flats (24A, 24B) stay separate surveys, and unreadable or reused numbers are flagged. |
| `test_the_rule_not_the_page_type_names_decides` | Prest's pages with every page type renamed and the number in another field group into the same surveys, with the same problems, as Prest's own; the pages before the first starting page are flagged as belonging to no `return`. |
| `test_without_a_number_field_pages_follow_the_page_that_starts_their_survey` | With no number field, every page (blank ones too) follows the page that starts its survey, and nothing is flagged. |
| `test_with_no_page_type_that_starts_a_survey_each_page_is_one` | With a level no page type starts, each page is its own survey and a blank page is in none. |
| `test_where_each_item_is_one_record_its_pages_are_one_whatever_their_types` | In a series whose items are each one record, every page but a blank one is in the item's record, named after the item, whatever its type and number, with nothing flagged. |
| `test_a_level_groups_the_pages_of_each_record_of_the_level_above` | With two levels (folders of letters) each folder's letters are made from its own pages, named `<folder>-n<place>` (or `<folder>-<number>` with a number field), a folder's pages before its first letter stay in it unflagged, a letter's problem is flagged on its own number field, and the records are listed parents first. |
| `test_a_level_below_sees_its_records_pages_in_scan_order_with_cards_matched_by_number_in_place` | A survey's coded card, matched to it by number, stays where it was scanned for the level below, so it stays in the survey rather than joining a section after it. |
| `test_real_bundles_group_like_ash`                | 19 real bundles (`group/`, Opus 5.5 transcriptions + Ash's hand grouping of 589 surveys): at least `BASELINE` surveys match Ash exactly, and every one that does not is flagged for a human.                                               |

## `test_scans.py`

Real archive pages saved in `archive/` (Box Hill 00's download page; the Strathfieldsaye Estate Diaries' series page, list of
items and a search of it; a search of the Red Cross cards; a card's page; a diary's download page), so the code that reads
them is checked against the archive's own markup, not only the tests' stand-in.

| Test                                                             | What it checks                                                                                                                                             |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_the_archives_real_download_page_gives_every_page_its_file` | Reading the real page finds all 227 pages in order, each with its file id (page 1 → 423448, page 227 → 425881).                                            |
| `test_a_series_real_list_of_items_is_read_with_which_can_be_downloaded` | The diaries' page links to their list; reading it gives all 18 items with title, identifier and number, and the one with no scans can't be downloaded. |
| `test_a_real_search_result_keeps_the_fields_its_matches_are_highlighted_in` | In a search's results, an identifier the archive highlighted part of is read whole. |
| `test_a_real_reading_room_card_is_listed_as_not_downloadable` | A card for the Reading Room only ("Access restrictions apply") is listed as not downloadable. |
| `test_a_real_items_page_names_its_series_and_its_download_page_its_original_pdf` | A card's page gives its title, identifier and series; a diary's download page gives its original PDF's file id. |
| `test_no_test_reaches_the_internet`                              | A plain `urllib` request to the archive fails during tests: `tests/conftest.py` blocks every internet lookup but this computer's own.                      |
| `test_a_scan_the_archive_cant_send_is_logged_with_the_reason`    | A page scan the archive can't send comes back as none and logs one warning naming the bundle, the page and the error, and when the archive is asked again. |

## `test_migrations.py`

The database is `backend/db/prestcribe.db`, made by one migration, `backend/db/migrations/versions/001_prestcribe.py`: the tables in `backend/db/models.py` and nothing in them. A series is added in the app or opened from a PrestCribe file.

| Test | What it checks |
| ---- | -------------- |
| `test_migrations_match_the_models` | The migration in `backend/db/migrations/` builds the same tables and columns as `backend/db/models.py` (Alembic's check). Fails if `models.py` changes a table or column without a migration. It does not compare CHECK constraints or server defaults, and the unit tests build their db from `models.py`, not from the migrations. |
| `test_a_fresh_db_is_at_revision_001_with_every_table_of_the_models_and_no_rows` | A db made by the migration is at revision `001`, has every table of the models and no rows in any of them. |
| `test_a_table_change_keeps_the_edits_on_it_and_backs_the_db_up_first` | A later migration that rebuilds `fields` (how SQLite changes a column) keeps the reviewers' edits on it, and the db is copied to `<name>-backup-<revision>.db` before it runs. |
| `test_a_migration_that_breaks_a_link_is_undone` | A later migration that leaves rows pointing at nothing (deletes a bundle its pages belong to) stops with an error, and the db is left as it was before it. |

## `check_review_integration.mjs` / `check_review_integration.py` — 15 test

Tests the real frontend review adapter against the FastAPI backend using a
temporary copy of `backend/db/prestcribe.db`. The source database stays
unchanged. Results appear in the terminal, and the temporary copy is deleted
afterwards.V

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

## `review.spec.ts` — 22 tests

Tests the review screen in a real browser using Playwright.
Each test uses a sample survey, mock images and an isolated mock API.
No running backend or database is needed.

| Test                                                                                                 | What it checks                                                                                  |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `test("Next/Previous show matching page data and image", async ({ page }) => ...)`                   | Navigation shows matching fields and images, with buttons disabled at the first and last pages. |
| `test("Search and Clear filters return expected rows", async ({ page }) => ...)`                     | Search finds fields, shows an empty state and clears correctly.                                 |
| `test("Flag filter and disclosure show the reason", async ({ page }) => ...)`                        | Flagged fields can be filtered and their explanations expanded.                                 |
| `test("A field breaking its rule is flagged with why, and filtered to", async ({ page }) => ...)` | A value breaking its field's rule shows as that kind of flag with its reason, and the filter can show only those. |
| `test("Zoom and Fit to Page change the image scale", async ({ page }) => ...)`                       | Zoom changes the scale and Fit to Page fits the image inside the viewer.                        |
| `test("Clicking Address highlights its scan area", async ({ page }) => ...)`                         | Selecting Address displays its named highlight and zooms in.                                    |
| `test("Clicking an annotation shows the whole card and a note", async ({ page }) => ...)` | An annotation with no mapped scan area shows the whole card with a note saying where it is; zooming by hand hides the note and a mapped field still highlights and zooms. |
| `test("Clicking an annotation with an area highlights the area and shows the note", async ({ page }) => ...)` | An annotation with an area highlights it, zooms to fit it (between 100% and 200%) and still shows the note; zooming by hand keeps the new zoom and the highlight. |
| `test("Clicking an annotation with a region highlights the region", async ({ page }) => ...)` | An annotation with its own region (a row of the residents table) highlights that region, not its whole area. |
| `test("A field's own wide region is highlighted at a lower zoom", async ({ page }) => ...)` | A field's own region is used instead of the shared one, and a wide one zooms less than 200%. |
| `test("The status line names the person working", async ({ page }) => ...)`                          | The status line says the page is saved as the person chosen on the home page.                   |
| `test("Cancel discards draft text", async ({ page, api }) => ...)`                                   | Cancelling the editor leaves the original value unchanged.                                      |
| `test("Apply creates draft; Save persists and reload restores it", async ({ page, api }) => ...)`    | Applying creates a draft; saving stores it in the mock API and refreshing restores it.          |
| `test("Rejected save displays reason and retains unsaved correction", async ({ page, api }) => ...)` | A rejected save displays the error and preserves the draft.                                     |
| `test("Review all preserves correction and saves all fields", async ({ page, api }) => ...)`         | Reviewing all fields preserves existing corrections and saves every field.                      |
| `test("Review all keeps another reviewer's saved review", async ({ page, api }) => ...)`             | A field another reviewer already saved keeps their value and name after reviewing all fields.   |
| `test("Try again recovers from a failed survey request", async ({ page, api }) => ...)`              | Retrying restores the screen after a failed request.                                            |
| `test("Stay here and Escape retain the unsaved review", async ({ page, api }) => ...)`               | Dismissing the navigation warning retains the draft without saving.                             |
| `test("Save and continue saves before switching pages", async ({ page, api }) => ...)`               | Changes are saved before navigation and remain visible when returning.                          |
| `test("Discard restores the previous saved correction", async ({ page, api }) => ...)`               | Discarding a draft restores the earlier saved correction without another save.                  |
| `test("Failed save keeps the current page and unsaved review", async ({ page, api }) => ...)`        | A failed save keeps the warning open, displays the error and preserves the draft.               |
| `test("Leaving the website warns about unsaved reviews", async ({ page }) => ...)`                   | Leaving with unsaved changes triggers the browser warning.                                      |

## `export.spec.ts` — 8 tests

It tests the export interface in a real browser using Playwright.
API responses are mocked, so no running backend or database is needed.

Run from the project folder:

| Test                                                                      | What it checks                                                                        |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Downloads backend correction instead of an unsaved on-screen edit         | The downloaded export uses the backend response rather than an unsaved browser draft. |
| Shows backend export failure and permits retry                            | A failed export displays an error and allows another attempt.                         |
| Downloads a selected item as JSON                                         | Selecting an item produces a JSON download.                                           |
| Dashboard exports the selected item's ID rather than its display number   | Dashboard export requests use the database item ID.                                   |
| Review screen exports its current item using the backend item ID          | The Current item option uses the item ID supplied by the survey response.             |
| Warns for unreviewed data and clears the warning for a reviewed selection | The export warning reflects whether the selected data has been reviewed.              |
| Conditional export warning on dashboard — 2 cases                         | Checks the warning on both the all-items and selected-item dashboard views.           |

These tests cover browser interactions with mocked API responses.
The backend export tests separately check database selection and saved values.

These tests use mocked API responses. The integration runner separately
checks the real frontend adapter, backend and database.
The highlight test checks visibility and zoom, not coordinate accuracy.

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

## `progress.spec.ts` — 43 tests (US9: track progress)

Located in `tests/integration/frontend/progress.spec.ts`. Run only these tests from the project folder:

```bash
npm --prefix tests run test:e2e -- progress.spec.ts
```

| Test                                                                     | What it checks                                                                                                                                                                    |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `searches items and clears an empty result`                              | Item search finds a match; an unmatched search shows an empty state; Clear filters restores the list.                                                                             |
| `disables pagination for one item and filters by status`                 | Next is disabled for a single item, and Reviewed/Ready to review filters return the expected results.                                                                             |
| `opens item pages with matching review targets`                          | Opening an item shows its pages and the correct survey/page review link.                                                                                                          |
| `an item that is one record opens it from the items list, which has no Total pages column when no item has more than one page` | A loaded item whose pages are all one record links straight to it, and with no item of more than one page or record the list has neither column. |
| `an item of several records lists them, with their pages a switch away` | With an item of several records the list has a Records column; the item lists its records (each named by its number, with its pages, flags and status, linking to its first page), searched and filtered as records, with a Records / Pages switch to its pages that stays in the URL across reload and Back. |
| `an item lists its top level, each record opening the level below, past a level with only one thing in it` | In a series of folders of letters, an item lists its folders (pages, flags and status counted over everything in each; one a move emptied left out), a folder opens its letters in-app (named by place when they have no numbers) with its own pages a click away, crumbs and heading naming it, its Pages switch listing only its pages; a folder holding one letter and nothing of its own opens that letter; the item's crumb comes back with Back intact. |
| `an item's pages in no record are a click away from its records, as with a status only pages have` | A record is as far along as its least far page and opens at it (Transcribe, for a page awaiting transcription); an item's records list says how many of its pages are in no record, and Show pages lists them all; a status only pages have (as an older link may ask) lists the pages. |
| `an archive item is listed by its title over its identifier and number, found by any of them, and its page links to the archive` | An item on the archive is listed by its title, with its identifier and number under it and one link per row; search finds it by title (any case), identifier or number; its page is headed and crumbed by the title and links the identifier to its archive page. |
| `the Transcribe and error dialogs and the progress bar name an archive item by its title` | The Transcribe and Transcription error dialogs, and the row's progress bar label, use the item's title instead of its number. |
| `with no transcription model saved, the dialog prefills nothing, links to Settings and still starts a run with the model picked there` | With no model saved the Transcribe dialog says so and links to Settings, starts with provider, model and effort empty and Start disabled, and starts the run with the choice made there. |
| `with a transcription model saved, the dialog prefills it and shows no notice` | With a model saved the dialog starts on its provider, model and effort and shows no notice. |
| `unassigned pages do not prevent 100% review progress` | Pages in no survey are left out of an item's review progress, which can reach 100% and says how many pages are not in a survey. |
| `a page without a survey is not clickable but explains itself` | A page in no survey has no link, a dash with a tooltip saying why, and a plain cursor; a page in a survey keeps its View link. |
| `an item with only unassigned pages has no review percentage` | An item whose pages are all in no survey shows "No reviewable pages" and how many are not in a survey, with no percentage or progress bar. |
| `the overview asks for the URL's page, search and status, and shows the server's counts and totals` | The list is a page of items the server searched, filtered and counted: the dashboard asks for the URL's page, search and status and shows the server's counts and totals. |
| `paging, searching and filtering each ask the server, which answers one page at a time` | Next, a search, a status and Clear filters each ask the server again, which answers nine items at a time. |
| `an item's page asks only for that item, and for its partial results when it has a job and isn't loaded` | An item's page asks for that item only, and for its partial results when it has a job but isn't loaded. |
| `an item that isn't there says so` | An unknown item shows the server's "No such item." in an alert and no rows. |
| `a series whose pages don't group offers no grouping status` | For a series whose pages don't group into records, the Status filter has no "Not in a ..." option. |
| `Pg 1/2/3 opens its matching US7 page` — 3 tests                         | Each page's Review link opens the matching page in the review screen.                                                                                                             |
| `page table keeps actions visible at 936/640/375px` — 3 tests            | Flags and review actions remain visible without horizontal table overflow at desktop, tablet and phone widths.                                                                    |
| `untouched item prompts Transcribe and shows no reviewable pages`        | An item without pages or a job shows No reviewable pages, the not-started message and an enabled Transcribe button beside the filters.                                            |
| `partial item shows model and completion action without review access`   | A failed partial item offers Retry transcription and error details; its page list shows the incomplete notice, Complete transcription and the saved model, with no Review link.   |
| `waiting job disables duplicate transcription`                           | A queued job disables the transcription button and keeps the incomplete notice visible.                                                                                           |
| `running job disables duplicate transcription`                           | A running job disables the transcription button and keeps the incomplete notice visible.                                                                                          |
| `loaded item shows model or dash and hides incomplete notice`            | The Model column shows saved model information or a dash; completed items hide the incomplete notice and transcription action.                                                    |
| `pagination changes rows and searching resets to first page`             | Eleven pages span two table pages; searching from the second page resets pagination and shows matching rows.                                                                      |
| `item, page and status stay in the URL across reload and Back` | An item's table page and status filter are in the URL, survive a reload and are undone one step at a time by Back, down to the items list. |
| `clicking an item row opens it, but its Transcribe button only opens the dialog` | A click on an item's row opens the item; its Transcribe button opens the Transcribe dialog without opening the item. |
| `a failed item's Retry and error buttons act without opening the item` | Retry transcription and the error details button on a failed item's row open their dialogs and leave the list where it is. |
| `item rows have one keyboard stop, an Actions header, and open natively in a new tab` | Each row has one link and no buttons, under a single Actions header; Ctrl-click opens it in a new tab and Enter on the focused link opens it here. |
| `clicking a plain cell in a page row opens that page` | A click on a page row's ordinary cell opens that page in the review screen. |
| `awaiting transcription page has a Transcribe action targeting its survey page` | A page awaiting transcription links Transcribe to its survey page with the transcribe action, and has no Review link. |
| `polling waits for a slow refresh instead of piling up requests` | While a refresh is still unanswered, later polls send no new request; polling resumes once it finishes. |
| `failed progress request can be retried`                                 | A failed request displays its error; Try again restores the dashboard after the API recovers.                                                                                     |
| `polling updates review counts without a reload`                         | Updated API data changes the displayed reviewed count and percentage automatically.                                                                                               |

Related backend coverage lives in `tests/unit/test_progress.py` (5 tests): model/status/flag response data and review targets, saved versus unsaved reviews, reviews of resident, child and annotation fields, a transcribed page in no survey not being ready to review, and the progress being worked out again only after the database changes. Run it with `uv run pytest tests/unit/test_progress.py`.

### US7 → US9 review round trip — 3 browser tests

`review round trip: saved/unsaved/failed save updates progress only after persistence` opens an item that is one record from US9, at its first page, reviews all fields in US7, and returns through Back to All items. An accepted save updates the reviewed count, ready count, percentage, page status, flags and View action, including after refresh. Unsaved drafts and rejected saves leave progress unchanged. These tests use a stateful mock API; they verify the screen-to-screen flow, not real database persistence.

## `page-actions.spec.ts` — 5 tests

Checks same-item moves, immediate type changes without queuing, persistence of the transcription prompt after refresh, and separate transcription with or without a preceding type change. Also checks editable model selection and the model table, and that in a series whose pages don't group a page can't be moved to another record and the screen uses the series' own word for one.

## Import screen browser tests — 5 tests

`import.spec.ts` tests the import screen (`/?view=import`) in a real browser. Uploads are intercepted, so no
file reaches the data folder; the server's own checks are in `tests/unit/test_uploads.py`.

```bash
npm --prefix tests run test:e2e -- import.spec.ts
```

| Test                                                                                    | What it checks                                                                                                          |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `files need a bundle number, and unsupported, empty or repeated files are not added`    | Import stays disabled until every file has a 1–30 digit bundle number; other types, empty files and repeats are left out. |
| `each file is sent with its own bundle number and a refusal shows the server's reason`  | Each upload carries its file's trimmed bundle number; a refused file keeps its row editable and shows why.              |
| `page images of one bundle share its bundle number`                                     | Two page images with the same bundle number are both sent under it.                                                     |
| `controls are locked while an upload is under way`                                      | Choose files, Remove and the bundle numbers are disabled until the upload finishes.                                     |
| `a dropped file is added`                                                               | Dragging a file over the drop zone highlights it, and dropping adds the file.                                           |
