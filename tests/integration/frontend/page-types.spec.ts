import { test, expect, type Page } from "@playwright/test";

// The Page types screen (/?view=page-types) on an intercepted API: nothing reaches the real backend.
type PageType = { name: string; label: string; builtIn: boolean; unknown: boolean; startsRecord: boolean; matchedByKey: boolean; templateVersion: number | null };
const type = (name: string, label: string, over: Partial<PageType> = {}): PageType => ({
  name, label, builtIn: true, unknown: false, startsRecord: false, matchedByKey: false, templateVersion: null, ...over,
});

async function mockApi(page: Page, recordKey: string | null = "number_of_dwelling") {
  const types = [
    type("coded", "Coded page", { matchedByKey: true, templateVersion: 8 }),
    type("main", "Main page", { startsRecord: true, templateVersion: 7 }),
    type("notes", "Notes page", { templateVersion: 9 }),
    type("other", "Unknown", { unknown: true }),
  ];
  const collection = { id: 1, name: "Wilfred Prest Survey", recordKey };
  const versions: Record<string, { id: number; body: string }[]> = {
    main: [{ id: 7, body: '{"number_of_dwelling": null, "address": null}' }],
    coded: [{ id: 8, body: '{"number_of_dwelling": null}' }],
    notes: [{ id: 9, body: '{"text": null}' }],
  };
  const calls = { patchType: [] as unknown[], patchCollection: [] as unknown[], addType: [] as unknown[], saveTemplate: [] as unknown[] };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const named = path.match(/^\/api\/(page-types|instructions)\/(\w+)$/);
    if (path === "/api/page-types" && method === "GET") return route.fulfill({ json: types });
    if (path === "/api/reviewers") return route.fulfill({ json: [{ id: 1, name: "Ben" }] });
    if (path === "/api/collections/1" && method === "GET") return route.fulfill({ json: collection });
    if (path === "/api/collections/1" && method === "PATCH") {
      const body = request.postDataJSON();
      calls.patchCollection.push(body);
      if (body.recordKey === "address") return route.fulfill({ status: 400, json: { detail: "These page types' templates don't have 'address': Coded page." } });
      collection.recordKey = body.recordKey || null;
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
      versions[named[2]] = [{ id: 20, body: body.body }, ...(versions[named[2]] ?? [])];
      types.find((t) => t.name === named[2])!.templateVersion = 20;
      return route.fulfill({ status: 201, json: { id: 20 } });
    }
    return route.fulfill({ status: 404, json: { detail: "Not mocked." } });
  });
  return calls;
}

const row = (page: Page, label: string) => page.getByRole("row").filter({ has: page.getByRole("cell", { name: label, exact: true }) });

test("Settings links to the page types, listed by label with how they group and their template", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/connections", (route) => route.fulfill({ status: 500, json: { detail: "Not mocked." } }));
  await page.goto("/?view=settings");
  await page.getByRole("link", { name: "Manage page types" }).click();
  await expect(page).toHaveURL(/view=page-types/);
  await expect(page.getByRole("heading", { name: "Page types", level: 1 })).toBeVisible();
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
  expect(calls.saveTemplate.at(-1)).toEqual({ kind: "main", body: '{"number_of_dwelling": null, "street": null}', basedOn: 7, reviewerId: 1 });
});

test("a new page type is added by label, then opened to give it a template", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/?view=page-types");
  await page.getByRole("button", { name: "Add page type" }).click();
  const add = page.getByRole("dialog", { name: "Add page type" });
  await add.getByLabel("Label").fill("Follow-up visit");
  await add.getByLabel("Saved as").selectOption("Ben");
  await add.getByRole("button", { name: "Add" }).click();
  expect(calls.addType).toEqual([{ label: "Follow-up visit", reviewerId: 1 }]);
  const edit = page.getByRole("dialog", { name: "Edit Follow-up visit" });
  await expect(edit.getByText("Until it has one, pages of this type aren't read.")).toBeVisible();
  await edit.getByRole("button", { name: "Cancel" }).click();
  await expect(row(page, "Follow-up visit")).toContainText("None yet");
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
  expect(calls.patchCollection).toEqual([{ recordKey: "address" }, { recordKey: "" }]);
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
