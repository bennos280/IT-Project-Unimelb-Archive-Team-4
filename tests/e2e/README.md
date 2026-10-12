# End-to-end tests

Tests the review screen in a real browser using Playwright.
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

These tests use mocked API responses. The integration runner separately
checks the real frontend adapter, backend and database.
The highlight test checks visibility and zoom, not coordinate accuracy.
