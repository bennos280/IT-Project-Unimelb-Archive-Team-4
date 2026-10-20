import { test, expect, type Page } from "@playwright/test";
import { serveItems, type MockItem, type MockPage } from "./items-mock";

// A clickable table row opens its own link wherever it is clicked (WebKit included, so it runs on both engines),
// and a button or link inside it does its own thing. The API is intercepted: nothing reaches a real backend.
const BASE = {
  name: "", recordKey: "number_of_dwelling", archiveTitle: null, archiveItems: 45, bundles: 26, running: 0, failed: 0, pages: 8853,
  reviewable: 8719, reviewed: 1744, unknownPages: 0, flagged: 0, pageTypes: 3, templates: 3,
};
const SERIES = [1, 2, 3].map((id) => ({ ...BASE, id, name: `Series ${id}`, archiveSeries: 100 + id, archiveIdentifier: `UMA-SR-${id}` }));

const rows = (page: Page) => page.locator("tbody").getByRole("row");
// The cells of a row other than the one with the link.
const plainCell = (page: Page, row: number) => rows(page).nth(row).getByRole("cell").nth(2);

async function mock(page: Page, items: MockItem[] = []) {
  await page.context().route("https://archives.library.unimelb.edu.au/**", (route) => route.fulfill({ body: "archive" }));
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const served = serveItems(items, route.request());
    if (served) return route.fulfill(served);
    if (path === "/api/collections") return route.fulfill({ json: SERIES });
    if (path === "/api/collections/1")
      return route.fulfill({ json: { ...SERIES[0], levels: [], recordName: "survey", grouped: true } });
    if (path === "/api/reviewers") return route.fulfill({ json: [{ id: 1, name: "Ben" }] });
    if (path === "/api/jobs" || path === "/api/page-types") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
}

const survey = (name: string, id: string): MockPage[] =>
  [1, 2].map((n) => ({ id: `${name}/${id}p${n}`, label: `Pg ${n}`, category: "Main page", status: "Ready to review", flagCount: 0,
    surveyId: `${name}-${id}`, reviewPageId: `${name}/${id}p${n}` }));

test.describe("series table", () => {
  test.beforeEach(async ({ page }) => {
    await mock(page);
    await page.goto("/");
    await expect(rows(page)).toHaveCount(3);
  });

  for (const [index, name] of [[0, "first"], [1, "middle"], [2, "last"]] as const) {
    test(`a click on the ${name} row's plain cell opens that series`, async ({ page }) => {
      await plainCell(page, index).click({ force: true });
      await expect(page).toHaveURL(`/?collection=${index + 1}`);
    });
  }

  test("a click on the arrow cell or the link text opens that row's series", async ({ page }) => {
    await rows(page).nth(1).getByRole("cell").last().click();
    await expect(page).toHaveURL("/?collection=2");
    await page.goBack();
    await rows(page).nth(0).getByRole("link", { name: "Series 1" }).click();
    await expect(page).toHaveURL("/?collection=1");
  });

  test("the archive link in a row opens the archive and not the series", async ({ page }) => {
    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      rows(page).nth(0).getByRole("link", { name: "UMA-SR-1" }).click(),
    ]);
    expect(popup.url()).toBe("https://archives.library.unimelb.edu.au/nodes/view/101");
    await expect(page).toHaveURL("/");
  });
});

test.describe("items table", () => {
  const items: MockItem[] = [
    { bundle: "A", name: "A", pages: [...survey("A", "x"), ...survey("A", "y")] },
    { bundle: "B", name: "B", pages: [...survey("B", "x"), ...survey("B", "y")] },
    { bundle: "C", name: "C", loaded: false, pages: [] },
  ];
  test.beforeEach(async ({ page }) => {
    await mock(page, items);
    await page.goto("/?collection=1");
    await expect(rows(page)).toHaveCount(3);
  });

  for (const [index, name] of [[0, "A"], [1, "B"], [2, "C"]] as const) {
    test(`a click on item ${name}'s plain cell opens item ${name}`, async ({ page }) => {
      await plainCell(page, index).click({ force: true });
      await expect(page).toHaveURL(`/?collection=1&bundle=${name}`);
    });
  }

  test("a click on the link text opens that item", async ({ page }) => {
    await rows(page).nth(1).getByRole("link", { name: "B", exact: true }).click();
    await expect(page).toHaveURL("/?collection=1&bundle=B");
  });

  test("the Transcribe button in a row opens its dialog and not the item", async ({ page }) => {
    await rows(page).nth(2).getByRole("button", { name: "Transcribe", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Transcribe scans" })).toBeVisible();
    await expect(page).toHaveURL("/?collection=1");
  });
});

test.describe("an item's record table", () => {
  const items: MockItem[] = [{ bundle: "R", name: "R", pages: ["a", "b", "c"].flatMap((id) => survey("R", id)) }];
  test.beforeEach(async ({ page }) => {
    await mock(page, items);
    await page.goto("/?collection=1&bundle=R");
    await expect(rows(page)).toHaveCount(3);
  });

  for (const [index, id] of [[0, "a"], [1, "b"], [2, "c"]] as const) {
    test(`a click on record ${id}'s plain cell opens record ${id}`, async ({ page }) => {
      await plainCell(page, index).click({ force: true });
      await expect(page).toHaveURL(new RegExp(`^[^?]*\?survey=R-${id}&`));
    });
  }

  test("a click on the link text opens that record", async ({ page }) => {
    await rows(page).nth(1).getByRole("link").click();
    await expect(page).toHaveURL(/\?survey=R-b&/);
  });
});
