# End-to-end tests

The whole system behind a pipeline job: the API, the worker, the pipeline, the loader and the real database tables
(built by the migrations). Only page sorting (a GPU model) and the paid model call are faked, so these run in CI.

**1 Python pipeline test**, plus the Playwright browser tests documented below.

```bash
uv run pytest tests/e2e
```

## `test_pipeline_job.py` — 1 test

| Test                                       | What it checks                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `test_queued_bundle_comes_back_as_surveys` | A 4-page PDF (two surveys, numbered 7 and 9) is listed by `GET /bundles`, queued with `POST /jobs`, and run by the worker through the real split, group and loader steps into tables built by the migrations. It then shows as loaded with a done job of 4/4 pages and its surveys in scan order (`bundle-7`, `bundle-9`). `GET /survey/bundle-9` returns its main form and coded card, the main form's `imageUrl` serves a PNG scan, and the address field holds the transcribed "9 Peel St."; running the bundle again is refused (409). |

## Manual check with the real model (paid)

Before a demo, or after changing the pipeline, run one real bundle. A 130-page bundle takes about 15 minutes.

1. Start the app with `uv run app` (the API and the worker).
2. Open http://127.0.0.1:8000/docs and queue a bundle that isn't loaded yet with `POST /jobs` (its `pdf` as `GET /bundles` lists it).
3. Watch it go with `GET /bundles`: its job's `step` moves from split to transcribe (with `donePages`/`totalPages`), then the bundle shows `loaded` with its `surveys`.
4. Open `http://127.0.0.1:8000/survey/<one of those survey ids>`: it should list its main form, notes and coded card.
5. Optional: press Ctrl+C mid-run, run `uv run app` again and queue the bundle again. The job is marked failed when stopped, then carries on without paying again for pages already read.

## UI browser tests

Tests the review screen, progress dashboard and export dialog in a real browser using Playwright.
Each test uses a sample survey, mock images and an isolated mock API.
No running backend or database is needed.

Run from the project folder:

```bash
npm --prefix tests run test:e2e
```

## `review.spec.ts` — 17 tests

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

## `progress.spec.ts` — 21 tests (US9: track progress)

Located in `tests/e2e/ui-reviewscreen/progress.spec.ts`. Run only these tests from the project folder:

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

`review round trip: saved/unsaved/failed save updates progress only after persistence` opens a page from US9, reviews all fields in US7, and returns through Back to all bundles. An accepted save updates the reviewed count, ready count, percentage, page status, flags and View action, including after refresh. Unsaved drafts and rejected saves leave progress unchanged. These tests use a stateful mock API; they verify the screen-to-screen flow, not real database persistence.

## `page-actions.spec.ts` — 3 tests

Checks same-bundle moves, immediate type changes without queuing, persistence of the transcription prompt after refresh, and separate transcription with or without a preceding type change. Also checks editable model selection and the model table.
