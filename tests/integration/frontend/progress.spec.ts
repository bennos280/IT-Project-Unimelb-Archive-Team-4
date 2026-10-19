import { test, expect, type Locator, type Page } from "@playwright/test";

// The review-progress cell is the fourth column of a bundle row.
const meter = (row: Locator) => row.getByRole("cell").nth(3);
const incompleteNotice = (page: Page) =>
  page.getByRole("status").filter({ hasText: /has not (finished processing|been processed yet)/ });
const filters = (page: Page) => page.getByTestId("progress-filters");
const bundleRows = (page: Page) => page.locator("tbody").getByRole("row");
const pageRow = (page: Page, label: string) =>
  bundleRows(page).filter({
    has: page.getByRole("link", { name: new RegExp(`^(Review|View|Transcribe) ${label}$`) }),
  });

test.describe("Progress navigation and layout", () => {
  const survey = {
    id: "216417_1",
    title: "Wilfred Prest Survey",
    collectionId: 1,
    pages: ["main", "notes", "coded"].map((type, index) => ({
      id: `216417/p${index}`,
      type,
      imageUrl: "/test-scan.svg",
      fields: Array.from({ length: index === 0 ? 5 : 1 }, (_, field) => ({
        id: `test${field}`,
        label: `Test field ${field}`,
        group: "Test",
        value: "Sample value",
      })),
      flags:
        index === 0
          ? Array.from({ length: 5 }, (_, field) => ({
              id: `flag${field}`,
              fieldId: `test${field}`,
              kind: "uncertain",
              reason: "Check handwriting.",
            }))
          : [],
    })),
  };

  // Intercept requests before opening the page.
  // No requests reach the real backend or database.
  test.beforeEach(async ({ page }) => {
    await page.route("**/test-scan.svg", (route) =>
      route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"/>',
      }),
    );

    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;

      if (path === "/api/collections/1")
        return route.fulfill({ json: { id: 1, name: "Wilfred Prest Survey", recordKey: "number_of_dwelling", archiveSeries: 499420 } });
      if (path === "/api/progress")
        return route.fulfill({
          json: [
            {
              id: "216417",
              pages: survey.pages.map((p, i) => ({
                id: p.id,
                label: `Pg ${i + 1}`,
                category: p.type,
                status: "Ready to review",
                flagCount: p.flags.length,
                surveyId: survey.id,
                reviewPageId: p.id,
              })),
            },
          ],
        });
      if (path === "/api/bundles") return route.fulfill({ json: [] });
      if (path === "/api/survey/216417_1") {
        return route.fulfill({ json: survey });
      }

      if (path === "/api/reviews/216417_1") {
        return route.fulfill({
          json: { reviews: {}, revisions: {} },
        });
      }

      if (path === "/api/reviewers") {
        return route.fulfill({ json: [] });
      }

      return route.fulfill({
        status: 404,
        json: { detail: `Unexpected test request: ${path}` },
      });
    });
  });

  // test API responses connect the review screen and progress screens without touching
  // the development database. Progress changes only after an accepted save.
  for (const outcome of ["saved", "unsaved", "failed save"] as const) {
    test(`review round trip: ${outcome} updates progress only after persistence`, async ({
      page,
    }) => {
      let persisted = false;
      let saveRequests = 0;
      let savedReviews = {};
      await page.route("**/api/reviewers", (route) =>
        route.fulfill({ json: [{ id: 1, name: "Test reviewer" }] }),
      );
      await page.route("**/api/reviews/216417_1", async (route) => {
        if (route.request().method() === "POST") {
          saveRequests++;
          if (outcome === "failed save")
            return route.fulfill({
              status: 409,
              json: { detail: "Page changed in another tab." },
            });
          const payload = route.request().postDataJSON();
          expect(
            Object.keys(payload.reviews[survey.pages[0].id]).sort(),
          ).toEqual(survey.pages[0].fields.map((f) => f.id).sort());
          const savedAt = "2026-10-13T01:00:00Z";
          savedReviews = {
            [survey.pages[0].id]: Object.fromEntries(
              Object.entries(payload.reviews[survey.pages[0].id]).map(
                ([id, review]) => [id, { ...(review as object), savedAt }],
              ),
            ),
          };
          persisted = true;
          return route.fulfill({ json: { revision: 1, savedAt } });
        }
        return route.fulfill({
          json: {
            reviews: savedReviews,
            revisions: persisted ? { [survey.pages[0].id]: 1 } : {},
          },
        });
      });
      await page.route(/\/api\/progress(\?.*)?$/, (route) =>
        route.fulfill({
          json: [
            {
              id: "216417",
              pages: survey.pages.map((p, i) => ({
                id: p.id,
                label: `Pg ${i + 1}`,
                category: p.type,
                status: persisted && i === 0 ? "Reviewed" : "Ready to review",
                flagCount: persisted && i === 0 ? 0 : p.flags.length,
                surveyId: survey.id,
                reviewPageId: p.id,
              })),
            },
          ],
        }),
      );

      await page.goto("/?collection=1");
      const bundleRow = bundleRows(page).filter({
        has: page.getByRole("link", { name: "216417", exact: true }),
      });
      await expect(meter(bundleRow)).toContainText("0 / 3 reviewed · 0%");
      await page.getByRole("link", { name: "216417", exact: true }).click();
      const firstRow = pageRow(page, "Pg 1");
      await expect(firstRow).toContainText("5 need checking");
      await firstRow.getByRole("link", { name: "Review Pg 1", exact: true }).click();
      await expect(page.getByRole("heading", { name: "216417/p0 ·" })).toBeVisible();
      await page
        .getByRole("combobox", { name: "Reviewer name", exact: true })
        .selectOption("Test reviewer");
      // Flagged fields must be reviewed individually before saving.
      for (const field of survey.pages[0].fields) {
        await page.getByRole("button", { name: `Edit ${field.label}`, exact: true }).click();
        await page.getByRole("button", { name: "Apply review", exact: true }).click();
      }
      expect(persisted).toBe(false);
      if (outcome !== "unsaved") {
        await page
          .getByRole("button", { name: "Save Page Transcript", exact: true })
          .click();
        if (outcome === "saved") {
          await expect(
            page.getByText("Reviewed by:"),
          ).toHaveCount(5);
        } else {
          await expect(
            page.getByRole("status").filter({ hasText: "Page changed in another tab." }),
          ).toHaveText("Page changed in another tab.");
        }
      }
      // Accept the browser's leave warning for deliberately discarded drafts.
      page.on("dialog", (dialog) => dialog.accept());
      await page.getByRole("link", { name: "Wilfred Prest Survey" }).click();
      const complete = outcome === "saved";
      expect(saveRequests).toBe(outcome === "unsaved" ? 0 : 1);
      for (const refresh of [false, true]) {
        if (refresh) await page.reload();
        await expect(meter(bundleRow)).toContainText(
          complete ? "1 / 3 reviewed · 33%" : "0 / 3 reviewed · 0%",
        );
        await expect(page.getByTestId("stat-reviewed")).toHaveText(
          complete ? "1" : "0",
        );
        await expect(page.getByTestId("stat-ready-to-review")).toHaveText(
          complete ? "2" : "3",
        );
      }
      await page.getByRole("link", { name: "216417", exact: true }).click();
      await expect(firstRow.getByRole("cell").nth(3)).toHaveText(
        complete ? "Reviewed" : "Ready to review",
      );
      await expect(firstRow).toContainText(
        complete ? "No flags" : "5 need checking",
      );
      await expect(
        firstRow.getByRole("link", {
          name: complete ? "View Pg 1" : "Review Pg 1",
          exact: true,
        }),
      ).toBeVisible();
    });
  }

  test("searches items and clears an empty result", async ({ page }) => {
    await page.goto("/?collection=1");

    await expect(
      page.getByRole("heading", { name: "All items" }),
    ).toBeVisible();

    await page.getByLabel("Search items").fill("216417");
    await expect(bundleRows(page)).toHaveCount(1);

    await page.getByLabel("Search items").fill("missing");
    await expect(
      page.getByText("No items match your filters."),
    ).toBeVisible();

    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(bundleRows(page)).toHaveCount(1);
  });

  test("disables pagination for one item and filters by status", async ({
    page,
  }) => {
    await page.goto("/?collection=1");

    await expect(
      page.getByRole("button", { name: "Next", exact: true }),
    ).toBeDisabled();

    await page.getByLabel("Status", { exact: true }).selectOption("Reviewed");
    await expect(
      page.getByText("No items match your filters."),
    ).toBeVisible();

    await page
      .getByLabel("Status", { exact: true })
      .selectOption("Ready to review");

    await expect(
      page.getByRole("link", { name: "216417", exact: true }),
    ).toBeVisible();
  });

  test("opens item pages with matching review targets", async ({ page }) => {
    await page.goto("/?collection=1");
    await page.getByRole("link", { name: "216417", exact: true }).click();

    await expect(
      page.getByRole("heading", { name: "Item 216417" }),
    ).toBeVisible();

    const notesRow = pageRow(page, "Pg 2");

    await expect(
      notesRow.getByRole("link", { name: "Review Pg 2", exact: true }),
    ).toHaveAttribute("href", "/?survey=216417_1&page=216417%2Fp1");

    await page.getByRole("link", { name: "Wilfred Prest Survey" }).click();

    await expect(
      page.getByRole("heading", { name: "All items" }),
    ).toBeVisible();
  });

  test("Import opens the import screen", async ({ page }) => {
    await page.goto("/?collection=1");
    await page.getByRole("button", { name: "Import", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Import items" })).toBeVisible();
  });

  for (const [label, pageId] of [
    ["Pg 1", "216417/p0"],
    ["Pg 2", "216417/p1"],
    ["Pg 3", "216417/p2"],
  ]) {
    test(`${label} opens its matching US7 page`, async ({ page }) => {
      await page.goto("/?collection=1");
      await page.getByRole("link", { name: "216417", exact: true }).click();

      const row = pageRow(page, label);

      await expect(row.getByRole("link")).toHaveCount(1);

      await row.getByRole("link", { name: `Review ${label}`, exact: true }).click();

      await expect(page.getByRole("heading", { name: `${pageId} ·` })).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Transcript Review" }),
      ).toBeVisible();
    });
  }

  for (const width of [936, 640, 375]) {
    test(`page table keeps actions visible at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/?collection=1");
      await page.getByRole("link", { name: "216417", exact: true }).click();

      await expect(
        page.getByRole("columnheader", { name: "Flags", exact: true }),
      ).toBeVisible();

      await expect(
        page.getByRole("columnheader", { name: "Survey ID", exact: true }),
      ).toHaveCount(0);

      await expect(
        page.getByRole("cell", { name: "5 need checking", exact: true }),
      ).toBeVisible();

      const links = page.getByRole("link", { name: /^Review Pg \d$/ });
      await expect(links).toHaveCount(3);

      for (const link of await links.all()) {
        await expect(link).toBeVisible();
        const box = await link.boundingBox();
        expect(box).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      }

      expect(
        await page
          .getByRole("table")
          .locator("..")
          .evaluate(
            (element) => element.scrollWidth <= element.clientWidth + 1,
          ),
      ).toBe(true);
    });
  }
});

test.describe("Progress and transcription states", () => {
  const readyPage = (i: number) => ({
    id: `p${i}`,
    label: `Pg ${i}`,
    category: "Main page",
    status: "Ready to review",
    flagCount: 0,
    surveyId: "s",
    reviewPageId: `p${i}`,
    model: i === 1 ? "test-model" : null,
  });

  async function mock(
    page: Page,
    options: {
      loaded?: boolean;
      status?: string;
      partial?: boolean;
      count?: number;
      archive?: boolean;
    } = {},
  ) {
    const loaded = options.loaded ?? false;
    const job = options.status
      ? {
          id: 1,
          status: options.status,
          step: "transcribe",
          donePages: 1,
          totalPages: 2,
          error:
            options.status === "failed" ? "Test transcription failure" : null,
        }
      : null;
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/progress")
        return route.fulfill({
          json: loaded
            ? [
                {
                  id: "b",
                  pages: Array.from({ length: options.count ?? 2 }, (_, i) =>
                    readyPage(i + 1),
                  ),
                },
              ]
            : [],
        });
      if (path === "/api/bundles")
        return route.fulfill({
          json: [
            {
              bundle: "b",
              name: "216424",
              archive: options.archive ? { identifier: "UMA-ITE-1973000200013", title: "Collingwood 07" } : null,
              pdf: "b.pdf",
              loaded,
              surveys: [],
              job,
            },
          ],
        });
      if (path === "/api/jobs/1") return route.fulfill({ json: job });
      if (path === "/api/jobs/1/transcripts")
        return route.fulfill({
          json: {
            pages: options.partial
              ? [
                  {
                    id: "b_00001",
                    category: "main",
                    status: "Transcribed — not grouped",
                    data: { model: "partial-model" },
                  },
                ]
              : [],
          },
        });
      return route.fulfill({
        status: 404,
        json: { detail: `Unexpected request: ${path}` },
      });
    });
    await page.goto("/?collection=1");
  }

  async function openBundle(page: Page) {
    await page.getByRole("link", { name: "216424", exact: true }).click();
  }

  test("an archive item is listed by its title over its identifier and number, found by any of them, and its page links to the archive", async ({
    page,
  }) => {
    await mock(page, { loaded: true, archive: true });
    const row = bundleRows(page).filter({ has: page.getByRole("link", { name: "Collingwood 07", exact: true }) });
    await expect(row).toContainText("UMA-ITE-1973000200013 · 216424");
    await expect(row.getByRole("link")).toHaveCount(1);
    for (const [query, found] of [["collingwood", 1], ["UMA-ITE-1973000200013", 1], ["216424", 1], ["brighton", 0]] as const) {
      await page.getByLabel("Search items").fill(query);
      await expect(row).toHaveCount(found);
    }
    await page.getByLabel("Search items").fill("");
    await row.getByRole("link").click();
    await expect(page.getByRole("heading", { name: "Collingwood 07", level: 1 })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" }).locator('[aria-current="page"]')).toHaveText("Collingwood 07");
    const archive = page.getByRole("link", { name: "UMA-ITE-1973000200013" });
    await expect(archive).toHaveAttribute("href", "https://archives.library.unimelb.edu.au/nodes/view/216424");
    await expect(archive).toHaveAttribute("target", "_blank");
    await expect(page.locator("main")).toContainText("UMA-ITE-1973000200013 · 216424 · 2 pages ready to review");
  });

  test("the Transcribe and error dialogs and the progress bar name an archive item by its title", async ({ page }) => {
    await mock(page, { status: "failed", archive: true });
    const row = bundleRows(page).filter({ has: page.getByRole("link", { name: "Collingwood 07", exact: true }) });
    await row.getByRole("button", { name: "Retry transcription", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Transcribe scans" })).toHaveAccessibleDescription("Collingwood 07");
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await row.getByRole("button", { name: "more details here" }).click();
    await expect(page.getByRole("dialog", { name: "Transcription error" })).toHaveAccessibleDescription("Collingwood 07");
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await mock(page, { loaded: true, archive: true });
    await expect(page.getByRole("progressbar", { name: "Collingwood 07 review progress" })).toBeVisible();
  });

  test("untouched item prompts Transcribe and shows no reviewable pages", async ({
    page,
  }) => {
    await mock(page);
    await expect(
      page.getByText("No reviewable pages", { exact: true }),
    ).toBeVisible();
    await openBundle(page);
    await expect(
      page.getByText(
        "This item has not been processed yet. Press Transcribe to get started.",
      ),
    ).toBeVisible();
    await expect(
      filters(page).getByRole("button", { name: "Transcribe", exact: true }),
    ).toBeEnabled();
    await expect(
      page.getByRole("button", { name: "Complete transcription", exact: true }),
    ).toHaveCount(0);
  });

  test("partial item shows model and completion action without review access", async ({
    page,
  }) => {
    await mock(page, { status: "failed", partial: true });
    await expect(page.getByRole("button", { name: "View error" })).toHaveCount(
      0,
    );
    await page.getByRole("button", { name: "more details here" }).click();
    await expect(page.getByRole("dialog")).toContainText(
      "Test transcription failure",
    );
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Retry transcription" }),
    ).toBeEnabled();
    await openBundle(page);
    await expect(incompleteNotice(page)).toContainText(
      "has not finished processing",
    );
    await expect(
      filters(page).getByRole("button", { name: "Complete transcription" }),
    ).toBeEnabled();
    await expect(
      page.getByRole("cell", { name: "partial-model", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /^(Review|View|Transcribe) / }),
    ).toHaveCount(0);
  });

  for (const status of ["waiting", "running"]) {
    test(`${status} job disables duplicate transcription`, async ({ page }) => {
      await mock(page, { status });
      await openBundle(page);
      const action = filters(page).getByRole("button");
      await expect(action).toBeDisabled();
      await expect(action).toHaveAccessibleName(
        status === "waiting" ? "Waiting — queued" : "Transcription in progress",
      );
      await expect(incompleteNotice(page)).toContainText(
        "has not finished processing",
      );
    });
  }

  test("loaded item shows model or dash and hides incomplete notice", async ({
    page,
  }) => {
    await mock(page, { loaded: true });
    await openBundle(page);
    await expect(
      page.getByRole("columnheader", { name: "Model", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "test-model", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "—", exact: true }),
    ).toBeVisible();
    await expect(incompleteNotice(page)).toHaveCount(0);
    await expect(filters(page).getByRole("button")).toHaveCount(0);
  });

  test("pagination changes rows and searching resets to first page", async ({
    page,
  }) => {
    await mock(page, { loaded: true, count: 11 });
    await openBundle(page);
    await expect(bundleRows(page)).toHaveCount(9);
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByText("Showing 10–11 of 11 pages")).toBeVisible();
    await page.getByLabel("Search pages").fill("Pg 1");
    await expect(page.getByText("Showing 1–3 of 3 pages")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Previous", exact: true }),
    ).toBeDisabled();
  });

  test("item, page and status stay in the URL across reload and Back", async ({
    page,
  }) => {
    await mock(page, { loaded: true, count: 11 });
    await openBundle(page);
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page).toHaveURL(/\/\?collection=1&bundle=216424&page=2$/);
    await page.reload();
    await expect(page.getByText("Showing 10–11 of 11 pages")).toBeVisible();
    await page.getByLabel("Status").selectOption("Ready to review");
    await expect(page).toHaveURL(/\/\?collection=1&bundle=216424&status=Ready\+to\+review$/);
    await page.goBack();
    await expect(page.getByText("Showing 10–11 of 11 pages")).toBeVisible();
    await page.goBack();
    await expect(page.getByText("Showing 1–9 of 11 pages")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/\?collection=1$/);
    await expect(page.getByRole("link", { name: "216424", exact: true })).toBeVisible();
  });

  test("clicking an item row opens it, but its Transcribe button only opens the dialog", async ({
    page,
  }) => {
    await mock(page);
    const row = bundleRows(page).filter({
      has: page.getByRole("link", { name: "216424", exact: true }),
    });
    await row.getByRole("button", { name: "Transcribe", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Transcribe scans" })).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "All items" })).toBeVisible();
    await expect(page).toHaveURL(/\/\?collection=1$/);
    // The row link's overlay covers the Total pages cell, so click its centre with the mouse.
    const box = await row.getByRole("cell").nth(1).boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await expect(page.getByRole("heading", { name: "Item 216424" })).toBeVisible();
    await expect(page).toHaveURL(/\/\?collection=1&bundle=216424$/);
  });

  test("a failed item's Retry and error buttons act without opening the item", async ({
    page,
  }) => {
    await mock(page, { status: "failed" });
    const row = bundleRows(page).filter({
      has: page.getByRole("link", { name: "216424", exact: true }),
    });
    await row.getByRole("button", { name: "Retry transcription", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Transcribe scans" })).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await row.getByRole("button", { name: "more details here" }).click();
    await expect(page.getByRole("dialog")).toContainText("Test transcription failure");
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await expect(page.getByRole("heading", { name: "All items" })).toBeVisible();
    await expect(page).toHaveURL(/\/\?collection=1$/);
  });

  test("item rows have one keyboard stop, an Actions header, and open natively in a new tab", async ({
    page,
  }) => {
    await page.context().route("**/api/**", (route) => route.abort());
    await mock(page, { loaded: true });
    await expect(page.getByRole("columnheader", { name: "Actions", exact: true })).toHaveCount(1);
    const row = bundleRows(page).filter({
      has: page.getByRole("link", { name: "216424", exact: true }),
    });
    await expect(row.getByRole("link")).toHaveCount(1);
    await expect(row.getByRole("button")).toHaveCount(0);
    const link = row.getByRole("link", { name: "216424", exact: true });
    await expect(link).toHaveAttribute("href", "/?collection=1&bundle=216424");
    const opened = page.context().waitForEvent("page");
    await link.click({ modifiers: ["Control"] });
    const tab = await opened;
    expect(new URL(tab.url()).search).toBe("?collection=1&bundle=216424");
    await tab.close();
    await expect(page).toHaveURL(/\/\?collection=1$/);
    await expect(page.getByRole("heading", { name: "All items" })).toBeVisible();
    await link.focus();
    await expect(link).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Item 216424" })).toBeVisible();
    await expect(page).toHaveURL(/\/\?collection=1&bundle=216424$/);
    await expect(page.getByRole("columnheader", { name: "Actions", exact: true })).toHaveCount(1);
  });

  test("clicking a plain cell in a page row opens that page", async ({ page }) => {
    await mock(page, { loaded: true });
    await openBundle(page);
    const box = await pageRow(page, "Pg 2").getByRole("cell").nth(1).boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await expect(page).toHaveURL(/\/\?survey=s&page=p2/);
  });

  test("failed progress request can be retried", async ({ page }) => {
    await mock(page, { loaded: true });
    let failed = true;
    await page.route(/\/api\/progress(\?.*)?$/, (route) =>
      failed
        ? route.fulfill({ status: 500, json: { detail: "Temporary failure" } })
        : route.fulfill({ json: [{ id: "b", pages: [readyPage(1)] }] }),
    );
    await page.reload();
    await expect(page.getByRole("alert")).toContainText("Temporary failure");
    failed = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: "216424", exact: true }),
    ).toBeVisible();
  });

  test("polling updates review counts without a reload", async ({ page }) => {
    await mock(page, { loaded: true });
    await expect(
      page.getByText("0 / 2 reviewed · 0%", { exact: true }),
    ).toBeVisible();
    await page.route(/\/api\/progress(\?.*)?$/, (route) =>
      route.fulfill({
        json: [
          {
            id: "b",
            pages: [{ ...readyPage(1), status: "Reviewed" }, readyPage(2)],
          },
        ],
      }),
    );
    await expect(
      page.getByText("1 / 2 reviewed · 50%", { exact: true }),
    ).toBeVisible({ timeout: 10000 });
  });
  test("polling waits for a slow refresh instead of piling up requests", async ({
    page,
  }) => {
    await page.clock.install();
    await mock(page, { loaded: true });
    await expect(page.getByText("0 / 2 reviewed · 0%", { exact: true })).toBeVisible();
    let calls = 0;
    let release = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    await page.route(/\/api\/progress(\?.*)?$/, async (route) => {
      calls++;
      await held;
      await route.fulfill({ json: [{ id: "b", pages: [readyPage(1), readyPage(2)] }] });
    });
    await page.clock.runFor(5000);
    await expect.poll(() => calls).toBe(1);
    await page.clock.runFor(20000);
    // A request sent after the timers proves every poll they started has reached the routes.
    await Promise.all([
      page.waitForRequest("**/api/sync"),
      page.evaluate(() => fetch("/api/sync").catch(() => {})),
    ]);
    expect(calls).toBe(1);
    release();
    // Polling resumes once the slow refresh finishes; it ends asynchronously, so keep ticking until a poll goes out.
    await expect
      .poll(async () => {
        await page.clock.runFor(5000);
        return calls;
      })
      .toBeGreaterThanOrEqual(2);
  });
});

test('awaiting transcription page has a Transcribe action targeting its survey page', async ({ page }) => {
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/progress') return route.fulfill({json:[{id:'b',pages:[{id:'b/p4',label:'Pg 4',category:'Coded',status:'Awaiting transcription',flagCount:0,surveyId:'s1',reviewPageId:'b/p4'}]}]});
    if (path === '/api/bundles') return route.fulfill({json:[]});
    return route.fulfill({status:404,json:{detail:'Unexpected test request'}});
  });
  await page.goto("/?collection=1");
  await page.getByRole('link',{name:'b',exact:true}).click();
  const row=bundleRows(page).filter({hasText:'Pg 4'});
  await expect(row.getByRole('link',{name:'Transcribe Pg 4',exact:true})).toHaveAttribute('href','/?survey=s1&page=b%2Fp4&action=transcribe');
  await expect(row.getByRole('link',{name:'Review Pg 4',exact:true})).toHaveCount(0);
});

test.describe("Pages without a survey", () => {
  async function showBundle(page: Page, includeReviewedPage: boolean) {
    const pages = [
      {
        id: "unassigned-page",
        label: "Pg 2",
        category: "Notes",
        status: "Not in a survey",
        flagCount: 0,
        surveyId: null,
        reviewPageId: "unassigned-page",
      },
      ...(includeReviewedPage
        ? [{
            id: "reviewed-page",
            label: "Pg 1",
            category: "Main page",
            status: "Reviewed",
            flagCount: 0,
            surveyId: "survey-1",
            reviewPageId: "reviewed-page",
          }]
        : []),
    ];

    // Keep requests isolated from the real backend and review database.
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/progress") {
        return route.fulfill({ json: [{ id: "test-bundle", pages }] });
      }
      if (path === "/api/bundles") {
        return route.fulfill({ json: [] });
      }
      return route.fulfill({
        status: 404,
        json: { detail: `Unexpected request: ${path}` },
      });
    });
    await page.goto("/?collection=1");
    return page.getByRole("row").filter({
      has: page.getByRole("link", { name: "test-bundle", exact: true }),
    });
  }

  test("unassigned pages do not prevent 100% review progress", async ({ page }) => {
    const row = await showBundle(page, true);
    await expect(row.locator("td").nth(1)).toHaveText("2");
    await expect(meter(row)).toContainText("1 / 1 reviewed · 100%");
    await expect(meter(row)).toContainText("1 page not in a survey");
    const progress = row.getByRole("progressbar");
    await expect(progress).toHaveAttribute("aria-valuenow", "1");
    await expect(progress).toHaveAttribute("aria-valuemax", "1");
  });

  test("a page without a survey is not clickable but explains itself", async ({ page }) => {
    const row = await showBundle(page, true);
    await row.getByRole("link", { name: "test-bundle", exact: true }).click();
    const unassigned = bundleRows(page).filter({ hasText: "Pg 2" });
    await expect(unassigned.getByRole("link")).toHaveCount(0);
    await expect(unassigned).toHaveCSS("cursor", "auto");
    await expect(unassigned.getByTitle("This page has no survey assignment")).toHaveText("—");
    const assigned = bundleRows(page).filter({ hasText: "Pg 1" });
    await expect(assigned.getByRole("link", { name: "View Pg 1", exact: true })).toBeVisible();
    await expect(assigned).toHaveCSS("cursor", "pointer");
    await expect(page.getByRole("columnheader", { name: "Actions", exact: true })).toHaveCount(1);
  });

  test("an item with only unassigned pages has no review percentage", async ({ page }) => {
    const row = await showBundle(page, false);
    await expect(row.locator("td").nth(1)).toHaveText("1");
    await expect(meter(row)).toContainText("No reviewable pages");
    await expect(meter(row)).toContainText("1 page not in a survey");
    await expect(meter(row)).not.toContainText("%");
    await expect(row.getByRole("progressbar")).toHaveCount(0);
  });
});

test("with no transcription model saved, the dialog prefills nothing, links to Settings and still starts a run with the model picked there", async ({ page }) => {
  const started: unknown[] = [];
  await page.route("**/api/**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/progress") return route.fulfill({ json: [] });
    if (path === "/api/bundles")
      return route.fulfill({ json: [{ bundle: "b", name: "216424", pdf: "b.pdf", loaded: false, surveys: [], job: null }] });
    if (path === "/api/transcription-models") return route.fulfill({ json: { configured: null, models: [] } });
    if (path === "/api/jobs" && request.method() === "POST") {
      started.push(request.postDataJSON());
      return route.fulfill({ status: 202, json: { id: 1, status: "waiting", step: null, donePages: 0, totalPages: 0, error: null } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected request: ${path}` } });
  });
  await page.goto("/?collection=1");
  const row = bundleRows(page).filter({ has: page.getByRole("link", { name: "216424", exact: true }) });
  await row.getByRole("button", { name: "Transcribe", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Transcribe scans" });
  await expect(dialog.getByText("No transcription model is set.")).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Choose one on the Settings page" })).toHaveAttribute("href", "/?view=settings");
  await expect(dialog.getByLabel("Model", { exact: true })).toHaveValue("");
  await expect(dialog.getByLabel("Effort", { exact: true })).toHaveValue("");
  await expect(dialog.getByLabel("Provider", { exact: true })).toHaveValue("");
  const start = dialog.getByRole("button", { name: "Start transcription" });
  await expect(start).toBeDisabled();
  await dialog.getByLabel("Model", { exact: true }).fill("sonnet");
  await expect(start).toBeDisabled();
  await dialog.getByLabel("Effort", { exact: true }).fill("low");
  await expect(start).toBeDisabled(); //the provider is chosen too
  await dialog.getByLabel("Provider", { exact: true }).selectOption("claude");
  await dialog.getByLabel("Model", { exact: true }).fill("sonnet");
  await start.click();
  await expect(dialog).toHaveCount(0);
  expect(started).toEqual([{ pdf: "b.pdf", model: "sonnet", provider: "claude", effort: "low" }]);
});

test("with a transcription model saved, the dialog prefills it and shows no notice", async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/progress") return route.fulfill({ json: [] });
    if (path === "/api/bundles")
      return route.fulfill({ json: [{ bundle: "b", name: "216424", pdf: "b.pdf", loaded: false, surveys: [], job: null }] });
    if (path === "/api/transcription-models")
      return route.fulfill({ json: { configured: { provider: "codex", model: "gpt-x", effort: "high" }, models: [] } });
    return route.fulfill({ status: 404, json: { detail: `Unexpected request: ${path}` } });
  });
  await page.goto("/?collection=1");
  await bundleRows(page).getByRole("button", { name: "Transcribe", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Transcribe scans" });
  await expect(dialog.getByLabel("Model", { exact: true })).toHaveValue("gpt-x");
  await expect(dialog.getByLabel("Provider", { exact: true })).toHaveValue("codex");
  await expect(dialog.getByLabel("Effort", { exact: true })).toHaveValue("high");
  await expect(dialog.getByText("No transcription model is set.")).toHaveCount(0);
});
