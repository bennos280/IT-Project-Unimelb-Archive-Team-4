import { test, expect, type Page } from "@playwright/test";

// Home (the collections) and New collection, on an intercepted API: nothing reaches the real backend or the archive.
const PREST = {
  id: 1, name: "Wilfred Prest Survey", recordKey: "number_of_dwelling", archiveSeries: 499420, archiveIdentifier: "UMA-SR-000000842",
  archiveTitle: "University of Melbourne Social Survey forms", archiveItems: 45, bundles: 26, running: 1, failed: 1, pages: 8853,
  reviewable: 8719, reviewed: 1744, unknownPages: 463, flagged: 1579, pageTypes: 3, templates: 3,
};
const SHIPS = { ...PREST, id: 3, name: "Shipping manifests", archiveSeries: 7, archiveIdentifier: null, archiveTitle: null,
  archiveItems: null, bundles: 0, running: 0, failed: 0, pages: 0, reviewable: 0, reviewed: 0, unknownPages: 0, flagged: 0,
  pageTypes: 0, templates: 0 };
const SERIES = {
  id: 499420, title: "[UMA-SR-000000842] University of Melbourne Social Survey forms", identifier: "UMA-SR-000000842",
  date: "1941-1943", access: "Open for public access", items: 45, url: "https://archives.library.unimelb.edu.au/nodes/view/499420",
};
const ITEM = { ...SERIES, id: 216412, title: "Box Hill 00", identifier: "UMA-ITE-1973000200001", items: null,
  url: "https://archives.library.unimelb.edu.au/nodes/view/216412" };

async function mockApi(page: Page, { archiveDown = false, slowNode = 0 } = {}) {
  const created: unknown[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/collections" && request.method() === "GET") return route.fulfill({ json: [PREST, SHIPS] });
    if (path === "/api/collections" && request.method() === "POST") {
      created.push(request.postDataJSON());
      return route.fulfill({ status: 201, json: { ...PREST, id: 2, name: request.postDataJSON().name, bundles: 0, pages: 0 } });
    }
    const series = path.match(/^\/api\/archive-series\/(\d+)$/);
    if (series) {
      if (archiveDown) return route.fulfill({ status: 502, json: { detail: "Couldn't reach the archive (timed out)." } });
      if (Number(series[1]) === slowNode) await new Promise((resolve) => setTimeout(resolve, 1500));
      const found = [SERIES, ITEM].find((s) => s.id === Number(series[1]));
      return found ? route.fulfill({ json: found }) : route.fulfill({ status: 404, json: { detail: "The archive has no page with that number." } });
    }
    if (path === "/api/collections/2") return route.fulfill({ json: { ...PREST, id: 2, name: "Social survey forms", recordKey: null, recordName: "record", grouped: false } });
    if (path === "/api/page-types") return route.fulfill({ json: [] });
    if (path === "/api/reviewers") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return created;
}

const dialog = (page: Page) => page.getByRole("dialog", { name: "New series" });

test("home lists each series with its archive identifier, items, review progress and what needs attention", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  const row = page.getByRole("row").filter({ hasText: "Wilfred Prest Survey" });
  await expect(row.getByRole("link", { name: "Wilfred Prest Survey" })).toHaveAttribute("href", "/?collection=1");
  await expect(row.getByRole("link", { name: "UMA-SR-000000842" })).toHaveAttribute("href", "https://archives.library.unimelb.edu.au/nodes/view/499420");
  await expect(row).toContainText("University of Melbourne Social Survey forms");
  await expect(row).toContainText("26 of 45 processed");
  await expect(row).toContainText("1 processing now");
  await expect(row).toContainText("1 failed");
  await expect(row).toContainText("1,744 / 8,719 pages · 20%");
  await expect(row).toContainText("463 pages need a type");
  await expect(row).toContainText("1,579 flags to check");
  await expect(row.getByRole("progressbar", { name: "Wilfred Prest Survey review progress" })).toBeVisible();
});

test("a series not set up yet shows its next step, and one with no identifier its series number", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  const row = page.getByRole("row").filter({ hasText: "Shipping manifests" });
  await expect(row.getByRole("link", { name: "Next: add its page types" })).toHaveAttribute("href", "/?collection=3&view=page-types");
  await expect(row.getByRole("link", { name: "Series 7" })).toBeVisible();
  await expect(row).toContainText("0 processed");
  await expect(row).toContainText("Nothing");
});

test("clicking anywhere on a series' row opens it", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  // A plain cell, clicked where a person would: the name's link covers the row.
  const box = (await page.getByRole("row").filter({ hasText: "Wilfred Prest Survey" }).getByRole("cell", { name: /26 of 45 processed/ }).boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page).toHaveURL("/?collection=1");
});

test("a new series previews what it links to on the archive, takes its name from it, and opens its page types", async ({ page }) => {
  const created = await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "New series" }).click();
  await dialog(page).getByLabel("Archive series").fill("https://archives.library.unimelb.edu.au/nodes/view/499420");
  const preview = dialog(page).getByRole("region", { name: "Archive series" });
  await expect(preview).toContainText("[UMA-SR-000000842] University of Melbourne Social Survey forms");
  await expect(preview).toContainText("UMA-SR-000000842 · 1941-1943 · Open for public access");
  await expect(preview).toContainText("45 items in this series");
  await expect(preview.getByRole("link", { name: "Open on the archive" })).toHaveAttribute("href", SERIES.url);
  await expect(dialog(page).getByLabel("Name")).toHaveValue("University of Melbourne Social Survey forms");
  await dialog(page).getByLabel("Name").fill("Social survey forms");
  await dialog(page).getByRole("button", { name: "Create series" }).click();
  await expect(page).toHaveURL("/?collection=2&view=page-types");
  await expect(page.getByText("No page type starts a record, so each page is a record of its own.", { exact: false })).toBeVisible();
  expect(created).toEqual([{ name: "Social survey forms", archiveSeries: "https://archives.library.unimelb.edu.au/nodes/view/499420",
    archiveIdentifier: "UMA-SR-000000842", archiveTitle: "[UMA-SR-000000842] University of Melbourne Social Survey forms", archiveItems: 45 }]);
});

test("an item that isn't a series is pointed out, and a typed name is kept", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "New series" }).click();
  await dialog(page).getByLabel("Name").fill("My name");
  await dialog(page).getByLabel("Archive series").fill("216412");
  await expect(dialog(page).getByText("This isn't a series.", { exact: false })).toBeVisible();
  await expect(dialog(page).getByLabel("Name")).toHaveValue("My name");
});

test("an address that isn't a series, and an archive that can't be reached, are said plainly", async ({ page }) => {
  await mockApi(page, { archiveDown: true });
  await page.goto("/");
  await page.getByRole("button", { name: "New series" }).click();
  await dialog(page).getByLabel("Archive series").fill("UMA-SR-000000842");
  await expect(dialog(page).getByText("That isn't a series address or number.")).toBeVisible();
  await expect(dialog(page).getByRole("button", { name: "Create series" })).toBeDisabled();
  await dialog(page).getByLabel("Archive series").fill("499420");
  await expect(dialog(page).getByText("Couldn't reach the archive (timed out).")).toBeVisible();
});

test("Where do I find it? shows where the series' number is", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "New series" }).click();
  await expect(dialog(page).getByText("Copy the address from your browser's address bar.", { exact: false })).toBeHidden();
  await dialog(page).getByText("Where do I find it?").click();
  await expect(dialog(page).getByText("Copy the address from your browser's address bar.", { exact: false })).toBeVisible();
  await expect(dialog(page).getByText("A series' identifier starts with UMA-SR.", { exact: false })).toBeVisible();
});


test("a slow reply for an earlier address doesn't replace the newer one", async ({ page }) => {
  await mockApi(page, { slowNode: 216412 });
  await page.goto("/");
  await page.getByRole("button", { name: "New series" }).click();
  const asked = page.waitForRequest("**/api/archive-series/216412");
  await dialog(page).getByLabel("Archive series").fill("216412");
  await asked;
  await dialog(page).getByLabel("Archive series").fill("499420");
  const preview = dialog(page).getByRole("region", { name: "Archive series" });
  await expect(preview).toContainText("University of Melbourne Social Survey forms");
  await page.waitForResponse("**/api/archive-series/216412");
  await expect(preview).toContainText("University of Melbourne Social Survey forms");
  await expect(dialog(page).getByLabel("Name")).toHaveValue("University of Melbourne Social Survey forms");
});
