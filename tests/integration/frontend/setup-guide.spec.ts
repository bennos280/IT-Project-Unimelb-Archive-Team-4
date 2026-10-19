import { test, expect, type Page } from "@playwright/test";
import { serveItems, type MockItem } from "./items-mock";

// Setting a series up on a sample item, its pages on screen, in its Setup tab, on an intercepted API: nothing reaches the real
// backend or the archive.
const SERIES = {
  id: 2, name: "Letters", recordName: "record", levels: [], grouped: false, archiveSeries: 7, archiveIdentifier: null,
  pageTypes: 0, templates: 0, pages: 0, unknownPages: 0, bundles: 0, running: 0,
};
const ITEMS: MockItem[] = [
  { bundle: "101", name: "101", loaded: false, archive: { identifier: "UMA-IT-1", title: "Letters 1901" } },
  { bundle: "102", name: "102", loaded: false, archive: { identifier: "UMA-IT-2", title: "Letters 1902" } },
];
// a 1-pixel PNG, for every page's scan
const SCAN = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");

// The series, its items (each with its count of pages, or a failure to get them) and the scans asked for.
async function mock(page: Page, items = ITEMS, pages: Record<string, number | string> = { 101: 3, 102: 2 }) {
  const asked: string[] = [];
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const served = serveItems(items, route.request());
    if (served) return route.fulfill(served);
    const scans = path.match(/^\/api\/collections\/2\/items\/(\d+)\/scans(?:\/(\d+))?$/);
    if (scans && scans[2]) {
      asked.push(`${scans[1]}/${scans[2]}?width=${url.searchParams.get("width")}`);
      return route.fulfill({ body: SCAN, contentType: "image/png" });
    }
    if (scans) {
      const found = pages[scans[1]];
      return typeof found === "string" ? route.fulfill({ status: 502, json: { detail: found } }) : route.fulfill({ json: { pages: found } });
    }
    if (path === "/api/collections/2") return route.fulfill({ json: SERIES });
    if (path === "/api/page-types") return route.fulfill({ json: [{ name: "unknown_2", label: "Unknown", unknown: true, templateVersion: null }] });
    if (path === "/api/reviewers") return route.fulfill({ json: [] });
    if (path === "/api/export/bundles") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return asked;
}

const sample = (page: Page) => page.getByRole("region", { name: /^Sample/ });
const strip = (page: Page) => sample(page).getByRole("list", { name: "Pages" });
const checklist = (page: Page) => page.getByRole("region", { name: "Set up series" });

test("a series not set up opens Setup on its first item, every page on screen beside the steps of setting it up", async ({ page }) => {
  const asked = await mock(page);
  await page.goto("/?collection=2&view=setup");
  await expect(sample(page).getByRole("heading")).toHaveText("Sample: Letters 1901");
  await expect(sample(page)).toContainText("Item 1 of 2 · 3 pages");
  await expect(strip(page).getByRole("button")).toHaveText(["1", "2", "3"]);
  await expect(strip(page).getByRole("button", { name: "Page 1" })).toHaveAttribute("aria-current", "true");
  await expect(sample(page).getByRole("img", { name: "Page 1 of 3" })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Setup" })).toHaveCount(0);

  await strip(page).getByRole("button", { name: "Page 3" }).click();
  await expect(sample(page).getByRole("img", { name: "Page 3 of 3" })).toBeVisible();
  await expect(sample(page).getByRole("button", { name: "Next page" })).toBeDisabled();
  await sample(page).getByRole("button", { name: "Previous page" }).click();
  await expect(sample(page).getByRole("img", { name: "Page 2 of 3" })).toBeVisible();
  await expect(strip(page).getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "true");
  await expect.poll(() => asked.includes("101/3?width=1200")).toBe(true);
  await expect.poll(() => asked.filter((a) => a.endsWith("width=240")).sort()).toEqual(["101/1?width=240", "101/2?width=240", "101/3?width=240"]);

  // the pages are one tab stop, moved through by the arrow keys
  await expect(strip(page).locator('button[tabindex="0"]')).toHaveCount(1);
  await strip(page).getByRole("button", { name: "Page 2" }).focus();
  await page.keyboard.press("ArrowDown");
  await expect(strip(page).getByRole("button", { name: "Page 3" })).toBeFocused();
  await expect(sample(page).getByRole("img", { name: "Page 3 of 3" })).toBeVisible();
  await page.keyboard.press("Home");
  await expect(strip(page).getByRole("button", { name: "Page 1" })).toBeFocused();
  await expect(strip(page).getByRole("button", { name: "Page 1" })).toHaveAttribute("tabindex", "0");

  // the steps beside it; reading it is done on its own page
  await expect(checklist(page)).toContainText("0 of 3 done");
  await expect(checklist(page).getByRole("link", { name: "Open setup" })).toHaveCount(0);
  const read = checklist(page).getByRole("listitem").filter({ hasText: "Read one item as a sample" });
  await expect(read).toContainText("Transcribe it on its own page.");
  await expect(read.getByRole("link", { name: "Open item" })).toHaveAttribute("href", "/?collection=2&bundle=101");
  await expect(checklist(page).getByRole("link", { name: "Add page types" })).toHaveAttribute("href", "/?collection=2&view=setup&section=page-types");

  // another item as the sample, kept in the URL, on its first page
  await sample(page).getByRole("button", { name: "Next item" }).click();
  await expect(sample(page).getByRole("heading")).toHaveText("Sample: Letters 1902");
  await expect(page).toHaveURL("/?collection=2&view=setup&sample=2");
  await expect(sample(page).getByRole("img", { name: "Page 1 of 2" })).toBeVisible();
  await expect(sample(page).getByRole("button", { name: "Next item" })).toBeDisabled();
  await expect(read.getByRole("link", { name: "Open item" })).toHaveAttribute("href", "/?collection=2&bundle=102");
  await page.reload();
  await expect(sample(page).getByRole("heading")).toHaveText("Sample: Letters 1902");
  await sample(page).getByRole("button", { name: "Previous item" }).click();
  await expect(page).toHaveURL("/?collection=2&view=setup");

  // one asked for past the last is the last
  await page.goto("/?collection=2&view=setup&sample=99");
  await expect(sample(page)).toContainText("Item 2 of 2 · 2 pages");
  await sample(page).getByRole("button", { name: "Previous item" }).click();
  await expect(sample(page).getByRole("heading")).toHaveText("Sample: Letters 1901");
});

test("a section of Setup chosen shows it as usual, while the series isn't set up", async ({ page }) => {
  await mock(page);
  await page.goto("/?collection=2&view=setup&section=page-types");
  await expect(page.getByRole("tab", { name: "Page types" })).toHaveAttribute("aria-selected", "true");
  await expect(sample(page)).toHaveCount(0);
  await page.getByRole("tab", { name: "Levels" }).click();
  await expect(page).toHaveURL("/?collection=2&view=setup&section=levels");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Levels" })).toBeVisible();
});

test("an item whose scans the archive can't send says so, and can be asked for again", async ({ page }) => {
  const pages: Record<string, number | string> = { 101: "Couldn't get its scans from the archive (timed out).", 102: 2 };
  await mock(page, ITEMS, pages);
  await page.goto("/?collection=2&view=setup");
  await expect(sample(page).getByRole("alert")).toContainText("Couldn't get its scans from the archive (timed out).");
  pages[101] = 4;
  await sample(page).getByRole("button", { name: "Try again" }).click();
  await expect(sample(page)).toContainText("Item 1 of 2 · 4 pages");
  await expect(sample(page).getByRole("alert")).toHaveCount(0);
});

test("a series with no items yet says to add some first", async ({ page }) => {
  await mock(page, []);
  await page.goto("/?collection=2&view=setup");
  await expect(sample(page)).toContainText("Add items to the series first, on its Items page, then set it up on one of them.");
  await expect(sample(page).getByRole("link", { name: "Items" })).toHaveAttribute("href", "/?collection=2");
  await expect(checklist(page)).toContainText("Transcribe one of its items.");
  await expect(checklist(page).getByRole("link", { name: "Open setup" })).toHaveCount(0);
});
