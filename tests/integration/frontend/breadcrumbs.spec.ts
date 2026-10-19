import { test, expect, type Page } from "@playwright/test";
import { serveItems } from "./items-mock";

// The top bar on every screen: the app's name (home), the series switcher and the trail below it, and Settings and Tasks; and a
// series' own header with its actions and its Items | Setup tabs. Every API call is intercepted: no requests reach the real backend.
// The bundle's id (pdf-216417) differs from its name (216417), as for a PDF inside a numbered folder.
const pages = ["main", "notes"].map((type, index) => ({
  id: `216417/p${index}`,
  type,
  imageUrl: "/test-scan.svg",
  fields: [{ id: "address", label: "Address", group: "Address", value: "Sample value" }],
  flags: [],
}));
const COLLECTION = { id: 1, name: "Wilfred Prest Survey", recordKey: "number_of_dwelling", recordName: "survey", grouped: true, archiveSeries: 499420,
  archiveIdentifier: "UMA-SR-000000842", pageTypes: 3, templates: 3, pages: 2, unknownPages: 0, bundles: 1, running: 0 };
const DIARIES = { ...COLLECTION, id: 2, name: "Strathfieldsaye Estate Diaries", archiveSeries: 524173, archiveIdentifier: "UMA-SR-000001769" };

// noItemInfo leaves the item's name and archive title out of the survey, as an older server would. The item holds a second
// survey (one more page), so it isn't one record; whole makes the survey say it is its whole item.
async function mockApi(page: Page, { noItemInfo = false, archive = false, whole = false } = {}) {
  const archiveItem = archive ? { identifier: "UMA-ITE-1973000200006", title: "Brunswick 02 - Part 3" } : null;
  await page.route("**/test-scan.svg", (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"/>' }),
  );
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const served = serveItems([{
      bundle: "pdf-216417", name: "216417", pdf: "216417/pdf-216417.pdf", archive: archiveItem,
      pages: [...pages, { id: "216417/p2", type: "main" }].map((p, i) => ({
        id: p.id, label: `Pg ${i + 1}`, category: p.type, status: "Ready to review", flagCount: 0,
        surveyId: i < pages.length ? "216417_1" : "216417_2", reviewPageId: p.id,
      })),
    }], route.request());
    if (served) return route.fulfill(served);
    if (path === "/api/survey/216417_1")
      return route.fulfill({ json: {
        id: "216417_1", bundleId: "pdf-216417", collectionId: 1, title: "Wilfred Prest Survey", recordName: "survey", grouped: true, pages,
        wholeItem: whole,
        ...(noItemInfo ? {} : { item: { name: "216417", archive: archiveItem } }),
      } });
    if (path === "/api/reviews/216417_1") return route.fulfill({ json: { reviews: {}, revisions: {} } });
    if (path === "/api/reviewers") return route.fulfill({ json: [{ id: 1, name: "Ben" }] });
    if (path === "/api/collections/1") return route.fulfill({ json: COLLECTION });
    if (path === "/api/collections/2") return route.fulfill({ json: DIARIES });
    if (path === "/api/collections") return route.fulfill({ json: [COLLECTION, DIARIES] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
}

const trail = (page: Page) => page.getByRole("navigation", { name: "Breadcrumb" });
// The crumbs after the series menu; separators are presentational, so only crumbs are list items.
const crumbs = (page: Page) => trail(page).locator('[data-slot="breadcrumb-item"]:not(:has(button))');
const current = (page: Page) => trail(page).locator('[aria-current="page"]');
const switcher = (page: Page) => page.getByRole("banner").getByRole("button", { name: /^Series: / });
const menuItems = (page: Page) => page.getByRole("menu").getByRole("menuitem");
const itemsCrumb = (page: Page) => trail(page).getByRole("link", { name: "Items", exact: true });
const bundleLink = (page: Page) => page.getByRole("link", { name: "216417", exact: true });
const appName = (page: Page) => page.getByRole("link", { name: "PrestCribe" });
const tabs = (page: Page) => page.getByRole("navigation", { name: "Series" }).getByRole("link");

test("home is the app's name alone, which links home, with Settings and Tasks", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(trail(page)).toHaveCount(0);
  await expect(appName(page)).toHaveAttribute("href", "/");
  await expect(page.getByRole("banner").getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/?view=settings");
  await expect(page.getByRole("banner").getByRole("link", { name: "Tasks" })).toHaveAttribute("href", "/?view=tasks");
  await expect(page.locator("h1")).toHaveText("Series");
});

test("a series' items name it in the series menu and its heading, with its Items and Setup tabs", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?collection=1");
  await expect(switcher(page)).toHaveAccessibleName("Series: Wilfred Prest Survey");
  await switcher(page).click();
  await expect(menuItems(page)).toHaveText(["Items", "Setup", "Strathfieldsaye Estate Diaries", "All series"]);
  await page.keyboard.press("Escape");
  await expect(crumbs(page)).toHaveCount(0);
  await expect(page.locator("h1")).toHaveText("Wilfred Prest Survey");
  await expect(page.getByRole("link", { name: "UMA-SR-000000842" })).toHaveAttribute("href", "https://archives.library.unimelb.edu.au/nodes/view/499420");
  await expect(tabs(page)).toHaveText(["Items", "Setup"]);
  await expect(tabs(page).first()).toHaveAttribute("aria-current", "page");
  await expect(tabs(page).last()).toHaveAttribute("href", "/?collection=1&view=setup");
  await expect(page.getByRole("heading", { name: "All items", level: 2 })).toBeVisible();
});

test("the series menu opens another series on the same tab, or all of them, and its keys move without leaving", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?collection=1&view=setup");
  await switcher(page).click();
  await page.getByRole("menuitem", { name: "Strathfieldsaye Estate Diaries" }).click();
  await expect(page).toHaveURL("/?collection=2&view=setup");
  await page.goto("/?collection=1");
  await switcher(page).focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await expect(page).toHaveURL("/?collection=1"); // moving through it goes nowhere
  await page.getByRole("menuitem", { name: "All series" }).click();
  await expect(page).toHaveURL("/");
});

test("from an item, the series menu still leads to its Items and Setup", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?collection=1&bundle=216417");
  await switcher(page).click();
  await expect(page.getByRole("menuitem", { name: "Items" })).toHaveAttribute("href", "/?collection=1");
  await expect(page.getByRole("menuitem", { name: "Setup" })).toHaveAttribute("href", "/?collection=1&view=setup");
});

test("an item's pages show Items > Item, and Items returns in-app with Back and Forward intact", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?collection=1");
  await bundleLink(page).click();
  await expect(page).toHaveURL("/?collection=1&bundle=216417");
  await expect(crumbs(page)).toHaveText(["Items", "Item 216417"]);
  await expect(current(page)).toHaveText("Item 216417");
  await expect(page.locator("h1")).toHaveText("Item 216417");
  await expect(itemsCrumb(page)).toHaveAttribute("href", "/?collection=1");
  await expect(page.getByRole("button", { name: "Back to all bundles" })).toHaveCount(0);

  // The click is handled in the page: the document is not reloaded.
  await page.evaluate(() => { (window as unknown as { kept: boolean }).kept = true; });
  await itemsCrumb(page).click();
  await expect(page).toHaveURL(/\/\?collection=1$/);
  await expect(page.getByRole("heading", { name: "All items" })).toBeVisible();
  await expect(crumbs(page)).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { kept?: boolean }).kept)).toBe(true);

  await page.goBack();
  await expect(page).toHaveURL("/?collection=1&bundle=216417");
  await expect(page.getByRole("heading", { name: "Item 216417" })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("heading", { name: "All items" })).toBeVisible();
});

test("a Ctrl or middle click on Items opens the series' items in a new tab and leaves this one on the item", async ({ page, context }) => {
  await mockApi(page);
  await page.goto("/?collection=1&bundle=216417");
  for (const click of [{ modifiers: ["Control" as const] }, { button: "middle" as const }]) {
    const [tab] = await Promise.all([context.waitForEvent("page"), itemsCrumb(page).click(click)]);
    await expect(tab).toHaveURL(/\/\?collection=1$/);
    await expect(page).toHaveURL("/?collection=1&bundle=216417");
    await expect(page.getByRole("heading", { name: "Item 216417" })).toBeVisible();
    await tab.close();
  }
});

test("the review screen shows the series, then Items > Item > Survey, and the item crumb opens that item's pages", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?survey=216417_1&page=216417%2Fp0");
  await expect(switcher(page)).toHaveAccessibleName("Series: Wilfred Prest Survey");
  await expect(crumbs(page)).toHaveText(["Items", "Item 216417", "Survey 216417_1"]);
  await expect(current(page)).toHaveText("Survey 216417_1");
  await expect(appName(page)).toHaveAttribute("href", "/");
  await expect(itemsCrumb(page)).toHaveAttribute("href", "/?collection=1");
  await expect(trail(page).getByRole("link", { name: "Item 216417" })).toHaveAttribute("href", "/?collection=1&bundle=216417");
  await expect(page.locator("h1")).toHaveCount(1);

  await trail(page).getByRole("link", { name: "Item 216417" }).click();
  await expect(page).toHaveURL("/?collection=1&bundle=216417");
  await expect(page.getByRole("heading", { name: "Item 216417" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Review Survey 216417_1", exact: true })).toBeVisible();
});

test("a record that is its whole item is named by the item, with no step between them", async ({ page }) => {
  await mockApi(page, { whole: true });
  await page.goto("/?survey=216417_1");
  await expect(crumbs(page)).toHaveText(["Items", "Item 216417"]);
  await expect(current(page)).toHaveText("Item 216417");
  await expect(trail(page).locator("a[href]", { hasText: "Item 216417" })).toHaveCount(0); // where you are, not a way to its pages
  await expect(itemsCrumb(page)).toHaveAttribute("href", "/?collection=1");
});

test("a record of one page has no page arrows, and one of several has", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?survey=216417_1");
  await expect(page.getByRole("navigation", { name: "Survey pages" })).toContainText("Page 1 of 2");
  await page.route("**/api/survey/216417_1", (route) => route.fulfill({ json: {
    id: "216417_1", bundleId: "pdf-216417", collectionId: 1, title: "Wilfred Prest Survey", recordName: "survey", grouped: true, pages: [pages[0]] } }));
  await page.reload();
  await expect(page.getByRole("heading", { name: "Transcript Review" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Survey pages" })).toHaveCount(0);
});

test("an item on the archive is named by its title in the review screen's crumbs and on its own page", async ({ page }) => {
  await mockApi(page, { archive: true });
  await page.goto("/?survey=216417_1&page=216417%2Fp0");
  await expect(crumbs(page)).toHaveText(["Items", "Brunswick 02 - Part 3", "Survey 216417_1"]);
  await trail(page).getByRole("link", { name: "Brunswick 02 - Part 3" }).click();
  await expect(page).toHaveURL("/?collection=1&bundle=216417");
  await expect(current(page)).toHaveText("Brunswick 02 - Part 3");
});

test("the review screen names its item from the survey and asks for no list of items", async ({ page }) => {
  await mockApi(page, { archive: true });
  const asked: string[] = [];
  page.on("request", (request) => asked.push(new URL(request.url()).pathname));
  await page.goto("/?survey=216417_1&page=216417%2Fp0");
  await expect(crumbs(page)).toHaveText(["Items", "Brunswick 02 - Part 3", "Survey 216417_1"]);
  expect(asked.filter((path) => /^\/api\/(bundles|progress|collections\/\d+\/items)/.test(path))).toEqual([]);
});

test("the review screen's Items crumb opens the series' items", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?survey=216417_1");
  await itemsCrumb(page).click();
  await expect(page).toHaveURL(/\/\?collection=1$/);
  await expect(page.getByRole("heading", { name: "All items" })).toBeVisible();
});

test("a survey without item info falls back to the bundle id in the crumb, and the dashboard accepts it", async ({ page }) => {
  await mockApi(page, { noItemInfo: true });
  await page.goto("/?survey=216417_1");
  const crumb = trail(page).getByRole("link", { name: "Item pdf-216417" });
  await expect(crumb).toHaveAttribute("href", "/?collection=1&bundle=pdf-216417");
  await expect(current(page)).toHaveText("Survey 216417_1");
  await crumb.click();
  await expect(page.getByRole("heading", { name: "Item 216417" })).toBeVisible();
});

for (const [url, crumb, h1] of [["/?view=import", "Import", "Import items"], ["/?view=settings", "Settings", "Settings"], ["/?view=tasks", "Tasks", "Tasks"]]) {
  test(`the ${crumb} screen is a crumb after the app's name, with one h1`, async ({ page }) => {
    await mockApi(page);
    await page.goto(url);
    await expect(crumbs(page)).toHaveText([crumb]);
    await expect(current(page)).toHaveText(crumb);
    await expect(page.locator("h1")).toHaveText(h1);
    await expect(switcher(page)).toHaveCount(0);
    await appName(page).click();
    await expect(page.getByRole("heading", { name: "Series", level: 1 })).toBeVisible();
  });
}

test("a series' actions sit by its title, Add items first; Settings and Tasks are in the top bar", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?collection=1");
  const main = page.getByRole("main");
  await expect(main.getByRole("button", { name: /^(Add items|Export|Import)$/ })).toHaveText(["Add items", "Export", "Import"]);
  await expect(page.getByRole("banner").getByRole("button")).toHaveCount(1); // the series menu; the rest are links
  await main.getByRole("button", { name: "Export", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Export" })).toBeVisible();
  await page.keyboard.press("Escape");
  await main.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Import items" })).toBeVisible();
  await page.goBack();
  await tabs(page).last().click();
  await expect(page).toHaveURL("/?collection=1&view=setup");
  await page.getByRole("banner").getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();
});

test("on a phone no screen scrolls sideways, and the trail shows the level above and where you are", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 375, height: 800 });
  for (const url of ["/", "/?collection=1", "/?collection=1&bundle=216417", "/?survey=216417_1", "/?view=import", "/?view=settings"]) {
    await page.goto(url);
    await expect(page.locator("h1").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), url).toBe(true);
  }
  await page.goto("/?survey=216417_1");
  await expect(current(page)).toBeVisible();
  await expect(trail(page).getByRole("link", { name: "Item 216417" })).toBeVisible(); // a way back up
  await expect(itemsCrumb(page)).toBeHidden();
  await expect(switcher(page)).toBeVisible();
  await page.goto("/?collection=1&bundle=216417");
  await expect(itemsCrumb(page)).toBeVisible();
});

test("an old item link without a series still opens the item", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?bundle=216417");
  await expect(page.getByRole("heading", { name: "Item 216417" })).toBeVisible();
  await expect(crumbs(page)).toHaveText(["Items", "Item 216417"]);
});

test("a record inside others follows them in the trail, each opening its records on the item's page", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/survey/216417_1", (route) => route.fulfill({ json: {
    id: "216417_1", bundleId: "pdf-216417", collectionId: 1, title: "Wilfred Prest Survey", recordName: "letter", grouped: true, pages,
    item: { name: "216417", archive: null }, parentId: "216417", ancestors: [{ id: "216417", name: "folder", parent: null }] } }));
  await page.goto("/?survey=216417_1");
  await expect(crumbs(page)).toHaveText(["Items", "Item 216417", "Folder 216417", "Letter 1"]);
  await expect(trail(page).getByRole("link", { name: "Folder 216417" })).toHaveAttribute("href", "/?collection=1&bundle=216417&record=216417");
  await page.route("**/api/survey/216417_1", (route) => route.fulfill({ json: {  // the folder holds just this letter: no crumb
    id: "216417_1", bundleId: "pdf-216417", collectionId: 1, title: "Wilfred Prest Survey", recordName: "letter", grouped: true, pages,
    item: { name: "216417", archive: null }, parentId: "216417", ancestors: [] } }));
  await page.reload();
  await expect(crumbs(page)).toHaveText(["Items", "Item 216417", "Letter 1"]); // numbered within its folder, not the item
});
