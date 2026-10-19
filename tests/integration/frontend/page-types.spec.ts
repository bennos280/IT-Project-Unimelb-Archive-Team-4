import { test, expect, type Page } from "@playwright/test";

// The Page types screen (/?view=page-types) on an intercepted API: nothing reaches the real backend.
type PageType = { name: string; label: string; builtIn: boolean; unknown: boolean; startsRecord: boolean; matchedByKey: boolean; templateVersion: number | null };
type Version = { id: number; body: string; rules: object; reviewer: string | null; note: string | null; createdAt: string };
const type = (name: string, label: string, over: Partial<PageType> = {}): PageType => ({
  name, label, builtIn: true, unknown: false, startsRecord: false, matchedByKey: false, templateVersion: null, ...over,
});

async function mockApi(page: Page, recordKey: string | null = "number_of_dwelling", reviewers = [{ id: 1, name: "Ben" }]) {
  const types = [
    type("coded", "Coded page", { matchedByKey: true, templateVersion: 8 }),
    type("main", "Main page", { startsRecord: true, templateVersion: 7 }),
    type("notes", "Notes page", { templateVersion: 9 }),
    type("other", "Unknown", { unknown: true }),
  ];
  const collection = {
    id: 1, name: "Wilfred Prest Survey", recordKey, recordName: "survey",
    get grouped() { return types.some((t) => t.startsRecord); },
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
    patchType: [] as unknown[], patchCollection: [] as unknown[], addType: [] as unknown[], saveTemplate: [] as unknown[], addReviewer: [] as unknown[],
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
    if (path === "/api/collections/1" && method === "PATCH") {
      const body = request.postDataJSON();
      calls.patchCollection.push(body);
      if (body.recordKey === "address") return route.fulfill({ status: 400, json: { detail: "These page types' templates don't have 'address': Coded page." } });
      collection.recordKey = body.recordKey || null;
      collection.recordName = body.recordName.trim().toLowerCase() || "record";
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
      Object.assign(t, { label: body.label, startsRecord: body.startsRecord, matchedByKey: body.matchedByKey });
      return route.fulfill({ json: t });
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
  await dialog.getByRole("button", { name: "Use version 1" }).click();
  await expect(dialog.getByLabel("Template")).toHaveValue('{"number_of_dwelling": null}');
  await dialog.getByLabel("Saved as").selectOption("Ben");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls.saveTemplate.at(-1)).toEqual({ kind: "main", body: '{"number_of_dwelling": null}', rules: {}, basedOn: 7, reviewerId: 1 });
});

const row = (page: Page, label: string) => page.getByRole("row").filter({ has: page.getByRole("cell", { name: label, exact: true }) });

test("a series' page types are listed by label with how they group and their template", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?collection=1&view=page-types");
  await expect(page.getByRole("heading", { name: "Page types", level: 1 })).toBeVisible();
  await expect(page.locator('[data-slot="breadcrumb-item"]')).toHaveText(
    ["Series", "Wilfred Prest Survey", "Page types"]);
  await expect(row(page, "Main page")).toContainText("Starts a survey");
  await expect(row(page, "Coded page")).toContainText("Joins the survey with the same number");
  await expect(row(page, "Notes page")).toContainText("Follows the page before it");
  await expect(row(page, "Unknown")).toContainText("Pages sorting couldn't place wait here");
  await expect(row(page, "Unknown")).toContainText("Not read");
  await expect(page.getByLabel("Survey number field")).toHaveValue("number_of_dwelling");
});

test("a page type's label and grouping are saved together", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  await row(page, "Notes page").getByRole("button", { name: "Edit Notes page" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit Notes page" });
  await dialog.getByLabel("Label").fill("Interviewer notes");
  await dialog.getByRole("radio", { name: /Starts a survey/ }).click();
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls.patchType).toEqual([{ label: "Interviewer notes", startsRecord: true, matchedByKey: false }]);
  await expect(row(page, "Interviewer notes")).toContainText("Starts a survey");
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

test("the survey number field saves, and a refusal is shown", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  const field = page.getByLabel("Survey number field");
  await field.fill("address");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("These page types' templates don't have 'address': Coded page.")).toBeVisible();
  await field.fill("");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(field).toHaveValue("");
  expect(calls.patchCollection).toEqual([{ recordName: "survey", recordKey: "address" }, { recordName: "survey", recordKey: "" }]);
});

test("the record name words the page types, and is saved with the number field", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  await page.getByLabel("Record name").fill("Household card");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(row(page, "Main page")).toContainText("Starts a household card");
  await expect(page.getByLabel("Household card number field")).toHaveValue("number_of_dwelling");
  expect(calls.patchCollection).toEqual([{ recordName: "Household card", recordKey: "number_of_dwelling" }]);
});

test("with no page type starting a record, each page is a record of its own", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?view=page-types");
  await row(page, "Main page").getByRole("button", { name: "Edit Main page" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit Main page" });
  await dialog.getByRole("radio", { name: /Follows the page before it/ }).click();
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(row(page, "Notes page")).toContainText("A survey of its own");
  await expect(page.getByText("No page type starts a survey, so each page is a survey of its own.", { exact: false })).toBeVisible();
});

test("joining by number needs a survey number field, and the Unknown type has no grouping or template", async ({ page }) => {
  await mockApi(page, null);
  await page.goto("/?view=page-types");
  await row(page, "Notes page").getByRole("button", { name: "Edit Notes page" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit Notes page" });
  await expect(dialog.getByRole("radio", { name: /Joins the survey with the same number/ })).toBeDisabled();
  await expect(dialog.getByText("Set a survey number field first.")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await row(page, "Unknown").getByRole("button", { name: "Edit Unknown" }).click();
  const unknown = page.getByRole("dialog", { name: "Edit Unknown" });
  await expect(unknown.getByText(/wait here, unread, until a reviewer picks their type/)).toBeVisible();
  await expect(unknown.getByRole("radiogroup")).toHaveCount(0);
  await expect(unknown.getByLabel("Template")).toHaveCount(0);
});
