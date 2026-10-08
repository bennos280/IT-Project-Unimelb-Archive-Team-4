import { test, expect } from "@playwright/test";

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

test("searches bundles and clears an empty result", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "All survey bundles" }),
  ).toBeVisible();

  await page.getByLabel("Search bundles").fill("216417");
  await expect(page.locator(".progress-table tbody tr")).toHaveCount(1);

  await page.getByLabel("Search bundles").fill("missing");
  await expect(page.getByText("No bundles match your filters.")).toBeVisible();

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
  await expect(page.getByText("No bundles match your filters.")).toBeVisible();

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

test("Import opens its screen and Export opens its dialog", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Import", exact: true }).click();

  await expect(
    page.getByRole("heading", { name: "Import survey bundles" }),
  ).toBeVisible();

  await page.goto("/");
  await page.getByRole("button", { name: "Export", exact: true }).click();

  await expect(
    page.getByRole("dialog", { name: "Export", exact: true }),
  ).toBeVisible();

  await expect(
    page.getByRole("button", { name: "Export JSON", exact: true }),
  ).toBeEnabled();
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
        .evaluate((element) => element.scrollWidth <= element.clientWidth + 1),
    ).toBe(true);
  });
}
