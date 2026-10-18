import { test, expect, type Page } from "@playwright/test";

// Every API call is intercepted: no requests reach the real backend or database.
// The bundle's id (pdf-216417) differs from its name (216417), as for a PDF inside a numbered folder.
const pages = ["main", "notes"].map((type, index) => ({
  id: `216417/p${index}`,
  type,
  imageUrl: "/test-scan.svg",
  fields: [{ id: "address", label: "Address", group: "Address", value: "Sample value" }],
  flags: [],
}));

// failFirstBundles fails only the first /bundles request, which the review screen makes before the dashboard does.
async function mockApi(page: Page, { failFirstBundles = false } = {}) {
  let bundleRequests = 0;
  await page.route("**/test-scan.svg", (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"/>' }),
  );
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/progress")
      return route.fulfill({
        json: [{
          id: "pdf-216417",
          name: "216417",
          pages: pages.map((p, i) => ({
            id: p.id, label: `Pg ${i + 1}`, category: p.type, status: "Ready to review", flagCount: 0,
            surveyId: "216417_1", reviewPageId: p.id,
          })),
        }],
      });
    if (path === "/api/bundles")
      return failFirstBundles && bundleRequests++ === 0
        ? route.fulfill({ status: 500, json: { detail: "Bundles unavailable" } })
        : route.fulfill({ json: [{ pdf: "216417/pdf-216417.pdf", bundle: "pdf-216417", name: "216417", loaded: true, surveys: ["216417_1"], job: null }] });
    if (path === "/api/survey/216417_1") return route.fulfill({ json: { id: "216417_1", bundleId: "pdf-216417", title: "Test survey", pages } });
    if (path === "/api/reviews/216417_1") return route.fulfill({ json: { reviews: {}, revisions: {} } });
    if (path === "/api/reviewers") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
}

const trail = (page: Page) => page.getByRole("navigation", { name: "Breadcrumb" });
// Separators are presentational, so only the crumbs are list items in the accessibility tree.
const crumbs = (page: Page) => trail(page).locator('[data-slot="breadcrumb-item"]');
const current = (page: Page) => trail(page).locator('[aria-current="page"]');
const bundleLink = (page: Page) => page.getByRole("link", { name: "216417", exact: true });
const allBundles = (page: Page) => trail(page).getByRole("link", { name: "All bundles" });
const appName = (page: Page) => page.getByRole("link", { name: "Wilfred Prest Survey" });

test("the dashboard overview shows All bundles as the current crumb", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(crumbs(page)).toHaveText(["All bundles"]);
  await expect(current(page)).toHaveText("All bundles");
  await expect(appName(page)).toHaveAttribute("href", "/");
  await expect(page.locator("h1")).toHaveText("All survey bundles");
});

test("a bundle's pages show All bundles > Bundle, and All bundles returns in-app with Back and Forward intact", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await bundleLink(page).click();
  await expect(page).toHaveURL("/?bundle=216417");
  await expect(crumbs(page)).toHaveText(["All bundles", "Bundle 216417"]);
  await expect(current(page)).toHaveText("Bundle 216417");
  await expect(page.locator("h1")).toHaveText("Bundle Number · 216417");
  await expect(allBundles(page)).toHaveAttribute("href", "/");
  await expect(page.getByRole("button", { name: "Back to all bundles" })).toHaveCount(0);

  // The click is handled in the page: the document is not reloaded.
  await page.evaluate(() => { (window as unknown as { kept: boolean }).kept = true; });
  await allBundles(page).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "All survey bundles" })).toBeVisible();
  await expect(current(page)).toHaveText("All bundles");
  expect(await page.evaluate(() => (window as unknown as { kept?: boolean }).kept)).toBe(true);

  await page.goBack();
  await expect(page).toHaveURL("/?bundle=216417");
  await expect(page.getByRole("heading", { name: "Bundle Number · 216417" })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("heading", { name: "All survey bundles" })).toBeVisible();
});

test("a Ctrl or middle click on All bundles opens the overview in a new tab and leaves this one on the bundle", async ({ page, context }) => {
  await mockApi(page);
  await page.goto("/?bundle=216417");
  for (const click of [{ modifiers: ["Control" as const] }, { button: "middle" as const }]) {
    const [tab] = await Promise.all([context.waitForEvent("page"), allBundles(page).click(click)]);
    await expect(tab).toHaveURL(/\/$/);
    await expect(page).toHaveURL("/?bundle=216417");
    await expect(page.getByRole("heading", { name: "Bundle Number · 216417" })).toBeVisible();
    await tab.close();
  }
});

test("the review screen shows All bundles > Bundle > Survey, and the bundle crumb opens that bundle's pages", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?survey=216417_1&page=216417%2Fp0");
  await expect(crumbs(page)).toHaveText(["All bundles", "Bundle 216417", "Survey 216417_1"]);
  await expect(current(page)).toHaveText("Survey 216417_1");
  await expect(appName(page)).toHaveAttribute("href", "/");
  await expect(allBundles(page)).toHaveAttribute("href", "/");
  await expect(trail(page).getByRole("link", { name: "Bundle 216417" })).toHaveAttribute("href", "/?bundle=216417");
  await expect(page.locator("h1")).toHaveCount(1);

  await trail(page).getByRole("link", { name: "Bundle 216417" }).click();
  await expect(page).toHaveURL("/?bundle=216417");
  await expect(page.getByRole("heading", { name: "Bundle Number · 216417" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Review Pg 1", exact: true })).toBeVisible();
});

test("the review screen's All bundles crumb opens the overview", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?survey=216417_1");
  await allBundles(page).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "All survey bundles" })).toBeVisible();
});

test("the review bundle crumb falls back to the bundle id when /bundles fails, and the dashboard accepts it", async ({ page }) => {
  await mockApi(page, { failFirstBundles: true });
  await page.goto("/?survey=216417_1");
  const crumb = trail(page).getByRole("link", { name: "Bundle pdf-216417" });
  await expect(crumb).toHaveAttribute("href", "/?bundle=pdf-216417");
  await expect(current(page)).toHaveText("Survey 216417_1");
  await crumb.click();
  await expect(page.getByRole("heading", { name: "Bundle Number · 216417" })).toBeVisible();
});

test("the import screen shows All bundles > Import and one h1", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?view=import");
  await expect(crumbs(page)).toHaveText(["All bundles", "Import"]);
  await expect(current(page)).toHaveText("Import");
  await expect(page.locator("h1")).toHaveText("Import survey bundles");
  await expect(appName(page)).toHaveAttribute("href", "/");
  await allBundles(page).click();
  await expect(page.getByRole("heading", { name: "All survey bundles" })).toBeVisible();
});

test("the settings screen shows All bundles > Settings and one h1", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?view=settings");
  await expect(crumbs(page)).toHaveText(["All bundles", "Settings"]);
  await expect(current(page)).toHaveText("Settings");
  await expect(page.locator("h1")).toHaveText("Settings");
  await appName(page).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "All survey bundles" })).toBeVisible();
});

test("Export, Import and Settings work from the header", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  const header = page.getByRole("banner");
  await header.getByRole("button", { name: "Export", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Export" })).toBeVisible();
  await page.keyboard.press("Escape");
  await header.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Import survey bundles" })).toBeVisible();
  await page.goBack();
  await header.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();
});

test("on a phone no screen scrolls sideways and the header actions wrap under the breadcrumb", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 375, height: 800 });
  for (const url of ["/", "/?bundle=216417", "/?survey=216417_1", "/?view=import", "/?view=settings"]) {
    await page.goto(url);
    await expect(current(page)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), url).toBe(true);
  }
  await page.goto("/?bundle=216417");
  await expect(current(page)).toHaveText("Bundle 216417");
  const trailBox = (await trail(page).boundingBox())!;
  const exportBox = (await page.getByRole("banner").getByRole("button", { name: "Export", exact: true }).boundingBox())!;
  expect(exportBox.y).toBeGreaterThanOrEqual(trailBox.y + trailBox.height);
});
