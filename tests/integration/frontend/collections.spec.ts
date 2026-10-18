import { test, expect, type Page } from "@playwright/test";

// Home (the collections) and New collection, on an intercepted API: nothing reaches the real backend or the archive.
const PREST = { id: 1, name: "Wilfred Prest Survey", recordKey: "number_of_dwelling", archiveSeries: 499420, bundles: 26, pages: 8853 };
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
    if (path === "/api/collections" && request.method() === "GET") return route.fulfill({ json: [PREST] });
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
    if (path === "/api/collections/2") return route.fulfill({ json: { ...PREST, id: 2, name: "Social survey forms", recordKey: null } });
    if (path === "/api/page-types") return route.fulfill({ json: [] });
    if (path === "/api/reviewers") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return created;
}

const dialog = (page: Page) => page.getByRole("dialog", { name: "New collection" });

test("home lists the collections with their archive series, bundles and pages", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  const row = page.getByRole("row").filter({ hasText: "Wilfred Prest Survey" });
  await expect(row.getByRole("link", { name: "Wilfred Prest Survey" })).toHaveAttribute("href", "/?collection=1");
  await expect(row.getByRole("link", { name: "Series 499420" })).toHaveAttribute("href", "https://archives.library.unimelb.edu.au/nodes/view/499420");
  await expect(row).toContainText("26");
  await expect(row).toContainText("8,853");
});

test("a new collection previews its archive series, takes its name from it, and opens its page types", async ({ page }) => {
  const created = await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "New collection" }).click();
  await dialog(page).getByLabel("Archive series").fill("https://archives.library.unimelb.edu.au/nodes/view/499420");
  const preview = dialog(page).getByRole("region", { name: "Archive series" });
  await expect(preview).toContainText("[UMA-SR-000000842] University of Melbourne Social Survey forms");
  await expect(preview).toContainText("UMA-SR-000000842 · 1941-1943 · Open for public access");
  await expect(preview).toContainText("45 items in this series");
  await expect(preview.getByRole("link", { name: "Open on the archive" })).toHaveAttribute("href", SERIES.url);
  await expect(dialog(page).getByLabel("Name")).toHaveValue("University of Melbourne Social Survey forms");
  await dialog(page).getByLabel("Name").fill("Social survey forms");
  await dialog(page).getByRole("button", { name: "Create collection" }).click();
  await expect(page).toHaveURL("/?collection=2&view=page-types");
  expect(created).toEqual([{ name: "Social survey forms", archiveSeries: "https://archives.library.unimelb.edu.au/nodes/view/499420" }]);
});

test("an item that isn't a series is pointed out, and a typed name is kept", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "New collection" }).click();
  await dialog(page).getByLabel("Name").fill("My name");
  await dialog(page).getByLabel("Archive series").fill("216412");
  await expect(dialog(page).getByText("This isn't a series.", { exact: false })).toBeVisible();
  await expect(dialog(page).getByLabel("Name")).toHaveValue("My name");
});

test("an address that isn't a series, and an archive that can't be reached, are said plainly", async ({ page }) => {
  await mockApi(page, { archiveDown: true });
  await page.goto("/");
  await page.getByRole("button", { name: "New collection" }).click();
  await dialog(page).getByLabel("Archive series").fill("UMA-SR-000000842");
  await expect(dialog(page).getByText("That isn't a series address or number.")).toBeVisible();
  await expect(dialog(page).getByRole("button", { name: "Create collection" })).toBeDisabled();
  await dialog(page).getByLabel("Archive series").fill("499420");
  await expect(dialog(page).getByText("Couldn't reach the archive (timed out).")).toBeVisible();
});

test("Where do I find it? shows where the series' number is", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "New collection" }).click();
  await expect(dialog(page).getByText("Copy the address from your browser's address bar.", { exact: false })).toBeHidden();
  await dialog(page).getByText("Where do I find it?").click();
  await expect(dialog(page).getByText("Copy the address from your browser's address bar.", { exact: false })).toBeVisible();
  await expect(dialog(page).getByText("A series' identifier starts with UMA-SR.", { exact: false })).toBeVisible();
});


test("a slow reply for an earlier address doesn't replace the newer one", async ({ page }) => {
  await mockApi(page, { slowNode: 216412 });
  await page.goto("/");
  await page.getByRole("button", { name: "New collection" }).click();
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
