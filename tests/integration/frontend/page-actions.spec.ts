import { test, expect } from "@playwright/test";

// Browser tests use mocked API responses: no real database or transcription service is called.
// This scenario checks history, reviewer selection and moving a page within one bundle.
test("move keeps page identity and opens its destination; same types are allowed", async ({
  page,
}) => {
  // Simulate the server returning the destination survey after a successful move.
  let moved = false;
  const card = {
    id: "b/p4",
    type: "main",
    imageUrl: "/scan.svg",
    fields: [
      {
        id: "address",
        label: "Address",
        group: "Address",
        value: "24 Test Street",
      },
    ],
    flags: [],
  };
  // Supply a small image so the viewer does not depend on a real survey scan.
  await page.route("**/scan.svg", (r) =>
    r.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"/>',
    }),
  );
  await page.route("**/api/**", async (r) => {
    // Decode page IDs such as b%2Fp4 before matching the mocked endpoint.
    const path = decodeURIComponent(new URL(r.request().url()).pathname);
    const json = (body: unknown) => r.fulfill({ json: body });
    if (path === "/api/page-history/b/p4")
      return json({
        revision: 2,
        events: [
          {
            id: "version-1",
            time: "2026-10-14T00:00:00Z",
            reviewer: "Alex",
            title: "Page type changed",
            details: "Previous page type: notes.",
            snapshot: {
              fields: [
                { field_title: "address", text_raw: "Previous address" },
              ],
            },
          },
        ],
      });
    if (path === "/api/transcription-models")
      return json({
        configured: { model: "test-model", provider: "claude", effort: "low" },
        models: [],
      });
    if (path === "/api/reviewers") return json([{ id: 1, name: "Alex" }]);
    if (path.startsWith("/api/reviews/"))
      return json({ reviews: {}, revisions: { "b/p4": 0 } });
    if (path.startsWith("/api/survey/"))
      return json({ id: moved ? "s2" : "s1", title: "Survey", pages: [card] });
    if (path === "/api/page-actions/b/p4")
      return json({
        bundleId: "b",
        surveyId: moved ? "s2" : "s1",
        category: "main",
        revision: 0,
        hasReviews: false,
        job: null,
        surveys: [
          { id: "s1", pages: [{ id: "b/p4", type: "main" }] },
          { id: "s2", pages: [{ id: "b/p5", type: "main" }] },
        ],
      });
    // Check that the move request identifies the page's source, destination and reviewer.
    if (path === "/api/page-moves/b/p4") {
      expect(r.request().method()).toBe("PUT");
      expect(r.request().postDataJSON()).toEqual({
        surveyId: "s2",
        sourceSurveyId: "s1",
        reviewerId: 1,
        revision: 0,
        reason: "Same household",
      });
      moved = true;
      return json({ surveyId: "s2", pageId: "b/p4" });
    }
    return r.fulfill({ status: 404, json: { detail: path } });
  });
  await page.goto("/?survey=s1&page=b%2Fp4");
  // History belongs to the toolbar and can expand a stored snapshot without changing the page.
  const toolbar = page.getByTestId("page-toolbar");
  await expect(
    toolbar.getByRole("button", { name: "Page actions", exact: true }),
  ).toBeVisible();
  await toolbar.getByRole("button", { name: "History", exact: true }).click();
  const history = page.getByRole("dialog", {
    name: "Page history",
    exact: true,
  });
  await expect(
    history.getByText("Page type changed", { exact: true }),
  ).toBeVisible();
  // Each of the five columns has room, so the Details button sits inside its own cell.
  const detailsColumn = await history.getByRole("columnheader", { name: "Details" }).boundingBox();
  const snapshotButton = await history.getByRole("button", { name: "View snapshot", exact: true }).boundingBox();
  expect(detailsColumn!.width).toBeGreaterThan(snapshotButton!.width);
  expect(snapshotButton!.x).toBeGreaterThanOrEqual(detailsColumn!.x);
  await history
    .getByRole("button", { name: "View snapshot", exact: true })
    .click();
  await expect(
    history.getByText("Previous address", { exact: true }),
  ).toBeVisible();
  await history.getByRole("button", { name: "Close", exact: true }).click();
  await expect(history).not.toBeVisible();
  // No reviewer or destination has been selected yet, so moving must be disabled.
  await page.getByRole("button", { name: "Page actions", exact: true }).click();
  await page
    .getByRole("button", { name: "Move to another survey", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Move page", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  // Choose a reviewer, then move to a survey that already contains another main page.
  await page
    .getByRole("combobox", { name: "Reviewer name", exact: true })
    .selectOption("Alex");
  await page.getByRole("button", { name: "Page actions", exact: true }).click();
  await page
    .getByRole("button", { name: "Move to another survey", exact: true })
    .click();
  await page.getByLabel("Destination survey").selectOption("s2");
  await expect(
    page.getByText(/Multiple pages of the same type are allowed/),
  ).toBeVisible();
  await page.getByLabel("Reason (optional)").fill("Same household");
  await page.getByRole("button", { name: "Move page", exact: true }).click();
  // Navigation changes the survey, while the page ID and extracted value remain the same.
  await expect(page).toHaveURL(/survey=s2&page=b%2Fp4/);
  await expect(page.locator("[data-page-id]")).toHaveAttribute(
    "data-page-id",
    "b/p4",
  );
  await expect(page.getByText("24 Test Street", { exact: true })).toBeVisible();
});

// Exercise both entry points: change the type first, or open Transcribe directly from a page-list link.
for (const changeType of [true, false]) {
  test(`transcribe is separate from type change: change type ${changeType}`, async ({
    page,
  }) => {
    // These variables represent server state across requests and browser reloads.
    let category = "main";
    let needed = false;
    let queued = false;
    let done = false;
    let classificationRequests = 0;
    await page.route("**/api/**", async (r) => {
      const path = decodeURIComponent(new URL(r.request().url()).pathname);
      const json = (body: unknown) => r.fulfill({ json: body });
      if (path === "/api/transcription-models")
        return json({
          configured: {
            model: "test-model",
            provider: "claude",
            effort: "low",
          },
          models: [],
        });
      if (path === "/api/reviewers") return json([{ id: 1, name: "Alex" }]);
      if (path.startsWith("/api/reviews/"))
        return json({ reviews: {}, revisions: {} });
      if (path.startsWith("/api/survey/"))
        return json({
          id: "s1",
          title: "Survey",
          pages: [
            {
              id: "b/p4",
              type: category,
              typeLabel: category === "coded" ? "Coded page" : "Main page",
              needsTranscription: needed,
              imageUrl: "/scan.svg",
              fields: [
                {
                  id: "text",
                  label: "Text",
                  group: "Notes",
                  value: done ? "New transcription" : "Sample",
                },
              ],
              flags: [],
            },
          ],
        });
      // The next status poll after queuing reports completion, prompting the UI to reload its fields.
      if (path === "/api/page-actions/b/p4") {
        if (queued) {
          done = true;
          needed = false;
        }
        return json({
          bundleId: "b",
          surveyId: "s1",
          category,
          revision: classificationRequests,
          hasReviews: false,
          surveys: [],
          job: queued
            ? { id: 1, status: "done", pageType: category, error: null }
            : null,
        });
      }
      // Classification changes the type and revision but must not queue transcription.
      if (path === "/api/page-classification/b/p4") {
        expect(r.request().postDataJSON()).toEqual({
          pageType: "coded",
          reviewerId: 1,
          revision: 0,
        });
        category = "coded";
        needed = true;
        classificationRequests++;
        return json({ pageType: category, needsTranscription: true });
      }
      // A separate request must carry the selected model settings and the current revision.
      if (path === "/api/page-transcription/b/p4") {
        expect(r.request().postDataJSON()).toEqual({
          reviewerId: 1,
          revision: classificationRequests,
          model: "custom-model",
          provider: "claude",
          effort: "low",
        });
        queued = true;
        return json({
          job: { id: 1, status: "waiting", pageType: category, error: null },
        });
      }
      return r.fulfill({ status: 404, json: { detail: path } });
    });
    // action=transcribe should open the model dialog automatically for the requested page.
    await page.goto(
      changeType ? "/?survey=s1" : "/?survey=s1&page=b%2Fp4&action=transcribe",
    );
    if (changeType)
      await page
        .getByRole("combobox", { name: "Reviewer name", exact: true })
        .selectOption("Alex");
    else
      await page
        .getByRole("dialog", { name: "Transcribe page" })
        .getByRole("combobox", { name: "Reviewer", exact: true })
        .selectOption("Alex");
    if (changeType) {
      await page.getByRole("button", { name: "Page actions", exact: true }).click();
      await page
        .getByRole("button", { name: "Change page type", exact: true })
        .click();
      const dialog = page.getByRole("dialog", { name: "Change page type" });
      // Type changes need no model selection; the reminder must survive a reload.
      await expect(dialog.getByLabel("Model", { exact: true })).toHaveCount(0);
      await page.getByLabel("Correct page type").selectOption("coded");
      await dialog
        .getByRole("button", { name: "Change page type", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { level: 2, name: /^b\/p4 ·/ }),
      ).toHaveText("b/p4 · Coded page");
      await expect(
        page.getByText(
          "Page has been changed to a different page type. Click the Transcribe button.",
          { exact: true },
        ),
      ).toBeVisible();
      expect(queued).toBe(false);
      await page.reload();
      await expect(
        page.getByText(
          "Page has been changed to a different page type. Click the Transcribe button.",
          { exact: true },
        ),
      ).toBeVisible();
      await page
        .getByRole("combobox", { name: "Reviewer name", exact: true })
        .selectOption("Alex");
    }
    if (changeType)
      await page
        .getByTestId("page-toolbar")
        .getByRole("button", { name: "Transcribe", exact: true })
        .click();
    // Reviewers can inspect model information and return to the transcription form.
    await page.getByRole("button", { name: "View model table" }).click();
    await expect(
      page.getByRole("heading", { name: "Transcription models", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Back to transcription" }).click();
    const dialog = page.getByRole("dialog", { name: "Transcribe page" });
    // A model is required, and reviewers can enter a custom model name.
    await page.getByLabel("Model", { exact: true }).fill("");
    await expect(
      dialog.getByRole("button", { name: "Transcribe", exact: true }),
    ).toBeDisabled();
    await page.getByLabel("Model", { exact: true }).fill("custom-model");
    await dialog
      .getByRole("button", { name: "Transcribe", exact: true })
      .click();
    await expect(dialog).not.toBeVisible();
    // Wait for polling to load the replacement data and clear the transcription reminder.
    await expect(page.getByText("New transcription", { exact: true })).toBeVisible(
      { timeout: 10000 },
    );
    await expect(
      page.getByText(
        "Page has been changed to a different page type. Click the Transcribe button.",
        { exact: true },
      ),
    ).toHaveCount(0);
  });
}

test("the page's Transcribe dialog prefills nothing and links to Settings when no model is saved, yet can run with one picked there", async ({ page }) => {
  const sent: unknown[] = [];
  await page.route("**/scan.svg", (r) =>
    r.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"/>' }));
  await page.route("**/api/**", async (r) => {
    const path = decodeURIComponent(new URL(r.request().url()).pathname);
    const json = (body: unknown) => r.fulfill({ json: body });
    if (path === "/api/transcription-models") return json({ configured: null, models: [] });
    if (path === "/api/reviewers") return json([{ id: 1, name: "Alex" }]);
    if (path.startsWith("/api/reviews/")) return json({ reviews: {}, revisions: {} });
    if (path.startsWith("/api/survey/"))
      return json({ id: "s1", title: "Survey", pages: [{ id: "b/p4", type: "main", imageUrl: "/scan.svg", fields: [], flags: [] }] });
    if (path === "/api/page-actions/b/p4")
      return json({ bundleId: "b", surveyId: "s1", category: "main", revision: 0, hasReviews: false, job: null, surveys: [] });
    if (path === "/api/page-transcription/b/p4") {
      sent.push(r.request().postDataJSON());
      return json({ job: { id: 1, status: "waiting", pageType: "main", error: null } });
    }
    return r.fulfill({ status: 404, json: { detail: path } });
  });
  await page.goto("/?survey=s1&page=b%2Fp4&action=transcribe");
  const dialog = page.getByRole("dialog", { name: "Transcribe page" });
  await expect(dialog.getByText("No transcription model is set.")).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Choose one on the Settings page" })).toHaveAttribute("href", "/?view=settings");
  await expect(dialog.getByLabel("Model", { exact: true })).toHaveValue("");
  await expect(dialog.getByLabel("Effort", { exact: true })).toHaveValue("");
  await expect(dialog.getByLabel("Provider", { exact: true })).toHaveValue("");
  await dialog.getByRole("combobox", { name: "Reviewer", exact: true }).selectOption("Alex");
  const transcribe = dialog.getByRole("button", { name: "Transcribe", exact: true });
  await expect(transcribe).toBeDisabled();
  await dialog.getByLabel("Model", { exact: true }).fill("sonnet");
  await dialog.getByLabel("Effort", { exact: true }).fill("low");
  await expect(transcribe).toBeDisabled(); //the provider is chosen too
  await dialog.getByLabel("Provider", { exact: true }).selectOption("claude");
  await dialog.getByLabel("Model", { exact: true }).fill("sonnet");
  await transcribe.click();
  await expect(dialog).not.toBeVisible();
  expect(sent).toEqual([{ reviewerId: 1, revision: 0, model: "sonnet", provider: "claude", effort: "low" }]);
});
