import { test, expect, type Page } from "@playwright/test";
import { serveItems } from "./items-mock";

// Set up series on a series' Items page, on an intercepted API: nothing reaches the real backend.
type Type = { name: string; label: string; unknown: boolean; templateVersion: number | null };
const UNKNOWN: Type = { name: "unknown_2", label: "Unknown", unknown: true, templateVersion: null };
const LETTER: Type = { name: "letter", label: "Letter", unknown: false, templateVersion: 3 };
const ENVELOPE: Type = { name: "envelope", label: "Envelope", unknown: false, templateVersion: null };
const NEW = {
  id: 2, name: "Letters", recordName: "record", levels: [] as { name: string }[], grouped: false, archiveSeries: 7, archiveItems: 2,
  archiveIdentifier: null, pageTypes: 0, templates: 0, pages: 0, unknownPages: 0, bundles: 0, running: 0,
};

// The series, its page types and its items read, as the test changes them.
async function mock(page: Page) {
  const state = { series: { ...NEW }, types: [UNKNOWN], read: [] as { id: string; name: string }[] };
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const served = serveItems([{ bundle: "L1", name: "L1", loaded: false }, { bundle: "L2", name: "L2", loaded: false }], route.request());
    if (served) return route.fulfill(served);
    if (path === "/api/collections/2") return route.fulfill({ json: state.series });
    if (path === "/api/page-types") return route.fulfill({ json: state.types });
    if (path === "/api/export/bundles") return route.fulfill({ json: state.read });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return state;
}

const card = (page: Page) => page.getByRole("region", { name: /Set up series|Series set up/ });
const steps = (page: Page) => card(page).getByRole("list", { name: "Setup steps" }).getByRole("listitem");

test("a new series' Items page lists the steps of setting it up, each ticked from what it has, with where to do it", async ({ page }) => {
  const state = await mock(page);
  await page.goto("/?collection=2");
  await expect(card(page)).toContainText("0 of 3 done");
  await expect(card(page).getByRole("link", { name: "Open setup" })).toHaveAttribute("href", "/?collection=2&view=setup");
  await expect(steps(page).locator("p.font-medium")).toHaveText([
    "Add its page types: to do", "Give each page type a template: to do", "Read one item as a sample: to do", /^Say what a record is: to do\s*Optional$/]);
  await expect(steps(page).nth(0).getByRole("link", { name: "Add page types" })).toHaveAttribute("href", "/?collection=2&view=setup&section=page-types");
  await expect(steps(page).nth(2)).toContainText("Press Transcribe on one of its items below.");
  await expect(steps(page).nth(3).getByRole("link", { name: "Set levels" })).toHaveAttribute("href", "/?collection=2&view=setup&section=levels");

  // two page types, one with a template; an item read with all its pages waiting as Unknown isn't a sample yet
  Object.assign(state, { types: [UNKNOWN, LETTER, ENVELOPE], read: [{ id: "L1", name: "L1" }] });
  Object.assign(state.series, { pageTypes: 2, templates: 1, pages: 3, unknownPages: 3, bundles: 1, running: 1 });
  await page.reload();
  await expect(card(page)).toContainText("1 of 3 done");
  await expect(steps(page).nth(0)).toContainText("Letter and Envelope");
  await expect(steps(page).nth(0).getByRole("link")).toHaveCount(0);
  await expect(steps(page).nth(1)).toContainText("Envelope has none yet.");
  await expect(steps(page).nth(1).getByRole("link", { name: "Write templates" })).toHaveAttribute("href", "/?collection=2&view=setup&section=page-types");
  await expect(steps(page).nth(2)).toContainText("Reading…"); // another item is being read

  // set up: the sample read, until another item is read
  Object.assign(state, { types: [UNKNOWN, LETTER, { ...ENVELOPE, templateVersion: 4 }] });
  Object.assign(state.series, { templates: 2, pages: 4, unknownPages: 1, running: 0 });
  await page.reload();
  await expect(card(page).getByRole("heading")).toHaveText("Series set up");
  await expect(card(page).getByRole("link", { name: "Open setup" })).toHaveCount(0);
  await expect(card(page)).toContainText("Check the sample came out right, then read the other items.");
  await expect(steps(page).nth(2).getByRole("link", { name: "Check it" })).toHaveAttribute("href", "/?collection=2&bundle=L1");
  Object.assign(state.series, { bundles: 2 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "All items" })).toBeVisible();
  await expect(card(page)).toHaveCount(0);
});
