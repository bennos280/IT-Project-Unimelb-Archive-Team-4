import { test, expect, type Page } from "@playwright/test";

// A series' Setup tab (/?view=setup; /?view=page-types, its old name, still opens it) on an intercepted API: nothing reaches the real backend.
type PageType = { name: string; label: string; builtIn: boolean; unknown: boolean; templateVersion: number | null };
type Part = { type: string; count: string; how: string };
type Level = { name: string; parts: Part[]; key: string | null };
// The Prest survey's level: a main form starts one, then any notes, and its one coded card is matched by number.
const MAIN_PART = { type: "main", count: "one_or_more", how: "starts" };
const NOTES_PART = { type: "notes", count: "any", how: "follows" };
const CODED_PART = { type: "coded", count: "one", how: "matched" };
const PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="; // a PNG, one pixel
type Version = { id: number; body: string; rules: object; reviewer: string | null; note: string | null; createdAt: string };
type CheckVersion = { id: number; number: number; checks: object[]; reviewer: string | null; note: string | null; createdAt: string };
const type = (name: string, label: string, over: Partial<PageType> = {}): PageType => ({
  name, label, builtIn: true, unknown: false, templateVersion: null, ...over,
});

async function mockApi(page: Page, recordKey: string | null = "number_of_dwelling", reviewers = [{ id: 1, name: "Ben" }],
  checkVersions: CheckVersion[] = []) {
  const types = [
    type("coded", "Coded page", { templateVersion: 8 }),
    type("main", "Main page", { templateVersion: 7 }),
    type("notes", "Notes page", { templateVersion: 9 }),
    type("other", "Unknown", { unknown: true }),
  ];
  const collection = {
    id: 1, name: "Wilfred Prest Survey", levels: [{ name: "survey", parts: [MAIN_PART, NOTES_PART, CODED_PART], key: recordKey }] as Level[],
    get recordName() { return this.levels.at(-1)?.name ?? "record"; },
    get grouped() { return Boolean(this.levels[0]?.parts.length); },
  };
  const version = (id: number, body: string, extra: Partial<Version> = {}): Version =>
    ({ id, body, rules: {}, reviewer: null, note: null, createdAt: "2026-10-01T02:00:00+00:00", ...extra });
  const versions: Record<string, Version[]> = {  // newest first
    main: [version(7, '{"number_of_dwelling": null, "address": null}', { reviewer: "Ben", note: "address added" }),
      version(3, '{"number_of_dwelling": null}')],
    coded: [version(8, '{"number_of_dwelling": null}', { rules: { number_of_dwelling: { type: "text", required: true } } })],
    notes: [version(9, '{"text": null}')],
  };
  const calls = {
    patchType: [] as unknown[], putLevels: [] as unknown[], tried: [] as unknown[], addType: [] as unknown[], saveTemplate: [] as unknown[], addReviewer: [] as unknown[],
    saveChecks: [] as { checks: object[]; basedOn: number | null; reviewerId: number; note: string | null }[], checkAgain: 0,
  };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const named = path.match(/^\/api\/(page-types|instructions)\/(\w+)$/);
    if (path === "/api/page-types" && method === "GET") return route.fulfill({ json: types });
    if (path === "/api/reviewers" && method === "POST") {
      const body = request.postDataJSON();
      calls.addReviewer.push(body);
      const person = { id: reviewers.length + 1, name: body.name };
      reviewers.push(person);
      return route.fulfill({ json: person });
    }
    if (path === "/api/reviewers") return route.fulfill({ json: reviewers });
    if (path === "/api/collections/1" && method === "GET") return route.fulfill({ json: collection });
    if (path === "/api/export/bundles") return route.fulfill({ json: [{ id: "b1", name: "216412" }] });
    if (path === "/api/pages/b1_00002/thumbnail") return route.fulfill({ contentType: "image/png", body: Buffer.from(PIXEL, "base64") }); // others aren't here
    if (path === "/api/collections/1/levels/preview" && method === "POST") {
      calls.tried.push(request.postDataJSON());
      return route.fulfill({ json: { records: [{ id: "b1-3", parent: null, pages: ["b1_00002", "b1_00003"] },
        { id: "b1-7", parent: null, pages: ["b1_00004", "b1_00006"] }], loose: ["b1_00001"],
        pageTypes: { b1_00001: "Notes page", b1_00002: "Main page", b1_00003: "Coded page", b1_00004: "Main page", b1_00006: "Coded page" },
        problems: [{ page: "b1_00004", record: "b1-7", reason: "expected one Coded page, found 2" }] } });
    }
    if (path === "/api/collections/1/levels" && method === "PUT") {
      const body = request.postDataJSON();
      calls.putLevels.push(body);
      if (body.levels.some((l: Level) => l.name.includes("#"))) return route.fulfill({ status: 400, json: { detail: "A level's name is a word or two, like survey or letter." } });
      collection.levels = body.levels.map((l: Level) => ({ ...l, name: l.name.trim().toLowerCase(), key: l.key?.trim() || null }));
      return route.fulfill({ json: collection });
    }
    if (path === "/api/page-types" && method === "POST") {
      const body = request.postDataJSON();
      calls.addType.push(body);
      const created = type("follow_up_visit", body.label, { builtIn: false });
      types.push(created);
      return route.fulfill({ status: 201, json: created });
    }
    if (named?.[1] === "page-types" && method === "PATCH") {
      const body = request.postDataJSON();
      calls.patchType.push(body);
      const t = types.find((t) => t.name === named[2])!;
      Object.assign(t, { label: body.label });
      return route.fulfill({ json: t });
    }
    if (path === "/api/instructions" && method === "GET") return route.fulfill({ json: Object.fromEntries(Object.entries(versions).map(([k, v]) => [k, v[0]])) });
    if (path === "/api/collections/1/checks" && method === "GET") return route.fulfill({ json: checkVersions });
    if (path === "/api/collections/1/checks" && method === "POST") {
      const body = request.postDataJSON();
      calls.saveChecks.push(body);
      checkVersions.unshift({ id: 100 + checkVersions.length, number: checkVersions.length + 1, checks: body.checks, reviewer: "Ben",
        note: body.note, createdAt: "2026-10-19T05:00:00+00:00" });
      return route.fulfill({ status: 201, json: checkVersions[0] });
    }
    if (path === "/api/collections/1/check" && method === "POST") {
      calls.checkAgain += 1;
      return route.fulfill({ status: 202, json: { id: 55, kind: "check" } });
    }
    if (named?.[1] === "instructions" && method === "GET")
      return versions[named[2]] ? route.fulfill({ json: versions[named[2]] }) : route.fulfill({ status: 404, json: { detail: "None." } });
    if (named?.[1] === "instructions" && method === "POST") {
      const body = request.postDataJSON();
      calls.saveTemplate.push({ kind: named[2], ...body });
      if (!body.body.includes("number_of_dwelling"))
        return route.fulfill({ status: 400, json: { detail: [`${named[2]}: needs 'number_of_dwelling'`, `${named[2]}: 'x' must be null`] } });
      versions[named[2]] = [version(20, body.body, { rules: body.rules }), ...(versions[named[2]] ?? [])];
      types.find((t) => t.name === named[2])!.templateVersion = 20;
      return route.fulfill({ status: 201, json: { id: 20 } });
    }
    return route.fulfill({ status: 404, json: { detail: "Not mocked." } });
  });
  return calls;
}

test("each of a template's fields gets a rule and a description, saved with it", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  await row(page, "Main page").getByRole("button", { name: "Edit Main page" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit Main page" });
  await expect(dialog.getByRole("table").first().locator("tbody tr td:first-child")).toHaveText(["number_of_dwelling", "address"]);
  await dialog.getByLabel("number_of_dwelling type").selectOption("number");
  await dialog.getByLabel("number_of_dwelling from").fill("1");
  await dialog.getByLabel("number_of_dwelling to").fill("999");
  await dialog.getByLabel("number_of_dwelling required").check();
  await dialog.getByLabel("address description").fill("Street and number");
  await expect(dialog.getByLabel("Template")).toHaveValue('{\n  "number_of_dwelling": null,\n  "address": "Street and number"\n}');
  await dialog.getByLabel("address type").selectOption("one_of");
  await dialog.getByLabel("address values").fill("1 Peel St\n2 = Two Peel St\n");
  await dialog.getByLabel("Saved as").selectOption("Ben");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls.saveTemplate.at(-1)).toEqual({
    kind: "main", body: '{\n  "number_of_dwelling": null,\n  "address": "Street and number"\n}', basedOn: 7, reviewerId: 1,
    rules: { number_of_dwelling: { type: "number", required: true, min: "1", max: "999" },
      address: { type: "one_of", values: ["1 Peel St", "2 = Two Peel St"] } },
  });
});

test("a rule changed on its own is a new version, a pattern takes an example, and broken JSON has no fields to set", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  await row(page, "Coded page").getByRole("button", { name: "Edit Coded page" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit Coded page" });
  await expect(dialog.getByLabel("number_of_dwelling required")).toBeChecked(); // the newest version's rule
  await expect(dialog.getByRole("button", { name: "Save" })).toBeDisabled(); // nothing changed yet
  await dialog.getByLabel("number_of_dwelling type").selectOption("pattern");
  await dialog.getByLabel("number_of_dwelling pattern").fill("\\d+[A-Z]?");
  await dialog.getByLabel("number_of_dwelling example").fill("24A");
  await dialog.getByLabel("Saved as").selectOption("Ben");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls.saveTemplate.at(-1)).toEqual({ kind: "coded", body: '{"number_of_dwelling": null}', basedOn: 8, reviewerId: 1,
    rules: { number_of_dwelling: { type: "pattern", required: true, pattern: "\\d+[A-Z]?", example: "24A" } } });

  await row(page, "Notes page").getByRole("button", { name: "Edit Notes page" }).click();
  const notes = page.getByRole("dialog", { name: "Edit Notes page" });
  await notes.getByLabel("Template").fill('{"text": ');
  await expect(notes.getByText("Fix the template's JSON to set its fields' rules.")).toBeVisible();
  await expect(notes.getByLabel("text type")).toHaveCount(0);
});

test("a template's history lists each version, and an older one can be brought back as the newest", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  await row(page, "Main page").getByRole("button", { name: "Edit Main page" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit Main page" });
  const history = dialog.getByRole("table").last().locator("tbody tr");
  await expect(history).toHaveCount(2);
  await expect(history.first()).toContainText("Ben");
  await expect(history.first()).toContainText("address added");
  await expect(history.first()).toContainText("Current");
  await expect(history.last()).toContainText("From the files");
  await dialog.getByRole("button", { name: "Use version 3" }).click();  // its own number, as elsewhere in the app
  await expect(dialog.getByLabel("Template")).toHaveValue('{"number_of_dwelling": null}');
  await dialog.getByLabel("Saved as").selectOption("Ben");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls.saveTemplate.at(-1)).toEqual({ kind: "main", body: '{"number_of_dwelling": null}', rules: {}, basedOn: 7, reviewerId: 1 });
});

const row = (page: Page, label: string) => page.getByRole("row").filter({ has: page.getByRole("cell", { name: label, exact: true }) });

// The levels' ladder, and what a level's record is made of on its page.
const ladder = (page: Page) => page.getByRole("list", { name: "Levels" }).getByRole("listitem");
const parts = (page: Page) => page.getByRole("list", { name: "Parts" }).getByRole("listitem");

test("a series' levels are a ladder from Item to Page, and its page types are listed by label with their template", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?collection=1&view=setup");
  await expect(page.getByRole("heading", { name: "Wilfred Prest Survey", level: 1 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Series" }).getByRole("link", { name: "Setup" })).toHaveAttribute("aria-current", "page");
  await expect(ladder(page)).toHaveText([/^Item\s*From the archive$/, /^Survey\s*1\+ Main page · any Notes page · 1 Coded page by number\s*Edit$/,
    /^Page\s*From the scan$/]);
  await expect(page.getByRole("tablist", { name: "Setup" }).getByRole("tab")).toHaveText(["Levels", "Page types", "Checks"]);
  await expect(page.getByRole("tab", { name: "Levels" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Page types" }).click();
  await expect(page).toHaveURL("/?collection=1&view=setup&section=page-types");
  await page.reload(); // the tab shown is kept
  await expect(page.getByRole("heading", { name: "Page types", level: 2 })).toBeVisible();
  await expect(row(page, "Main page")).toContainText("Saved");
  await expect(row(page, "Unknown")).toContainText("Not read: pages sorting couldn't place wait here");
  await expect(page.getByRole("columnheader", { name: "Grouping" })).toHaveCount(0);
});

test("a page type's label is saved on its own: how its pages group is its series' levels'", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  await row(page, "Notes page").getByRole("button", { name: "Edit Notes page" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit Notes page" });
  await expect(dialog.getByRole("radiogroup")).toHaveCount(0);
  await dialog.getByLabel("Label").fill("Interviewer notes");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls.patchType).toEqual([{ label: "Interviewer notes" }]);
  await expect(row(page, "Interviewer notes")).toBeVisible();
});

test("a template is saved as a new version by the chosen reviewer, and the checks' problems are listed", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  await row(page, "Main page").getByRole("button", { name: "Edit Main page" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit Main page" });
  const template = dialog.getByLabel("Template");
  await expect(template).toHaveValue('{"number_of_dwelling": null, "address": null}');
  await template.fill('{"address": null}');
  await expect(dialog.getByRole("button", { name: "Save" })).toBeDisabled(); // no reviewer yet
  await dialog.getByLabel("Saved as").selectOption("Ben");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog.getByText("main: needs 'number_of_dwelling'")).toBeVisible();
  await expect(dialog.getByText("main: 'x' must be null")).toBeVisible();
  await template.fill('{"number_of_dwelling": null, "street": null}');
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls.saveTemplate.at(-1)).toEqual({ kind: "main", body: '{"number_of_dwelling": null, "street": null}', rules: {}, basedOn: 7, reviewerId: 1 });
});

test("a new page type is added by label, then opened to give it a template", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  await page.getByRole("button", { name: "Add page type" }).click();
  const add = page.getByRole("dialog", { name: "Add page type" });
  await add.getByLabel("Label").fill("Follow-up visit");
  await add.getByLabel("Saved as").selectOption("Ben");
  await add.getByRole("button", { name: "Add" }).click();
  expect(calls.addType).toEqual([{ label: "Follow-up visit", reviewerId: 1, collectionId: 1 }]);
  const edit = page.getByRole("dialog", { name: "Edit Follow-up visit" });
  await expect(edit.getByText("Until it has one, pages of this type aren't read.")).toBeVisible();
  await edit.getByRole("button", { name: "Cancel" }).click();
  await expect(row(page, "Follow-up visit")).toContainText("None yet");
});

test("with no reviewers yet, whoever adds a page type adds their name there, and it's listed for the template", async ({ page }) => {
  const calls = await mockApi(page, undefined, []);
  await page.goto("/?view=page-types");
  await page.getByRole("button", { name: "Add page type" }).click();
  const add = page.getByRole("dialog", { name: "Add page type" });
  await add.getByLabel("Label").fill("Follow-up visit");
  await expect(add.getByRole("button", { name: "Add", exact: true })).toBeDisabled(); // no reviewer yet
  await add.getByLabel("New reviewer name").fill(" Lachlan ");
  await add.getByRole("button", { name: "Add reviewer" }).click();
  await expect(add.getByLabel("Saved as")).toHaveValue("1");
  await expect(add.getByLabel("New reviewer name")).toHaveCount(0);
  await add.getByRole("button", { name: "Add", exact: true }).click();
  expect(calls.addReviewer).toEqual([{ name: "Lachlan" }]);
  expect(calls.addType).toEqual([{ label: "Follow-up visit", reviewerId: 1, collectionId: 1 }]);

  const edit = page.getByRole("dialog", { name: "Edit Follow-up visit" });
  await edit.getByLabel("Template").fill('{"visit": null}');
  await edit.getByLabel("Saved as").selectOption("Lachlan");
  await expect(edit.getByLabel("New reviewer name")).toHaveCount(0);
});

test("a level's name, what one is made of in order, and its number field are saved together, and a refusal is shown", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?collection=1&view=setup");
  await page.getByRole("link", { name: "Edit survey" }).click();
  await expect(page).toHaveURL("/?collection=1&view=setup&level=1");
  await expect(page.getByRole("heading", { name: "Level: Survey", level: 1 })).toBeVisible();
  await expect(parts(page).locator("p:first-child")).toHaveText(["Main page", "Notes page", "Coded page"]);
  await expect(parts(page).first()).toContainText("Starts a survey");
  await expect(page.getByLabel("How many Main page")).toHaveValue("one_or_more");
  await expect(page.getByLabel("How many Notes page")).toHaveValue("any");
  await expect(page.getByLabel("Notes page may be filed elsewhere: match by number")).not.toBeChecked();
  await expect(page.getByLabel("Coded page may be filed elsewhere: match by number")).toBeChecked();
  await expect(page.getByLabel("Add a page type")).toHaveCount(0); // every read type is in it; the Unknown type isn't offered
  // the number field is one every page type that starts one or is matched to it has: the coded card's template has only the number
  await expect(page.getByLabel("Number field").locator("option")).toHaveText(["None: by page order only", "Number of dwelling"]);
  await page.getByLabel("Coded page may be filed elsewhere: match by number").uncheck();
  await expect(page.getByLabel("Number field").locator("option")).toHaveText(["None: by page order only", "Number of dwelling", "Address"]);
  await page.getByLabel("Number field").selectOption("address");
  await page.getByLabel("Name").fill("survey #1");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("A level's name is a word or two, like survey or letter.")).toBeVisible();
  await page.getByLabel("Name").fill("Household card");
  await expect(parts(page).first()).toContainText("Starts a household card");
  await page.getByRole("button", { name: "Remove Coded page" }).click();
  await expect(page.getByLabel("Add a page type").locator("option")).toHaveText(["+ Add a page type", "Coded page"]);
  await page.getByLabel("How many Notes page").selectOption("At most one");
  await page.getByLabel("Number field").selectOption("");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page).toHaveURL("/?collection=1&view=setup");
  expect(calls.putLevels.at(-1)).toEqual({ levels: [{ name: "Household card", parts: [MAIN_PART, { ...NOTES_PART, count: "at_most_one" }], key: "" }] });
  await expect(ladder(page).nth(1)).toHaveText(/^Household card\s*1\+ Main page · 0–1 Notes page\s*Edit$/);
});

test("a level added goes inside the bottom one, its first page type starting one, and the ladder steps down to it", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?collection=1&view=setup");
  await page.getByRole("link", { name: "Add level" }).click();
  await expect(page).toHaveURL("/?collection=1&view=setup&level=new");
  await expect(page.getByText("It goes inside each survey. Items read from now on group by it.")).toBeVisible();
  await page.getByLabel("Name").fill("card");
  await expect(page.getByText("With no page types, each page is a card of its own.")).toBeVisible();
  await page.getByLabel("Add a page type").selectOption("Coded page");
  await page.getByLabel("Add a page type").selectOption("Notes page");
  await page.getByRole("button", { name: "Move Notes page up" }).click(); // now it starts one, and the coded card follows it
  await expect(parts(page).locator("p:first-child")).toHaveText(["Notes page", "Coded page"]);
  await expect(parts(page).first()).toContainText("Starts a card");
  await expect(page.getByRole("button", { name: "Move Notes page down" })).toBeFocused(); // at the top: on the button still there
  await expect(page.getByLabel("Coded page may be filed elsewhere: match by number")).not.toBeChecked();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(ladder(page)).toHaveText([/^Item/, /^Survey\s*1\+ Main page/, /^Card\s*1 Notes page · 1 Coded page\s*Edit$/, /^Page/]);
  await expect(ladder(page).last()).toHaveCSS("margin-left", "72px"); // three steps in
  expect(calls.putLevels).toEqual([{ levels: [{ name: "survey", parts: [MAIN_PART, NOTES_PART, CODED_PART], key: "number_of_dwelling" },
    { name: "card", parts: [{ type: "notes", count: "one", how: "starts" }, { type: "coded", count: "one", how: "follows" }], key: "" }] }]);
});

test("a level can be removed, leaving each item one record, and added again", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?collection=1&view=setup&level=1");
  await page.getByRole("button", { name: "Remove level" }).click();
  await expect(ladder(page)).toHaveText([/^Item/, /^Page/]);
  await expect(page.getByText("No levels: each item is one record.")).toBeVisible();
  await page.goto("/?collection=1&view=setup&level=1");
  await expect(page.getByText("This series has no such level.")).toBeVisible();
  await page.goto("/?collection=1&view=setup&level=new");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled(); // no name yet
  await page.getByLabel("Name").fill("letter");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(ladder(page).nth(1)).toHaveText(/^Letter\s*each page is one\s*Edit$/); // made of nothing
  await page.getByRole("link", { name: "Edit letter" }).click();
  await expect(page.getByLabel("Number field").locator("option")).toHaveText(["None: by page order only"]); // no page type to read one from
  await page.getByLabel("Add a page type").selectOption("Main page");
  await page.getByLabel("Add a page type").selectOption("Notes page");
  await page.getByRole("button", { name: "Remove Main page" }).click(); // the next one starts a letter now
  await expect(parts(page).first()).toContainText("Starts a letter");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(ladder(page).nth(1)).toHaveText(/^Letter\s*1 Notes page\s*Edit$/);
  expect(calls.putLevels).toEqual([{ levels: [] }, { levels: [{ name: "letter", parts: [], key: "" }] },
    { levels: [{ name: "letter", parts: [{ type: "notes", count: "one", how: "starts" }], key: "" }] }]);
});

test("the Unknown type has no template, and says where its pages wait", async ({ page }) => {
  await mockApi(page, null);
  await page.goto("/?view=page-types");
  await row(page, "Unknown").getByRole("button", { name: "Edit Unknown" }).click();
  const unknown = page.getByRole("dialog", { name: "Edit Unknown" });
  await expect(unknown.getByText("Pages sorting couldn't place wait here, unread, until a reviewer picks their type. They have no template.")).toBeVisible();
  await expect(unknown.getByLabel("Template")).toHaveCount(0);
});

// The Checks section: a series' checks across fields (backend/db/checks.py).
const checksSection = (page: Page) => page.locator("section").filter({ has: page.getByRole("heading", { name: "Checks", exact: true }) });
const DWELLING = { id: "dw", kind: "compare", left: ["main.number_of_dwelling"], op: "=", right: ["coded.number_of_dwelling"] };
const NOTES = { id: "nt", kind: "if", message: "Notes but no address", if: "notes.text", is: "filled", then: "main.address", must: "filled" };

test("a check is built from the series' fields, read back in words, and the checks saved together as a version", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=setup&section=checks");
  const section = checksSection(page);
  await expect(section.locator("tbody tr")).toHaveText(["No checks yet."]);
  await section.getByRole("button", { name: "Add check" }).click();
  const dialog = page.getByRole("dialog", { name: "Add check" });
  await dialog.getByLabel("Compare field 1").selectOption("main.number_of_dwelling");
  await expect(dialog.getByRole("button", { name: "Done" })).toBeDisabled(); // nothing to compare it with yet
  await dialog.getByLabel("With field 1").selectOption("coded.number_of_dwelling");
  await expect(dialog.getByText("Main page › number_of_dwelling = Coded page › number_of_dwelling")).toBeVisible();
  await dialog.getByRole("button", { name: "Done" }).click();

  await section.getByRole("button", { name: "Add check" }).click();
  const second = page.getByRole("dialog", { name: "Add check" });
  await second.getByLabel("Kind").selectOption("if");
  await second.getByLabel("If field").selectOption("notes.text");
  await second.getByLabel("Then field").selectOption("main.address");
  await second.getByLabel("Flag says").fill("Notes but no address");
  await second.getByRole("button", { name: "Done" }).click();
  await expect(section.locator("tbody tr td:first-child")).toHaveText([
    "Main page › number_of_dwelling = Coded page › number_of_dwelling",
    "If Notes page › text is filled, then Main page › address must be filled"]);
  await expect(section.locator("tbody tr").last()).toContainText("Notes but no address");

  await section.getByLabel("Saved as").selectOption("Ben");
  await section.getByLabel("Note", { exact: true }).fill("dwelling and notes");
  await section.getByRole("button", { name: "Save checks" }).click();
  await expect(section.getByRole("button", { name: "Save checks" })).toHaveCount(0);
  expect(calls.saveChecks).toEqual([{ basedOn: null, reviewerId: 1, note: "dwelling and notes", checks: [
    { ...DWELLING, id: expect.any(String) }, { ...NOTES, id: expect.any(String) }] }]);
  await expect(section.getByText("History (1 version)")).toBeVisible();
});

test("a check can be sums against a value, switched off, edited and removed, and an older version brought back", async ({ page }) => {
  const calls = await mockApi(page, undefined, undefined, [
    { id: 102, number: 2, checks: [DWELLING, NOTES], reviewer: "Ben", note: "notes", createdAt: "2026-10-19T04:00:00+00:00" },
    { id: 101, number: 1, checks: [DWELLING], reviewer: "Ben", note: null, createdAt: "2026-10-18T04:00:00+00:00" }]);
  await page.goto("/?view=setup&section=checks");
  const section = checksSection(page);
  const dwelling = "Main page › number_of_dwelling = Coded page › number_of_dwelling";
  await section.getByLabel(`${dwelling} on`).uncheck();
  await expect(section.getByRole("button", { name: "Save checks" })).toBeVisible();
  await section.getByRole("button", { name: "Discard" }).click();
  await expect(section.getByLabel(`${dwelling} on`)).toBeChecked();

  await section.getByRole("button", { name: `Edit ${dwelling}` }).click();
  const dialog = page.getByRole("dialog", { name: "Edit check" });
  await dialog.getByRole("button", { name: "Add a Compare field to sum" }).click();
  await dialog.getByLabel("Compare field 2", { exact: true }).selectOption("main.address");
  await dialog.getByLabel("Comparison").selectOption("<=");
  await dialog.getByLabel("With", { exact: true }).selectOption("value");
  await dialog.getByLabel("Value").fill("11");
  await dialog.getByRole("button", { name: "Done" }).click();
  const summed = "Main page › number_of_dwelling + Main page › address ≤ 11";
  await expect(section.locator("tbody tr td:first-child").first()).toHaveText(summed);
  await section.getByRole("button", { name: /^Remove If Notes page/ }).click();
  await section.getByLabel("Saved as").selectOption("Ben");
  await section.getByRole("button", { name: "Save checks" }).click();
  await expect(section.getByRole("button", { name: "Save checks" })).toHaveCount(0);
  expect(calls.saveChecks.at(-1)).toEqual({ basedOn: 102, reviewerId: 1, note: null, checks: [
    { id: "dw", kind: "compare", left: ["main.number_of_dwelling", "main.address"], op: "<=", value: "11" }] });

  await section.getByText("History (3 versions)").click();
  await section.getByRole("button", { name: "Use checks version 1" }).click();
  await expect(section.locator("tbody tr td:first-child").first()).toHaveText(dwelling);
  await section.getByLabel("Saved as").selectOption("Ben");
  await section.getByRole("button", { name: "Save checks" }).click();
  await expect.poll(() => calls.saveChecks.at(-1)?.checks).toEqual([DWELLING]);
});

test("Check again checks the series' pages as a task, linked to it", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=setup&section=checks");
  await checksSection(page).getByRole("button", { name: "Check again" }).click();
  await expect(checksSection(page).getByRole("link", { name: "see the task" })).toHaveAttribute("href", "/?view=tasks&task=55");
  expect(calls.checkAgain).toBe(1);
});

test("a check can compare as codes, or say a field names another's code", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=setup&section=checks");
  const section = checksSection(page);
  await section.getByRole("button", { name: "Add check" }).click();
  let dialog = page.getByRole("dialog", { name: "Add check" });
  await dialog.getByLabel("Compare field 1").selectOption("main.number_of_dwelling");
  await dialog.getByLabel("With field 1").selectOption("coded.number_of_dwelling");
  await dialog.getByLabel("Compare as").selectOption("codes");
  await expect(dialog.getByText("Main page › number_of_dwelling = Coded page › number_of_dwelling (as codes)")).toBeVisible();
  await dialog.getByRole("button", { name: "Done" }).click();
  await section.getByRole("button", { name: "Add check" }).click();
  dialog = page.getByRole("dialog", { name: "Add check" });
  await dialog.getByLabel("Compare field 1").selectOption("main.address");
  await dialog.getByLabel("Comparison").selectOption("names");
  await expect(dialog.getByLabel("Compare as")).toHaveCount(0);
  await dialog.getByLabel("With field 1").selectOption("coded.number_of_dwelling");
  await dialog.getByRole("button", { name: "Done" }).click();
  await section.getByLabel("Saved as").selectOption("Ben");
  await section.getByRole("button", { name: "Save checks" }).click();
  await expect(section.getByRole("button", { name: "Save checks" })).toHaveCount(0);
  expect(calls.saveChecks.at(-1)?.checks).toEqual([
    { id: expect.any(String), kind: "compare", left: ["main.number_of_dwelling"], op: "=", right: ["coded.number_of_dwelling"], as: "codes" },
    { id: expect.any(String), kind: "compare", left: ["main.address"], op: "names", right: ["coded.number_of_dwelling"] }]);
});

test("a level's settings are tried on an item already read before they're saved, and a change hides the old try", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?collection=1&view=setup&level=1");
  const main = page.getByRole("main");
  await expect(main.getByLabel("Item to try it on")).toHaveValue("b1");
  await main.getByRole("button", { name: "Try it" }).click();
  const preview = main.getByLabel("Preview");
  await expect(preview).toContainText("2 surveys · 1 page in none · 1 problem");
  const records = preview.getByRole("list", { name: "Records" }).getByRole("listitem");
  await expect(records.locator("p:first-child")).toHaveText(["In no record · Pg 1", "Survey 3 · Pg 2–3", "Survey 7 · Pg 4–5"]);
  await expect(records.nth(2)).toContainText("expected one Coded page, found 2");
  // each page as a small scan, named by its type and place, opening the whole scan; one not on this computer says so
  const scans = records.nth(1).getByRole("link");
  await expect(scans.first()).toHaveAccessibleName("Main page · Pg 2");
  await expect(scans.first()).toHaveAttribute("href", "/api/pages/b1_00002/image");
  await expect(scans.first().locator("img")).toHaveAttribute("src", "/api/pages/b1_00002/thumbnail");
  await expect(scans.last()).toContainText("No scan here");
  await expect(scans.last().locator("img")).toHaveCount(0);
  await preview.getByLabel("Only ones with problems").check();
  await expect(records.locator("p:first-child")).toHaveText(["Survey 7 · Pg 4–5"]);
  expect(calls.tried).toEqual([{ levels: [{ name: "survey", parts: [MAIN_PART, NOTES_PART, CODED_PART], key: "number_of_dwelling" }], item: "b1" }]);
  expect(calls.putLevels).toEqual([]); // nothing saved
  await main.getByRole("button", { name: "Try it" }).click(); // tried again: every record shown
  await expect(records.locator("p:first-child")).toHaveText(["In no record · Pg 1", "Survey 3 · Pg 2–3", "Survey 7 · Pg 4–5"]);
  await expect(preview.getByLabel("Only ones with problems")).not.toBeChecked();
  await main.getByLabel("How many Notes page").selectOption("At most one");
  await expect(main.getByLabel("Preview")).toHaveCount(0); // tried with other settings
  await main.getByLabel("Name").fill("survey #1");
  await page.route("**/api/collections/1/levels/preview", (route) =>
    route.fulfill({ status: 400, json: { detail: "A level's name is a word or two, like survey or letter." } }));
  await main.getByRole("button", { name: "Try it" }).click();
  await expect(main.getByText("A level's name is a word or two, like survey or letter.")).toBeVisible();
  await main.getByLabel("Name").fill("survey");
  await expect(main.getByText("A level's name is a word or two, like survey or letter.")).toHaveCount(0); // tried with another name
});
