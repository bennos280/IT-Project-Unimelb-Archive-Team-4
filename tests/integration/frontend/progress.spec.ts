import { test, expect, type Locator, type Page } from "@playwright/test";
import { serveItems, type MockItem, type MockPage } from "./items-mock";

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
    recordName: "survey", grouped: true,
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

  // The review pages of item 216417, as the server lists them; status is what each is at.
  const listed = (status = (_i: number) => "Ready to review", flags = (i: number) => survey.pages[i].flags.length): MockPage[] =>
    survey.pages.map((p, i) => ({
      id: p.id, label: `Pg ${i + 1}`, category: p.type, status: status(i), flagCount: flags(i),
      surveyId: survey.id, reviewPageId: p.id,
    }));
  const items = (pages = listed()): MockItem[] => [{ bundle: "216417", name: "216417", pages }];

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
      const served = serveItems(items(), route.request());
      if (served) return route.fulfill(served);

      if (path === "/api/collections/1")
        return route.fulfill({ json: { id: 1, name: "Wilfred Prest Survey", recordKey: "number_of_dwelling", recordName: "survey", grouped: true, archiveSeries: 499420 } });
      if (path === "/api/survey/216417_1") {
        return route.fulfill({ json: survey });
      }

      if (path === "/api/reviews/216417_1") {
        return route.fulfill({
          json: { reviews: {}, revisions: {} },
        });
      }

      if (path === "/api/reviewers") {
        return route.fulfill({ json: [{ id: 1, name: "Ben" }] });
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
      await page.route("**/api/collections/1/items**", (route) =>
        route.fulfill(
          serveItems(
            () => items(listed((i) => (persisted && i === 0 ? "Reviewed" : "Ready to review"), (i) => (persisted && i === 0 ? 0 : survey.pages[i].flags.length))),
            route.request(),
          )!,
        ),
      );

      await page.goto("/?series=1");
      const bundleRow = bundleRows(page).filter({
        has: page.getByRole("link", { name: "216417", exact: true }),
      });
      await expect(meter(bundleRow)).toContainText("0 / 3 reviewed · 0%");
      await page.getByRole("link", { name: "216417", exact: true }).click();
      const firstRow = pageRow(page, "Pg 1");
      await expect(firstRow).toContainText("5 need checking");
      await firstRow.getByRole("link", { name: "Review Pg 1", exact: true }).click();
      await expect(page.getByRole("heading", { name: "216417/p0 ·" })).toBeVisible();
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
      await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Items", exact: true }).click();
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
      await page.goto("/?series=1&item=216417");
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
    await page.goto("/?series=1");

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
    await page.goto("/?series=1");

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
    await page.goto("/?series=1&item=216417");

    await expect(
      page.getByRole("heading", { name: "Item 216417" }),
    ).toBeVisible();

    const notesRow = pageRow(page, "Pg 2");

    await expect(
      notesRow.getByRole("link", { name: "Review Pg 2", exact: true }),
    ).toHaveAttribute("href", "/?survey=216417_1&page=216417%2Fp1");

    await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Items", exact: true }).click();

    await expect(
      page.getByRole("heading", { name: "All items" }),
    ).toBeVisible();
  });

  for (const [label, pageId] of [
    ["Pg 1", "216417/p0"],
    ["Pg 2", "216417/p1"],
    ["Pg 3", "216417/p2"],
  ]) {
    test(`${label} opens its matching US7 page`, async ({ page }) => {
      await page.goto("/?series=1&item=216417");

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
      await page.goto("/?series=1&item=216417");

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
    const items: MockItem[] = [{
      bundle: "b", name: "216424", pdf: "b.pdf", loaded, job,
      pages: loaded ? Array.from({ length: options.count ?? 2 }, (_, i) =>
        ({ ...readyPage(i + 1) })) : [],
    }];
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      const served = serveItems(items, route.request());
      if (served) return route.fulfill(served);
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
    await page.goto("/?series=1");
  }

  async function openBundle(page: Page) {
    await page.getByRole("link", { name: "216424", exact: true }).click();
  }

  test("a series whose pages don't group offers no grouping status", async ({ page }) => {
    await mock(page, { loaded: true });
    await page.route("**/api/collections/1", (route) =>
      route.fulfill({ json: { id: 1, name: "Letters", recordName: "letter", grouped: false } }));
    await page.reload();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Letters");
    await expect(page.getByLabel("Status").locator("option", { hasText: "Not in a" })).toHaveCount(0);
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
    await expect(page).toHaveURL(/\/\?series=1&item=216424&page=2$/);
    await page.reload();
    await expect(page.getByText("Showing 10–11 of 11 pages")).toBeVisible();
    await page.getByLabel("Status").selectOption("Ready to review");
    await expect(page).toHaveURL(/\/\?series=1&item=216424&status=Ready\+to\+review$/);
    await page.goBack();
    await expect(page.getByText("Showing 10–11 of 11 pages")).toBeVisible();
    await page.goBack();
    await expect(page.getByText("Showing 1–9 of 11 pages")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/\?series=1$/);
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
    await expect(page).toHaveURL(/\/\?series=1$/);
    await row.getByRole("cell").nth(1).click();
    await expect(page.getByRole("heading", { name: "Item 216424" })).toBeVisible();
    await expect(page).toHaveURL(/\/\?series=1&item=216424$/);
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
    await expect(page).toHaveURL(/\/\?series=1$/);
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
    await expect(link).toHaveAttribute("href", "/?series=1&item=216424");
    const opened = page.context().waitForEvent("page");
    await link.click({ modifiers: ["Control"] });
    const tab = await opened;
    expect(new URL(tab.url()).search).toBe("?series=1&item=216424");
    await tab.close();
    await expect(page).toHaveURL(/\/\?series=1$/);
    await expect(page.getByRole("heading", { name: "All items" })).toBeVisible();
    await link.focus();
    await expect(link).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Item 216424" })).toBeVisible();
    await expect(page).toHaveURL(/\/\?series=1&item=216424$/);
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
    await page.route(/\/api\/collections\/1\/items(\?.*)?$/, (route) =>
      failed
        ? route.fulfill({ status: 500, json: { detail: "Temporary failure" } })
        : route.fulfill(serveItems([{ bundle: "b", name: "216424", pages: [readyPage(1)] }], route.request())!),
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
    await page.route(/\/api\/collections\/1\/items(\?.*)?$/, (route) =>
      route.fulfill(
        serveItems([{ bundle: "b", name: "216424", pages: [{ ...readyPage(1), status: "Reviewed" }, readyPage(2)] }], route.request())!,
      ),
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
    await page.route(/\/api\/collections\/1\/items(\?.*)?$/, async (route) => {
      calls++;
      await held;
      await route.fulfill(serveItems([{ bundle: "b", name: "216424", pages: [readyPage(1), readyPage(2)] }], route.request())!);
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
    const served = serveItems([{bundle:'b',name:'b',pages:[{id:'b/p4',label:'Pg 4',category:'Coded',status:'Awaiting transcription',flagCount:0,surveyId:'s1',reviewPageId:'b/p4'}]}], route.request());
    if (served) return route.fulfill(served);
    return route.fulfill({status:404,json:{detail:'Unexpected test request'}});
  });
  await page.goto("/?series=1&item=b");
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
      const served = serveItems([{ bundle: "test-bundle", name: "test-bundle", pages }], route.request());
      if (served) return route.fulfill(served);
      if (path === "/api/collections/1") {
        return route.fulfill({ json: { id: 1, name: "Wilfred Prest Survey", recordName: "survey", grouped: true } });
      }
      return route.fulfill({
        status: 404,
        json: { detail: `Unexpected request: ${path}` },
      });
    });
    await page.goto("/?series=1");
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
    // No item has more than one page, so there is no Total pages column: the progress is the third cell.
    await expect(page.getByRole("columnheader", { name: "Total pages" })).toHaveCount(0);
    const progress = row.getByRole("cell").nth(2);
    await expect(progress).toContainText("No reviewable pages");
    await expect(progress).toContainText("1 page not in a survey");
    await expect(progress).not.toContainText("%");
    await expect(row.getByRole("progressbar")).toHaveCount(0);
  });
});

test("with no transcription model saved, the dialog prefills nothing, links to Settings and still starts a run with the model picked there", async ({ page }) => {
  const started: unknown[] = [];
  await page.route("**/api/**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const served = serveItems([{ bundle: "b", name: "216424", pdf: "b.pdf", loaded: false }], request);
    if (served) return route.fulfill(served);
    if (path === "/api/transcription-models") return route.fulfill({ json: { configured: null, models: [] } });
    if (path === "/api/jobs" && request.method() === "POST") {
      started.push(request.postDataJSON());
      return route.fulfill({ status: 202, json: { id: 1, status: "waiting", step: null, donePages: 0, totalPages: 0, error: null } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected request: ${path}` } });
  });
  await page.goto("/?series=1");
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
    const served = serveItems([{ bundle: "b", name: "216424", pdf: "b.pdf", loaded: false }], route.request());
    if (served) return route.fulfill(served);
    if (path === "/api/transcription-models")
      return route.fulfill({ json: { configured: { provider: "codex", model: "gpt-x", effort: "high" }, models: [] } });
    return route.fulfill({ status: 404, json: { detail: `Unexpected request: ${path}` } });
  });
  await page.goto("/?series=1");
  await bundleRows(page).getByRole("button", { name: "Transcribe", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Transcribe scans" });
  await expect(dialog.getByLabel("Model", { exact: true })).toHaveValue("gpt-x");
  await expect(dialog.getByLabel("Provider", { exact: true })).toHaveValue("codex");
  await expect(dialog.getByLabel("Effort", { exact: true })).toHaveValue("high");
  await expect(dialog.getByText("No transcription model is set.")).toHaveCount(0);
});

test.describe("The server pages, searches and filters the overview", () => {
  const SERIES = { id: 1, name: "Wilfred Prest Survey", recordName: "survey", grouped: true };
  const params = (url: URL) => Object.fromEntries(url.searchParams);
  // The different requests made, in order; the dev build's remount asks for the first one twice.
  const distinct = (asked: URL[]) => [...new Set(asked.map((url) => url.search))].map((query) => Object.fromEntries(new URLSearchParams(query)));
  const onePage: MockPage = { id: "p1", label: "Pg 1", category: "Main page", status: "Ready to review", flagCount: 0, surveyId: "s", reviewPageId: "p1" };

  test("paging, searching and filtering each ask the server, which answers one page at a time", async ({ page }) => {
    const asked: URL[] = [];
    const items: MockItem[] = Array.from({ length: 20 }, (_, i) => ({ bundle: `b${i}`, name: String(216410 + i), pages: [onePage] }));
    await page.route("**/api/**", (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/collections/1") return route.fulfill({ json: SERIES });
      if (url.pathname === "/api/collections/1/items") asked.push(url);
      const served = serveItems(items, route.request());
      return served ? route.fulfill(served) : route.fulfill({ status: 404, json: { detail: `Unexpected request: ${url.pathname}` } });
    });
    await page.goto("/?series=1");
    await expect(page.getByText("Showing 1–9 of 20 items")).toBeVisible();
    await expect(bundleRows(page)).toHaveCount(9);
    expect(distinct(asked)).toEqual([{ page: "0", size: "9" }]);
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect.poll(() => params(asked[asked.length - 1])).toEqual({ page: "1", size: "9" });
    await expect(page.getByText("Showing 10–18 of 20 items")).toBeVisible();
    await expect(page.getByRole("link", { name: "216419", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "216410", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByText("Showing 19–20 of 20 items")).toBeVisible();
    await expect(page.getByRole("button", { name: "Next", exact: true })).toBeDisabled();
    // A search starts again from the first page, and is sent once typing pauses.
    await page.getByLabel("Search items").pressSequentially("216427");
    await expect.poll(() => params(asked[asked.length - 1])).toEqual({ page: "0", size: "9", search: "216427" });
    await expect(bundleRows(page)).toHaveCount(1);
    await page.getByLabel("Status", { exact: true }).selectOption("Reviewed");
    await expect.poll(() => params(asked[asked.length - 1])).toEqual({ page: "0", size: "9", search: "216427", status: "Reviewed" });
    await expect(page.getByText("No items match your filters.")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect.poll(() => params(asked[asked.length - 1])).toEqual({ page: "0", size: "9" });
    await expect(bundleRows(page)).toHaveCount(9);
  });

  test("an item's page asks only for that item, and for its partial results when it has a job and isn't loaded", async ({ page }) => {
    const asked: string[] = [];
    const job = { id: 7, status: "running", step: "transcribe", donePages: 1, totalPages: 2, error: null };
    await page.route("**/api/**", (route) => {
      const url = new URL(route.request().url());
      asked.push(url.pathname);
      if (url.pathname === "/api/collections/1") return route.fulfill({ json: SERIES });
      if (url.pathname === "/api/jobs/7/transcripts")
        return route.fulfill({ json: { pages: [{ id: "b_00001", category: "main", status: "Transcribed — not grouped", data: { model: "partial-model" } }] } });
      const served = serveItems([{ bundle: "b", name: "216424", pdf: "b.pdf", loaded: false, job }, { bundle: "c", name: "216425" }], route.request());
      return served ? route.fulfill(served) : route.fulfill({ status: 404, json: { detail: `Unexpected request: ${url.pathname}` } });
    });
    await page.goto("/?series=1&item=216424");
    await expect(page.getByRole("cell", { name: "partial-model", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Item 216424" })).toBeVisible();
    expect(new Set(asked)).toEqual(new Set([
      "/api/collections/1", "/api/collections", "/api/collections/1/items/216424", "/api/jobs/7/transcripts",
      "/api/transcription-models", "/api/connections", "/api/reviewers", // the last, once on load, checks who is working
    ]));
  });

  test("an item that isn't there says so", async ({ page }) => {
    await page.route("**/api/**", (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/collections/1") return route.fulfill({ json: SERIES });
      const served = serveItems([{ bundle: "b", name: "216424" }], route.request());
      return served ? route.fulfill(served) : route.fulfill({ status: 404, json: { detail: `Unexpected request: ${url.pathname}` } });
    });
    await page.goto("/?series=1&item=nobody");
    await expect(page.getByRole("alert")).toContainText("No such item.");
    await expect(bundleRows(page)).toHaveCount(0);
  });
});

