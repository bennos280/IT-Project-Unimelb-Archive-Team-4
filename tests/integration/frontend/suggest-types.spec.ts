import { test, expect, type Locator, type Page } from "@playwright/test";

// A series' Setup > Page types and its Suggest page types dialog on an intercepted API: nothing reaches the real backend.
type Suggestion = { label: string; description: string; pages: number[] };
type Answer = { status?: number; json: unknown };
type PageType = { name: string; label: string; builtIn: boolean; unknown: boolean; templateVersion: number | null };
const PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="; // a PNG, one pixel
const MODEL = { model: "claude-sonnet-5-5", provider: "claude", effort: "low" };
const type = (name: string, label: string, over: Partial<PageType> = {}): PageType => ({
  name, label, builtIn: true, unknown: false, templateVersion: null, ...over,
});
// The series has Coded page; the model finds it again in other letters, a second form and a cover with more pages than are shown.
const SUGGESTIONS: Suggestion[] = [
  { label: "Main form", description: "A printed form with handwritten answers", pages: [1, 5, 9] },
  { label: "Coded Page", description: "A card with a number in its corner", pages: [3] },
  { label: "Cover sheet", description: "A cover with a stamp", pages: [7, 11, 13, 15, 17, 19, 21, 23] },
];
const answer = (types: Suggestion[] = SUGGESTIONS): Answer => ({ json: { pages: [1, 3, 5, 7, 9, 11, 13, 15], types } });
// An item of the series; with no title it has no record on the archive (its scans were put here by hand) and isn't offered.
const item = (name: string, title: string | null) =>
  ({ name, bundle: name, pdf: `${name}.pdf`, archive: title && { identifier: name, title }, loaded: true, job: null });

async function mockApi(page: Page, configured: typeof MODEL | null = MODEL) {
  const types = [
    type("coded", "Coded page", { templateVersion: 8 }),
    type("main", "Main page", { templateVersion: 7 }),
    type("other", "Unknown", { unknown: true }),
  ];
  const api = {
    suggest: [] as unknown[], addType: [] as { label: string }[], itemsRequests: [] as string[], typeLoads: 0, unmocked: [] as string[],
    answer: answer(), gate: Promise.resolve(), aborted: 0,
    items: [item("216412", "Prest survey, box 1"), item("216413", "Prest survey, box 2"), item("216414", null)],
    failAdd: null as { label?: string; detail: string } | null, // refuses that page type (any, with no label)
    holdAdd: {} as Record<string, Promise<void>>, // a page type's POST waits for its promise
  };
  page.on("requestfailed", (request) => { if (request.url().endsWith("/page-types/suggest")) api.aborted += 1; });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const scan = url.pathname.match(/^\/api\/collections\/1\/items\/(\d+)\/scans\/\d+$/);
    if (url.pathname === "/api/collections" && url.searchParams.get("brief") === "true") return route.fulfill({ json: [{ id: 1, name: "Wilfred Prest Survey" }] });
    if (url.pathname === "/api/jobs") return route.fulfill({ json: [] }); // the header's task count
    if (url.pathname === "/api/reviewers") return route.fulfill({ json: [{ id: 1, name: "Ben" }] }); // who is working
    if (url.pathname === "/api/collections/1") return route.fulfill({ json: { id: 1, name: "Wilfred Prest Survey", levels: [] } });
    if (url.pathname === "/api/page-types" && method === "GET") {
      api.typeLoads += 1;
      return route.fulfill({ json: types });
    }
    if (url.pathname === "/api/page-types" && method === "POST") {
      const body = request.postDataJSON();
      api.addType.push(body);
      await api.holdAdd[body.label];
      if (api.failAdd && (!api.failAdd.label || api.failAdd.label === body.label)) return route.fulfill({ status: 409, json: { detail: api.failAdd.detail } });
      const created = type(body.label.toLowerCase().replace(/\W+/g, "_"), body.label, { builtIn: false });
      types.push(created);
      return route.fulfill({ status: 201, json: created });
    }
    if (url.pathname === "/api/collections/1/items" && method === "GET") {
      api.itemsRequests.push(url.search);
      return route.fulfill({ json: { items: api.items, page: 0, total: api.items.length, all: api.items.length, transcribed: api.items.length } });
    }
    if (url.pathname === "/api/transcription-models") return route.fulfill({ json: { configured, models: [] } });
    if (url.pathname === "/api/collections/1/page-types/suggest" && method === "POST") {
      api.suggest.push(request.postDataJSON());
      await api.gate;
      return route.fulfill({ status: api.answer.status ?? 200, json: api.answer.json }).catch(() => {}); // the page may have given up waiting
    }
    if (scan) return route.fulfill({ contentType: "image/png", body: Buffer.from(PIXEL, "base64") });
    api.unmocked.push(`${method} ${url.pathname}`);
    return route.fulfill({ status: 404, json: { detail: "Not mocked." } });
  });
  return api;
}

const open = async (page: Page) => {
  await page.goto("/?series=1&view=setup&section=page-types");
  await page.getByRole("button", { name: "Suggest page types" }).click();
  return page.getByRole("dialog", { name: "Suggest page types" });
};
const ask = (dialog: Locator) => dialog.getByRole("button", { name: "Suggest", exact: true }).click();
const row = (page: Page, label: string) => page.getByRole("row").filter({ has: page.getByRole("cell", { name: label, exact: true }) });
const suggestions = (dialog: Locator) => dialog.getByRole("list", { name: "Suggested page types" }).getByRole("listitem");
const suggestion = (dialog: Locator, label: string) =>
  suggestions(dialog).filter({ has: dialog.page().getByLabel(`Add ${label}`, { exact: true }) });

test("the button beside Add page type opens the dialog with the series' items and the model named", async ({ page }) => {
  const api = await mockApi(page);
  await page.goto("/?series=1&view=setup&section=page-types");
  await expect(page.getByRole("button", { name: "Add page type" })).toBeVisible();
  await page.getByRole("button", { name: "Suggest page types" }).click();
  const dialog = page.getByRole("dialog", { name: "Suggest page types" });
  await expect(dialog.getByText("claude-sonnet-5-5 · low on Claude Code looks at some of an item's pages and suggests the kinds of page in it.")).toBeVisible();
  await expect(dialog.getByLabel("Item to look at").locator("option")).toHaveText(["Prest survey, box 1", "Prest survey, box 2"]); // not 216414: no archive record
  await expect(dialog.getByLabel("Item to look at")).toHaveValue("216412");
  await expect(dialog.getByText("This series has no items from the archive")).toHaveCount(0);
  await expect(dialog.getByLabel("Pages to look at")).toHaveValue("16");
  await expect(dialog.getByRole("radio", { name: "Spread across the item" })).toBeChecked();
  await expect(dialog.getByRole("radio")).toHaveCount(3);
  await expect(dialog.getByLabel("From page")).toHaveCount(0);
  await expect(dialog.getByLabel("Anything the model should know")).toHaveValue("");
  await expect(dialog.getByRole("button", { name: "Suggest", exact: true })).toBeEnabled();
  expect([...new Set(api.itemsRequests)]).toEqual(["?page=0&size=100"]); // StrictMode runs the effect twice
  expect(api.suggest).toEqual([]); // nothing asked until Suggest is pressed
  expect(api.unmocked).toEqual([]);
});

test("with no model chosen, Suggest is disabled and the dialog says to choose one in Settings", async ({ page }) => {
  const api = await mockApi(page, null);
  const dialog = await open(page);
  await expect(dialog.getByText("Choose a transcription model in Settings first")).toBeVisible();
  await expect(dialog.getByLabel("Item to look at").locator("option")).toHaveCount(2); // the options are there to see
  await expect(dialog.getByRole("button", { name: "Suggest", exact: true })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeEnabled();
  expect(api.suggest).toEqual([]);
});

for (const [what, items] of [["no items", []], ["only items not from the archive", [item("216414", null)]]] as const) {
  test(`a series with ${what} says it has none from the archive to look at, with nothing to choose or ask`, async ({ page }) => {
    const api = await mockApi(page);
    api.items = [...items];
    const dialog = await open(page);
    await expect(dialog.getByText("This series has no items from the archive to look at yet.")).toBeVisible();
    await expect(dialog.getByLabel("Item to look at")).toBeDisabled();
    await expect(dialog.getByLabel("Item to look at").locator("option")).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Suggest", exact: true })).toBeDisabled();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toHaveCount(0);
    expect(api.suggest).toEqual([]);
  });
}

test("Suggest asks for pages spread across the item, and says it is asking until the answer comes", async ({ page }) => {
  const api = await mockApi(page);
  let release = () => {};
  api.gate = new Promise<void>((resolve) => { release = resolve; });
  const dialog = await open(page);
  await ask(dialog);
  await expect(dialog.getByRole("button", { name: "Asking…" })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeEnabled(); // the person can still give up waiting
  await expect(dialog.getByRole("status")).toHaveText("Asking about 16 pages… this can take a minute.");
  release();
  await expect(dialog.getByRole("list", { name: "Suggested page types" })).toBeVisible();
  expect(api.suggest).toEqual([{ item: "216412", count: 16, pick: "spread", hint: "" }]); // no range unless asked for
  expect(api.aborted).toBe(0);
});

for (const [how, close] of [
  ["Cancel", (dialog: Locator) => dialog.getByRole("button", { name: "Cancel" }).click()],
  ["Escape", (dialog: Locator) => dialog.page().keyboard.press("Escape")],
] as const) {
  test(`${how} while asking closes the dialog and abandons the request, whose answer shows nothing`, async ({ page }) => {
    const api = await mockApi(page);
    let release = () => {};
    api.gate = new Promise<void>((resolve) => { release = resolve; });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const dialog = await open(page);
    await ask(dialog);
    await expect(dialog.getByRole("button", { name: "Asking…" })).toBeDisabled();
    await close(dialog);
    await expect(dialog).toHaveCount(0);
    await expect.poll(() => api.aborted).toBe(1); // the browser stopped waiting
    await page.getByRole("button", { name: "Suggest page types" }).click(); // a new dialog starts afresh
    const again = page.getByRole("dialog", { name: "Suggest page types" });
    await expect(again.getByRole("button", { name: "Suggest", exact: true })).toBeEnabled();
    release(); // the model finishes after all
    await expect(again.getByLabel("Item to look at")).toHaveValue("216412");
    await expect(again.getByRole("list", { name: "Suggested page types" })).toHaveCount(0);
    await expect(again.getByRole("alert")).toHaveCount(0);
    expect(api.suggest).toHaveLength(1);
    expect(api.addType).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test("Suggest asks for pages at random from another item, the count held to 30, and a range left behind isn't sent", async ({ page }) => {
  const api = await mockApi(page);
  const dialog = await open(page);
  await dialog.getByLabel("Item to look at").selectOption("Prest survey, box 2");
  await dialog.getByRole("radio", { name: "A range of pages" }).click();
  await dialog.getByLabel("From page").fill("5");
  await dialog.getByRole("radio", { name: "At random" }).click();
  await expect(dialog.getByLabel("From page")).toHaveCount(0);
  await dialog.getByLabel("Pages to look at").fill("99");
  await expect(dialog.getByLabel("Pages to look at")).toHaveValue("99"); // as typed until it is left
  await dialog.getByLabel("Pages to look at").blur();
  await expect(dialog.getByLabel("Pages to look at")).toHaveValue("30");
  await ask(dialog);
  await expect(dialog.getByRole("list", { name: "Suggested page types" })).toBeVisible();
  expect(api.suggest).toEqual([{ item: "216413", count: 30, pick: "random", hint: "" }]);
});

test("the number fields keep what is typed, an empty one included, and the count is made a whole number from 1 to 30 when left", async ({ page }) => {
  await mockApi(page);
  const dialog = await open(page);
  const count = dialog.getByLabel("Pages to look at");
  await count.fill("");
  await expect(count).toHaveValue(""); // not put back to a number while the next one is being typed
  await count.pressSequentially("12");
  await expect(count).toHaveValue("12");
  for (const [typed, left] of [["", "16"], ["2.7", "2"], ["-3", "1"], ["30", "30"], ["31", "30"]]) {
    await count.fill(typed);
    await expect(count).toHaveValue(typed);
    await count.blur();
    await expect(count).toHaveValue(left);
  }
  await dialog.getByRole("radio", { name: "A range of pages" }).click();
  for (const field of [dialog.getByLabel("From page"), dialog.getByLabel("to", { exact: true })]) {
    await field.fill("");
    await expect(field).toHaveValue("");
    await field.pressSequentially("45");
    await expect(field).toHaveValue("45"); // a range has no top
  }
});

test("Suggest sends the numbers typed as whole ones: the count from 1 to 30 (16 when empty), the range's ends from 1", async ({ page }) => {
  const api = await mockApi(page);
  const dialog = await open(page);
  await dialog.getByRole("radio", { name: "A range of pages" }).click();
  await dialog.getByLabel("Pages to look at").fill("");
  await dialog.getByLabel("From page").fill("-4");
  await dialog.getByLabel("to", { exact: true }).fill("17.8");
  await ask(dialog);
  await expect(dialog.getByRole("list", { name: "Suggested page types" })).toBeVisible();
  await dialog.getByRole("button", { name: "Ask again" }).click();
  await dialog.getByLabel("Pages to look at").fill("99");
  await dialog.getByLabel("From page").fill("");
  await dialog.getByLabel("to", { exact: true }).fill("9.9");
  await ask(dialog);
  await expect(dialog.getByRole("list", { name: "Suggested page types" })).toBeVisible();
  expect(api.suggest).toEqual([{ item: "216412", count: 16, pick: "range", first: 1, last: 17, hint: "" },
    { item: "216412", count: 30, pick: "range", first: 1, last: 9, hint: "" }]);
});

test("Suggest asks for a range of pages with a hint, the range's ends shown only for it", async ({ page }) => {
  const api = await mockApi(page);
  const dialog = await open(page);
  await dialog.getByRole("radio", { name: "A range of pages" }).click();
  await expect(dialog.getByLabel("From page")).toHaveValue("1");
  await expect(dialog.getByLabel("to", { exact: true })).toHaveValue("20");
  await dialog.getByLabel("From page").fill("5");
  await dialog.getByLabel("to", { exact: true }).fill("12");
  await dialog.getByLabel("Pages to look at").fill("6");
  await dialog.getByLabel("Anything the model should know").fill("Covers and adverts count as their own page types.");
  await ask(dialog);
  await expect(dialog.getByRole("list", { name: "Suggested page types" })).toBeVisible();
  expect(api.suggest).toEqual([{ item: "216412", count: 6, pick: "range", first: 5, last: 12,
    hint: "Covers and adverts count as their own page types." }]);
});

test("the results list each suggestion with a checkbox, an editable name, its description and up to six example scans", async ({ page }) => {
  await mockApi(page);
  const dialog = await open(page);
  await ask(dialog);
  await expect(suggestions(dialog)).toHaveCount(3);
  const form = suggestion(dialog, "Main form");
  await expect(form.getByRole("checkbox", { name: "Add Main form" })).toBeChecked();
  await expect(form.getByLabel("Name for Main form")).toHaveValue("Main form");
  await expect(form.getByLabel("Name for Main form")).toBeEditable();
  await expect(form.getByText("A printed form with handwritten answers")).toBeVisible();
  await expect(form.getByRole("img")).toHaveCount(3);
  await expect(form.getByRole("img").first()).toHaveAttribute("alt", "Page 1");
  await expect(form.getByRole("img").nth(1)).toHaveAttribute("src", "/api/collections/1/items/216412/scans/5");
  await expect(form.getByRole("img").first()).toHaveJSProperty("naturalWidth", 1); // loaded
  await expect(form.getByText(/and \d+ more/)).toHaveCount(0);
  const cover = suggestion(dialog, "Cover sheet");
  await expect(cover.getByRole("img")).toHaveCount(6);
  await expect(cover.getByRole("img").last()).toHaveAttribute("src", "/api/collections/1/items/216412/scans/19");
  await expect(cover.getByText("and 2 more")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Add 2 page types" })).toBeEnabled();
  await expect(dialog.getByRole("button", { name: "Ask again" })).toBeEnabled();
});

test("a suggestion that matches a page type the series has, in any case, is unchecked and disabled", async ({ page }) => {
  await mockApi(page);
  const dialog = await open(page);
  await ask(dialog);
  const coded = suggestion(dialog, "Coded Page");
  await expect(coded.getByRole("checkbox", { name: "Add Coded Page" })).not.toBeChecked();
  await expect(coded.getByRole("checkbox", { name: "Add Coded Page" })).toBeDisabled();
  await expect(coded.getByLabel("Name for Coded Page")).toBeDisabled();
  await expect(coded.getByText("Already a page type")).toBeVisible();
  await expect(coded.getByText("A card with a number in its corner")).toBeVisible();
  await expect(dialog.getByText("Already a page type")).toHaveCount(1);
  await expect(dialog.getByRole("checkbox", { checked: true })).toHaveCount(2);
});

test("a suggestion unticked or renamed changes what Add sends: one page type per kept one under its new name, then the list reloads", async ({ page }) => {
  const api = await mockApi(page);
  const dialog = await open(page);
  await ask(dialog);
  await dialog.getByLabel("Name for Cover sheet").fill("Cover");
  await dialog.getByRole("checkbox", { name: "Add Main form" }).uncheck();
  await expect(dialog.getByLabel("Name for Main form")).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Add 1 page type" })).toBeEnabled();
  const loads = api.typeLoads;
  await dialog.getByRole("button", { name: "Add 1 page type" }).click();
  await expect(dialog).toHaveCount(0);
  expect(api.addType).toEqual([{ label: "Cover", reviewerId: 1, collectionId: 1 }]);
  await expect(row(page, "Cover")).toBeVisible();
  await expect(row(page, "Main form")).toHaveCount(0);
  expect(api.typeLoads).toBe(loads + 1);
  expect(api.unmocked).toEqual([]);
});

test("every kept suggestion is added in the order listed, and with none kept Add is disabled", async ({ page }) => {
  const api = await mockApi(page);
  const dialog = await open(page);
  await ask(dialog);
  await dialog.getByLabel("Name for Main form").fill("Printed form");
  await dialog.getByRole("button", { name: "Add 2 page types" }).click();
  await expect(dialog).toHaveCount(0);
  expect(api.addType).toEqual([{ label: "Printed form", reviewerId: 1, collectionId: 1 }, { label: "Cover sheet", reviewerId: 1, collectionId: 1 }]);
  await expect(page.getByRole("table").locator("tbody tr td:first-child")).toHaveText(["Coded page", "Main page", "Unknown", "Printed form", "Cover sheet"]);

  const again = await open(page); // Cover sheet is a page type the series has now; Main form was added as Printed form
  await ask(again);
  await expect(again.getByRole("checkbox", { checked: true })).toHaveCount(1);
  await again.getByRole("checkbox", { name: "Add Main form" }).uncheck();
  await expect(again.getByRole("button", { name: "Add 0 page types" })).toBeDisabled();
});

test("a page type that can't be added is shown in the dialog, which stays open, and Ask again clears the message", async ({ page }) => {
  const api = await mockApi(page);
  api.failAdd = { detail: "There is already a page type labelled Cover sheet." };
  const dialog = await open(page);
  await ask(dialog);
  await dialog.getByRole("checkbox", { name: "Add Main form" }).uncheck();
  const loads = api.typeLoads;
  await dialog.getByRole("button", { name: "Add 1 page type" }).click();
  await expect(dialog.getByText("There is already a page type labelled Cover sheet.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Add 1 page type" })).toBeEnabled();
  await expect(dialog.getByRole("checkbox", { name: "Add Cover sheet" })).toBeChecked(); // not added, so still kept
  expect(api.addType).toEqual([{ label: "Cover sheet", reviewerId: 1, collectionId: 1 }]);
  expect(api.typeLoads).toBe(loads); // nothing was added, so the list behind has nothing new to show
  await dialog.getByRole("button", { name: "Ask again" }).click();
  await expect(dialog.getByText("There is already a page type labelled Cover sheet.")).toHaveCount(0);
  await expect(dialog.getByLabel("Item to look at")).toBeVisible();
});

test("Add refuses a kept name that is a page type already, in any case, or kept twice, adding nothing until it is renamed or unticked", async ({ page }) => {
  const api = await mockApi(page);
  const dialog = await open(page);
  await ask(dialog);
  await dialog.getByLabel("Name for Cover sheet").fill("  main PAGE "); // the series has Main page
  await dialog.getByRole("button", { name: "Add 2 page types" }).click();
  await expect(dialog.getByText(`"main PAGE" is a page type already, or kept twice: rename it or untick it.`)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Add 2 page types" })).toBeEnabled();
  await dialog.getByLabel("Name for Cover sheet").fill("MAIN form"); // and Main form is kept too
  await dialog.getByRole("button", { name: "Add 2 page types" }).click();
  await expect(dialog.getByText(`"Main form" is a page type already, or kept twice: rename it or untick it.`)).toBeVisible();
  await expect(dialog.getByText("main PAGE")).toHaveCount(0);
  expect(api.addType).toEqual([]); // not even the one that was fine
  await dialog.getByRole("checkbox", { name: "Add Cover sheet" }).uncheck();
  await dialog.getByRole("button", { name: "Add 1 page type" }).click();
  await expect(dialog).toHaveCount(0);
  expect(api.addType).toEqual([{ label: "Main form", reviewerId: 1, collectionId: 1 }]);
});

test("a kept name is added trimmed, and one left blank isn't added or counted", async ({ page }) => {
  const api = await mockApi(page);
  const dialog = await open(page);
  await ask(dialog);
  await dialog.getByLabel("Name for Cover sheet").fill("  Cover  ");
  await dialog.getByLabel("Name for Main form").fill("   ");
  await expect(dialog.getByRole("button", { name: "Add 1 page type" })).toBeEnabled();
  await dialog.getByRole("button", { name: "Add 1 page type" }).click();
  await expect(dialog).toHaveCount(0);
  expect(api.addType).toEqual([{ label: "Cover", reviewerId: 1, collectionId: 1 }]);
});

test("each page type is unticked once added, and neither Cancel nor Escape closes the dialog while they are being added", async ({ page }) => {
  const api = await mockApi(page);
  let release = () => {};
  api.holdAdd["Cover sheet"] = new Promise<void>((resolve) => { release = resolve; });
  const dialog = await open(page);
  await ask(dialog);
  await dialog.getByRole("button", { name: "Add 2 page types" }).click();
  await expect(dialog.getByRole("button", { name: "Adding…" })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Ask again" })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeDisabled();
  await expect(dialog.getByRole("checkbox", { name: "Add Main form" })).not.toBeChecked(); // added
  await expect(dialog.getByRole("checkbox", { name: "Add Cover sheet" })).toBeChecked(); // being added
  expect(api.addType).toEqual([{ label: "Main form", reviewerId: 1, collectionId: 1 }, { label: "Cover sheet", reviewerId: 1, collectionId: 1 }]);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  release();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("table").locator("tbody tr td:first-child")).toHaveText(["Coded page", "Main page", "Unknown", "Main form", "Cover sheet"]);
});

test("a failure part-way leaves the dialog open with those added unticked and the list behind reloaded, and Add again adds only the rest", async ({ page }) => {
  const api = await mockApi(page);
  api.failAdd = { label: "Cover sheet", detail: "There is already a page type labelled Cover sheet." };
  const dialog = await open(page);
  await ask(dialog);
  const loads = api.typeLoads;
  await dialog.getByRole("button", { name: "Add 2 page types" }).click();
  await expect(dialog.getByText("There is already a page type labelled Cover sheet.")).toBeVisible();
  expect(api.addType).toEqual([{ label: "Main form", reviewerId: 1, collectionId: 1 }, { label: "Cover sheet", reviewerId: 1, collectionId: 1 }]);
  await expect.poll(() => api.typeLoads).toBe(loads + 1); // the page types are loaded again, with Main form among them
  const added = suggestion(dialog, "Main form");
  await expect(added.getByRole("checkbox", { name: "Add Main form" })).not.toBeChecked();
  await expect(added.getByText("Already a page type")).toBeVisible();
  await expect(dialog.getByRole("checkbox", { name: "Add Cover sheet" })).toBeChecked();
  await expect(dialog.getByRole("button", { name: "Add 1 page type" })).toBeEnabled();
  await dialog.getByLabel("Name for Cover sheet").fill("Cover");
  api.failAdd = null;
  await dialog.getByRole("button", { name: "Add 1 page type" }).click();
  await expect(dialog).toHaveCount(0);
  expect(api.addType.slice(2)).toEqual([{ label: "Cover", reviewerId: 1, collectionId: 1 }]);
  await expect(page.getByRole("table").locator("tbody tr td:first-child")).toHaveText(["Coded page", "Main page", "Unknown", "Main form", "Cover"]);
  expect(api.typeLoads).toBe(loads + 2);
});

for (const [status, detail] of [
  [409, "Choose a transcription model on the Settings page first."],
  [400, "That item has 8 pages: choose pages within them."],
  [502, "Page types couldn't be suggested: claude timed out after 300 seconds"],
] as const) {
  test(`a ${status} from Suggest shows its detail in the dialog, and Suggest can be pressed again`, async ({ page }) => {
    const api = await mockApi(page);
    api.answer = { status, json: { detail } };
    const dialog = await open(page);
    await dialog.getByLabel("Pages to look at").fill("8");
    await ask(dialog);
    await expect(dialog.getByText(detail)).toBeVisible();
    await expect(dialog.getByLabel("Pages to look at")).toHaveValue("8"); // still on the options
    await expect(dialog.getByRole("list", { name: "Suggested page types" })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Suggest", exact: true })).toBeEnabled();
    api.answer = answer();
    await ask(dialog);
    await expect(suggestions(dialog)).toHaveCount(3);
    await expect(dialog.getByText(detail)).toHaveCount(0);
    expect(api.suggest).toEqual([{ item: "216412", count: 8, pick: "spread", hint: "" }, { item: "216412", count: 8, pick: "spread", hint: "" }]);
  });
}

test("Ask again goes back to the options as they were, and a second answer replaces the first", async ({ page }) => {
  const api = await mockApi(page);
  const dialog = await open(page);
  await dialog.getByLabel("Item to look at").selectOption("Prest survey, box 2");
  await dialog.getByRole("radio", { name: "At random" }).click();
  await dialog.getByLabel("Anything the model should know").fill("Ignore the blank backs.");
  await ask(dialog);
  await dialog.getByLabel("Name for Cover sheet").fill("Cover");
  await dialog.getByRole("button", { name: "Ask again" }).click();
  await expect(dialog.getByRole("list", { name: "Suggested page types" })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /^Add \d+ page types?$/ })).toHaveCount(0);
  await expect(dialog.getByLabel("Item to look at")).toHaveValue("216413");
  await expect(dialog.getByRole("radio", { name: "At random" })).toBeChecked();
  await expect(dialog.getByLabel("Anything the model should know")).toHaveValue("Ignore the blank backs.");
  api.answer = answer([{ label: "Letter", description: "A typed letter", pages: [2] }]);
  await ask(dialog);
  await expect(suggestions(dialog)).toHaveCount(1);
  await expect(dialog.getByLabel("Name for Letter")).toHaveValue("Letter");
  await expect(dialog.getByRole("img")).toHaveAttribute("src", "/api/collections/1/items/216413/scans/2");
  await expect(dialog.getByRole("button", { name: "Add 1 page type" })).toBeEnabled();
  expect(api.suggest).toHaveLength(2);
  expect(api.addType).toEqual([]); // asking adds nothing
});

test("a suggestion list that comes back empty says so, and Cancel closes the dialog having added nothing", async ({ page }) => {
  const api = await mockApi(page);
  api.answer = answer([]);
  const dialog = await open(page);
  await ask(dialog);
  await expect(dialog.getByText("No page types were suggested. Try other pages, or a note.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Add 0 page types" })).toBeDisabled();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  expect(api.addType).toEqual([]);
});
