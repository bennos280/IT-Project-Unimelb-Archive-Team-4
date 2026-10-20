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

type Type = { name: string; label: string; unknown: boolean; templateVersion: number | null };
type Version = { id: number; body: string; rules: Record<string, unknown> };
const UNKNOWN: Type = { name: "unknown_2", label: "Unknown", unknown: true, templateVersion: null };

// The series (its counts following its page types), its items (each with its count of pages, or a failure to get them), the scans
// asked for, and its page types, what its sample's pages were said to be, its templates' versions and what was sent, as the test
// changes them.
async function mock(page: Page, items = ITEMS, pages: Record<string, number | string> = { 101: 3, 102: 2 }) {
  const asked: string[] = [];
  const state = { types: [UNKNOWN], labels: {} as Record<string, string>, versions: {} as Record<string, Version[]>, sent: [] as unknown[] };
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const body = method === "GET" ? undefined : route.request().postDataJSON();
    if (body) state.sent.push({ [`${method} ${path}`]: body });
    const label = path.match(/^\/api\/collections\/2\/items\/101\/labels(?:\/(\d+))?$/);
    if (label && label[1]) {
      if (body.pageType) state.labels[label[1]] = body.pageType;
      else delete state.labels[label[1]];
    }
    if (label) return route.fulfill({ json: state.labels });
    if (path === "/api/page-types" && method === "POST") {
      const created = { name: body.label.toLowerCase().replaceAll(" ", "_"), label: body.label, unknown: false, templateVersion: null };
      state.types.push(created);
      return route.fulfill({ status: 201, json: created });
    }
    const template = path.match(/^\/api\/instructions\/(\w+)$/);
    if (template && method === "POST") {
      const version = { id: 50 + state.sent.length, body: body.body, rules: body.rules };
      state.versions[template[1]] = [version, ...(state.versions[template[1]] ?? [])];
      state.types.find((t) => t.name === template[1])!.templateVersion = version.id;
      return route.fulfill({ status: 201, json: version });
    }
    if (template) return route.fulfill({ json: state.versions[template[1]] });
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
    const own = state.types.filter((t) => !t.unknown);
    if (path === "/api/collections/2") {
      return route.fulfill({ json: { ...SERIES, pageTypes: own.length, templates: own.filter((t) => t.templateVersion).length } });
    }
    if (path === "/api/page-types") return route.fulfill({ json: state.types });
    if (path === "/api/reviewers") return route.fulfill({ json: [{ id: 1, name: "Ben" }] });
    if (path === "/api/export/bundles") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return Object.assign(asked, { state });
}

const sample = (page: Page) => page.getByRole("region", { name: /^Sample/ });
const strip = (page: Page) => sample(page).getByRole("list", { name: "Pages" });
const checklist = (page: Page) => page.getByRole("region", { name: "Set up this series to start reading it" });
const panel = (page: Page) => page.getByRole("region", { name: "This page" });
const marked = (page: Page) => checklist(page).locator('li[aria-current="step"]'); // the step to do now

test("a series not set up opens Setup on its first item, every page on screen beside the steps of setting it up", async ({ page }) => {
  const asked = await mock(page);
  await page.goto("/?series=2&view=setup");
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
  await expect(checklist(page)).toContainText("0 of 3 steps done");
  await expect(checklist(page).getByRole("link", { name: "Open setup" })).toHaveCount(0);
  await expect(checklist(page).getByRole("progressbar")).toHaveCount(0);
  await expect(marked(page)).toContainText("Add its page types"); // set beside the scan: no button of its own
  const read = checklist(page).getByRole("listitem").filter({ hasText: "Read one item as a sample" });
  await expect(read).toContainText("Transcribe it on its own page.");
  await expect(read.getByRole("link", { name: "Open item" })).toHaveAttribute("href", "/?series=2&item=101");
  await expect(read.getByRole("link", { name: "Open item" })).toHaveAttribute("data-variant", "outline"); // not the step to do yet
  await expect(checklist(page)).toContainText("Say what kind of page the one shown is.");
  await expect(checklist(page).getByRole("link", { name: "Add page types" })).toHaveCount(0); // done beside the scan

  // another item as the sample, kept in the URL, on its first page
  await sample(page).getByRole("button", { name: "Next item" }).click();
  await expect(sample(page).getByRole("heading")).toHaveText("Sample: Letters 1902");
  await expect(page).toHaveURL("/?series=2&view=setup&sample=2");
  await expect(sample(page).getByRole("img", { name: "Page 1 of 2" })).toBeVisible();
  await expect(sample(page).getByRole("button", { name: "Next item" })).toBeDisabled();
  await expect(read.getByRole("link", { name: "Open item" })).toHaveAttribute("href", "/?series=2&item=102");
  await page.reload();
  await expect(sample(page).getByRole("heading")).toHaveText("Sample: Letters 1902");
  await sample(page).getByRole("button", { name: "Previous item" }).click();
  await expect(page).toHaveURL("/?series=2&view=setup");

  // one asked for past the last is the last
  await page.goto("/?series=2&view=setup&sample=99");
  await expect(sample(page)).toContainText("Item 2 of 2 · 2 pages");
  await sample(page).getByRole("button", { name: "Previous item" }).click();
  await expect(sample(page).getByRole("heading")).toHaveText("Sample: Letters 1901");
});

test("the page shown is said to be a new page type, named beside it, and that type's fields listed and saved as its template", async ({ page }) => {
  const { state } = await mock(page);
  await page.goto("/?series=2&view=setup");
  await expect(panel(page).getByLabel("Page 1 is a")).toHaveValue("");
  await panel(page).getByLabel("Page 1 is a").selectOption("New page type…");
  await panel(page).getByLabel("New page type").fill("Casualty card");
  await panel(page).getByRole("button", { name: "Add" }).click();
  await expect(panel(page).getByLabel("Page 1 is a")).toHaveValue("casualty_card");
  await expect(strip(page).getByRole("button", { name: "Page 1, Casualty card" })).toHaveText("1 · Casualty card");
  await expect(checklist(page)).toContainText("Casualty card has none yet.");
  await expect(checklist(page)).toContainText("1 of 3 steps done");
  await expect(marked(page)).toContainText("Give each page type a template"); // page types done: templates are next

  const fields = panel(page).getByRole("group", { name: "Fields to read from each Casualty card" });
  await expect(fields).toContainText("Its pages aren't read until these are saved.");
  await fields.getByLabel("Field 1", { exact: true }).fill("Index No.");
  await fields.getByRole("button", { name: "Add field" }).click();
  await fields.getByLabel("Field 2", { exact: true }).fill("index no");
  await expect(fields).toContainText("Two fields have the same name.");
  await expect(fields.getByRole("button", { name: "Save template" })).toBeDisabled();
  await fields.getByLabel("Field 2", { exact: true }).fill("Surname");
  await fields.getByRole("button", { name: "Save template" }).click();
  await expect(checklist(page)).toContainText("2 of 3 steps done"); // its template saved: page types and templates
  await expect(marked(page)).toContainText("Read one item as a sample");
  await expect(checklist(page).getByRole("link", { name: "Open item" })).toHaveAttribute("data-variant", "default"); // now the main button
  await expect(fields.getByLabel("Field 2", { exact: true })).toHaveValue("Surname");
  await expect(fields.getByRole("button", { name: "Save template" })).toBeDisabled(); // nothing changed since

  // another page said to be it, then unsaid
  await strip(page).getByRole("button", { name: "Page 2" }).click();
  await expect(panel(page).getByLabel("Page 2 is a")).toHaveValue("");
  await panel(page).getByLabel("Page 2 is a").selectOption("Casualty card");
  await expect(strip(page).getByRole("button", { name: "Page 2, Casualty card" })).toBeVisible();
  await panel(page).getByLabel("Page 2 is a").selectOption("Not said yet");
  await expect(strip(page).getByRole("button", { name: "Page 2" })).toHaveText("2");
  expect(state.sent).toEqual([
    { "POST /api/page-types": { label: "Casualty card", reviewerId: 1, collectionId: 2 } },
    { "PUT /api/collections/2/items/101/labels/1": { pageType: "casualty_card" } },
    { "POST /api/instructions/casualty_card": { body: '{\n  "index_no": null,\n  "surname": null\n}', rules: {}, basedOn: null, reviewerId: 1 } },
    { "PUT /api/collections/2/items/101/labels/2": { pageType: "casualty_card" } },
    { "PUT /api/collections/2/items/101/labels/2": { pageType: null } },
  ]);
});

test("a template's fields changed beside the scan keep each kept field's description and rules; grouped ones are edited in Page types", async ({ page }) => {
  const { state } = await mock(page);
  state.types.push({ name: "letter", label: "Letter", unknown: false, templateVersion: 3 },
    { name: "form", label: "Form", unknown: false, templateVersion: 4 });
  state.versions = {
    letter: [{ id: 3, body: '{"sender": "as signed", "date": null}', rules: { sender: { type: "text", required: true }, date: { type: "date" } } }],
    form: [{ id: 4, body: '{"person": {"name": null}}', rules: {} }],
  };
  state.labels = { 1: "letter", 2: "form" };
  await page.goto("/?series=2&view=setup");
  const fields = panel(page).getByRole("group", { name: "Fields to read from each Letter" });
  await expect(fields.getByLabel("Field 1", { exact: true })).toHaveValue("Sender");
  await expect(fields.getByLabel("Field 2", { exact: true })).toHaveValue("Date");
  await fields.getByRole("button", { name: "Remove field 2" }).click();
  await fields.getByRole("button", { name: "Add field" }).click();
  await fields.getByLabel("Field 2", { exact: true }).fill("Place");
  await strip(page).getByRole("button", { name: "Page 3" }).click(); // another page and back: what's typed stays
  await strip(page).getByRole("button", { name: "Page 1, Letter" }).click();
  await expect(fields.getByLabel("Field 2", { exact: true })).toHaveValue("Place");
  await fields.getByRole("button", { name: "Save template" }).click();
  await expect.poll(() => state.sent.length).toBe(1);
  expect(state.sent[0]).toEqual({ "POST /api/instructions/letter": {
    body: '{\n  "sender": "as signed",\n  "place": null\n}', rules: { sender: { type: "text", required: true } }, basedOn: 3, reviewerId: 1 } });

  await strip(page).getByRole("button", { name: "Page 2, Form" }).click();
  await expect(panel(page)).toContainText("Its fields are grouped: edit them in Page types.");
  await expect(panel(page).getByRole("link", { name: "Page types" })).toHaveAttribute("href", "/?series=2&view=setup&section=page-types");
});

test("a section of Setup chosen shows it as usual, while the series isn't set up", async ({ page }) => {
  await mock(page);
  await page.goto("/?series=2&view=setup&section=page-types");
  await expect(page.getByRole("tab", { name: "Page types" })).toHaveAttribute("aria-selected", "true");
  await expect(sample(page)).toHaveCount(0);
  await page.getByRole("tab", { name: "Levels" }).click();
  await expect(page).toHaveURL("/?series=2&view=setup&section=levels");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Levels" })).toBeVisible();
});

test("an item whose scans the archive can't send says so, and can be asked for again", async ({ page }) => {
  const pages: Record<string, number | string> = { 101: "Couldn't get its scans from the archive (timed out).", 102: 2 };
  await mock(page, ITEMS, pages);
  await page.goto("/?series=2&view=setup");
  await expect(sample(page).getByRole("alert")).toContainText("Couldn't get its scans from the archive (timed out).");
  pages[101] = 4;
  await sample(page).getByRole("button", { name: "Try again" }).click();
  await expect(sample(page)).toContainText("Item 1 of 2 · 4 pages");
  await expect(sample(page).getByRole("alert")).toHaveCount(0);
});

test("a series with no items yet says to add some first", async ({ page }) => {
  await mock(page, []);
  await page.goto("/?series=2&view=setup");
  await expect(sample(page)).toContainText("Add items to the series first, on its Items page, then set it up on one of them.");
  await expect(sample(page).getByRole("link", { name: "Items" })).toHaveAttribute("href", "/?series=2");
  await expect(checklist(page)).toContainText("Transcribe one of its items.");
  await expect(checklist(page).getByRole("link", { name: "Open setup" })).toHaveCount(0);
});
