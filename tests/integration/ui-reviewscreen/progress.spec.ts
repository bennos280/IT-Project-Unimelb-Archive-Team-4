import { test, expect, type Page } from "@playwright/test";

test.describe("Progress navigation and layout", () => {
  const survey = {
    id: "216417_1",
    title: "Test survey",
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
      await page.route("**/api/progress", (route) =>
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

      await page.goto("/");
      await expect(page.locator(".progress-meter")).toContainText(
        "0 / 3 reviewed · 0%",
      );
      await page.getByRole("button", { name: "216417", exact: true }).click();
      const firstRow = page
        .locator(".progress-table tbody tr")
        .filter({ has: page.getByRole("cell", { name: "Pg 1", exact: true }) });
      await expect(firstRow).toContainText("5 need checking");
      await firstRow.getByRole("link", { name: "Review", exact: true }).click();
      await expect(page.locator(".page-heading h2")).toContainText("216417/p0");
      await page
        .getByRole("combobox", { name: "Reviewer name", exact: true })
        .selectOption("Test reviewer");
      // Flagged fields must be reviewed individually before saving.
      for (const field of survey.pages[0].fields) {
        await page
          .getByRole("button", { name: `Edit ${field.label}`, exact: true })
          .click();
        await page
          .getByRole("button", { name: "Apply review", exact: true })
          .click();
      }
      expect(persisted).toBe(false);
      if (outcome !== "unsaved") {
        await page
          .getByRole("button", { name: "Save Page Transcript", exact: true })
          .click();
        if (outcome === "saved") {
          await expect(
            page.locator(".field-status").filter({ hasText: "Reviewed by:" }),
          ).toHaveCount(5);
        } else {
          await expect(page.locator(".save-help")).toHaveText(
            "Page changed in another tab.",
          );
        }
      }
      // Accept the browser's leave warning for deliberately discarded drafts.
      page.on("dialog", (dialog) => dialog.accept());
      await page.getByRole("link", { name: "Back to all bundles" }).click();
      const complete = outcome === "saved";
      expect(saveRequests).toBe(outcome === "unsaved" ? 0 : 1);
      for (const refresh of [false, true]) {
        if (refresh) await page.reload();
        await expect(page.locator(".progress-meter")).toContainText(
          complete ? "1 / 3 reviewed · 33%" : "0 / 3 reviewed · 0%",
        );
        await expect(
          page
            .locator(".progress-stats section")
            .filter({ hasText: /^Reviewed/ })
            .locator("strong"),
        ).toHaveText(complete ? "1" : "0");
        await expect(
          page
            .locator(".progress-stats section")
            .filter({ hasText: /^Ready to review/ })
            .locator("strong"),
        ).toHaveText(complete ? "2" : "3");
      }
      await page.getByRole("button", { name: "216417", exact: true }).click();
      await expect(firstRow.locator(".progress-badge")).toHaveText(
        complete ? "Reviewed" : "Ready to review",
      );
      await expect(firstRow).toContainText(
        complete ? "No flags" : "5 need checking",
      );
      await expect(
        firstRow.getByRole("link", {
          name: complete ? "View" : "Review",
          exact: true,
        }),
      ).toBeVisible();
    });
  }

  test("searches bundles and clears an empty result", async ({ page }) => {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: "All survey bundles" }),
    ).toBeVisible();

    await page.getByLabel("Search bundles").fill("216417");
    await expect(page.locator(".progress-table tbody tr")).toHaveCount(1);

    await page.getByLabel("Search bundles").fill("missing");
    await expect(
      page.getByText("No bundles match your filters."),
    ).toBeVisible();

    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.locator(".progress-table tbody tr")).toHaveCount(1);
  });

  test("disables pagination for one bundle and filters by status", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(
      page.getByRole("button", { name: "Next", exact: true }),
    ).toBeDisabled();

    await page.getByLabel("Status", { exact: true }).selectOption("Reviewed");
    await expect(
      page.getByText("No bundles match your filters."),
    ).toBeVisible();

    await page
      .getByLabel("Status", { exact: true })
      .selectOption("Ready to review");

    await expect(
      page.getByRole("button", { name: "216417", exact: true }),
    ).toBeVisible();
  });

  test("opens bundle pages with matching review targets", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "216417", exact: true }).click();

    await expect(
      page.getByRole("heading", { name: "Bundle Number · 216417" }),
    ).toBeVisible();

    const notesRow = page.locator(".progress-table tbody tr").filter({
      has: page.getByRole("cell", { name: "Pg 2", exact: true }),
    });

    await expect(
      notesRow.getByRole("link", { name: "Review", exact: true }),
    ).toHaveAttribute("href", "/?survey=216417_1&page=216417%2Fp1");

    await page.getByRole("button", { name: "Back to all bundles" }).click();

    await expect(
      page.getByRole("heading", { name: "All survey bundles" }),
    ).toBeVisible();
  });

  for (const [label, pageId] of [
    ["Pg 1", "216417/p0"],
    ["Pg 2", "216417/p1"],
    ["Pg 3", "216417/p2"],
  ]) {
    test(`${label} opens its matching US7 page`, async ({ page }) => {
      await page.goto("/");
      await page.getByRole("button", { name: "216417", exact: true }).click();

      const row = page.locator(".progress-table tbody tr").filter({
        has: page.getByRole("cell", { name: label, exact: true }),
      });

      await expect(
        row.getByRole("link", { name: label, exact: true }),
      ).toHaveCount(0);

      await row.getByRole("link", { name: "Review", exact: true }).click();

      await expect(page.locator(".page-heading h2")).toContainText(pageId);
      await expect(
        page.getByRole("heading", { name: "Transcript Review" }),
      ).toBeVisible();
    });
  }

  for (const width of [936, 640, 375]) {
    test(`page table keeps actions visible at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await page.getByRole("button", { name: "216417", exact: true }).click();

      await expect(
        page.getByRole("columnheader", { name: "Flags", exact: true }),
      ).toBeVisible();

      await expect(
        page.getByRole("columnheader", { name: "Survey ID", exact: true }),
      ).toHaveCount(0);

      await expect(
        page.getByRole("cell", { name: "5 need checking", exact: true }),
      ).toBeVisible();

      const links = page.getByRole("link", { name: "Review", exact: true });
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
          .locator(".progress-table-wrap")
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
    await page.goto("/");
  }

  async function openBundle(page: Page) {
    await page.getByRole("button", { name: "216424", exact: true }).click();
  }

  test("untouched bundle prompts Transcribe and shows no reviewable pages", async ({
    page,
  }) => {
    await mock(page);
    await expect(
      page.getByText("No reviewable pages", { exact: true }),
    ).toBeVisible();
    await openBundle(page);
    await expect(
      page.getByText(
        "This bundle has not been processed yet. Press Transcribe to get started.",
      ),
    ).toBeVisible();
    await expect(
      page
        .locator(".progress-filters")
        .getByRole("button", { name: "Transcribe", exact: true }),
    ).toBeEnabled();
    await expect(
      page.getByRole("button", { name: "Complete transcription", exact: true }),
    ).toHaveCount(0);
  });

  test("partial bundle shows model and completion action without review access", async ({
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
    await expect(page.locator(".progress-incomplete-warning")).toContainText(
      "has not finished processing",
    );
    await expect(
      page
        .locator(".progress-filters")
        .getByRole("button", { name: "Complete transcription" }),
    ).toBeEnabled();
    await expect(
      page.getByRole("cell", { name: "partial-model", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Review", exact: true }),
    ).toHaveCount(0);
  });

  for (const status of ["waiting", "running"]) {
    test(`${status} job disables duplicate transcription`, async ({ page }) => {
      await mock(page, { status });
      await openBundle(page);
      await expect(page.locator(".progress-filters button")).toBeDisabled();
      await expect(page.locator(".progress-incomplete-warning")).toContainText(
        "has not finished processing",
      );
    });
  }

  test("loaded bundle shows model or dash and hides incomplete notice", async ({
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
    await expect(page.locator(".progress-incomplete-warning")).toHaveCount(0);
    await expect(page.locator(".progress-filters button")).toHaveCount(0);
  });

  test("pagination changes rows and searching resets to first page", async ({
    page,
  }) => {
    await mock(page, { loaded: true, count: 11 });
    await openBundle(page);
    await expect(page.locator(".progress-table tbody tr")).toHaveCount(9);
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByText("Showing 10–11 of 11 pages")).toBeVisible();
    await page.getByLabel("Search pages").fill("Pg 1");
    await expect(page.getByText("Showing 1–3 of 3 pages")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Previous", exact: true }),
    ).toBeDisabled();
  });

  test("failed progress request can be retried", async ({ page }) => {
    await mock(page, { loaded: true });
    let failed = true;
    await page.route("**/api/progress", (route) =>
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
      page.getByRole("button", { name: "216424", exact: true }),
    ).toBeVisible();
  });

  test("polling updates review counts without a reload", async ({ page }) => {
    await mock(page, { loaded: true });
    await expect(
      page.getByText("0 / 2 reviewed · 0%", { exact: true }),
    ).toBeVisible();
    await page.route("**/api/progress", (route) =>
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
        ? [
            {
              id: "reviewed-page",
              label: "Pg 1",
              category: "Main page",
              status: "Reviewed",
              flagCount: 0,
              surveyId: "survey-1",
              reviewPageId: "reviewed-page",
            },
          ]
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
    await page.goto("/");
    return page.getByRole("row").filter({
      has: page.getByRole("button", { name: "test-bundle", exact: true }),
    });
  }

  test("unassigned pages do not prevent 100% review progress", async ({
    page,
  }) => {
    const row = await showBundle(page, true);
    await expect(row.locator("td").nth(1)).toHaveText("2");
    await expect(row.locator(".progress-meter")).toContainText(
      "1 / 1 reviewed · 100%",
    );
    await expect(row.locator(".progress-meter")).toContainText(
      "1 pages not in a survey",
    );
    const progress = row.getByRole("progressbar");
    await expect(progress).toHaveAttribute("value", "1");
    await expect(progress).toHaveAttribute("max", "1");
  });

  test("a bundle with only unassigned pages has no review percentage", async ({
    page,
  }) => {
    const row = await showBundle(page, false);
    await expect(row.locator("td").nth(1)).toHaveText("1");
    await expect(row.locator(".progress-meter")).toContainText(
      "No reviewable pages",
    );
    await expect(row.locator(".progress-meter")).toContainText(
      "1 pages not in a survey",
    );
    await expect(row.locator(".progress-meter")).not.toContainText("%");
    await expect(row.getByRole("progressbar")).toHaveCount(0);
  });
});
