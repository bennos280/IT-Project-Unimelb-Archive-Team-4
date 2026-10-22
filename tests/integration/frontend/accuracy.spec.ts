import { test, expect, type Locator, type Page } from "@playwright/test";

// A series' Accuracy tab (/?series=1&view=accuracy) on an intercepted API: nothing reaches the real backend.
const COLLECTION = { id: 1, name: "Wilfred Prest Survey", recordName: "survey", grouped: true, archiveSeries: 499420, archiveIdentifier: "UMA-SR-000000842",
  pageTypes: 3, templates: 3, pages: 2, unknownPages: 0, bundles: 1, running: 0 };
const SAVED = { provider: "claude", model: "claude-saved-model", effort: "high" };
const SONNET = { provider: "claude", model: "sonnet", effort: "low" }; // the model MODEL was read with
// Ids are shared by the prompt and every page type's template, so they differ from the numbers shown.
const version = (id: number, kind: string, label: string, number: number, over: object = {}) =>
  ({ id, kind, label, number, current: true, body: `${kind} text ${number}`, reviewer: null, note: null, createdAt: "", ...over });
const VERSIONS = [
  version(2, "prompt", "Prompt", 1, { current: false, body: "Read the page as JSON." }),
  version(3, "main", "Main page", 1, { current: false, body: '{"address": null}' }),
  version(4, "coded", "Coded page", 1),
  version(5, "main", "Main page", 2, { body: '{"address": null, "number_of_dwelling": null}', reviewer: "Ben", note: "dwelling added", createdAt: "2026-10-01T02:00:00+00:00" }),
  version(6, "notes", "Notes page", 1),
  version(7, "prompt", "Prompt", 2, { body: "Read the page as JSON, carefully." }),
];
// The series' page types with their newest template's id; Unknown has none.
const type = (name: string, label: string, templateVersion: number | null, unknown = false) => ({ name, label, builtIn: true, unknown, templateVersion });
const TYPES = [type("main", "Main page", 5), type("coded", "Coded page", 4), type("notes", "Notes page", 6), type("unknown", "Unknown", null, true)];
// Read with the older prompt (v1, id 2) and the older main template (v1, id 3)
const MODEL = { ...SONNET, promptVersion: 2, templateVersion: 3, pages: 120, averageSeconds: 21.5 };
const CODED_READ = { ...MODEL, templateVersion: 4, pages: 20, averageSeconds: 8 };
const NEXTM = { ...MODEL, promptVersion: 7, templateVersion: 5, pages: 10, averageSeconds: 12 }; // the newest prompt and main template
const GPT = { provider: "codex", model: "gpt-x", effort: null, promptVersion: null, templateVersion: 5, pages: 4, averageSeconds: null };
const LONG = "a-model-with-a-very-long-name-from-some-provider-v1.2.3";
const ROW = { model: "sonnet", effort: "low", pageType: "main", promptVersion: 2, templateVersion: 3, pages: 3, fields: 60, changed: 3 }; // 95.0%
const NEXT_ROW = { ...ROW, promptVersion: 7, templateVersion: 5, pages: 4, fields: 40, changed: 4 }; // 90.0%
const CODED = { ...ROW, pageType: "coded", templateVersion: 4, pages: 2, fields: 20, changed: 5 }; // 75.0%; with ROW: 5 pages, 8 of 80 fields changed, 90.0%
const NOTES = { model: "gpt-x", effort: null, pageType: "notes", promptVersion: null, templateVersion: null, pages: 1, fields: 10, changed: 0 }; // 100.0%
const BOTH = [ROW, CODED]; // the set-up MODEL and CODED_READ read: Main page v1 95.0%, Coded page v1 75.0%

type Options = {
  accuracy?: object[] | null; // the body of GET /api/accuracy; null: it answers 500
  models?: object[] | null; // the models in GET /api/transcription-models; null: it answers 500
  configured?: object | null; // the model saved in Settings; null: none
  versions?: object[] | null; // the body of GET /api/instruction-versions; null: it answers 500
  types?: object[] | null; // the body of GET /api/page-types; null: it answers 500
  series?: null; // GET /api/collections/1 answers 500
  hold?: boolean; // hold the replies to accuracy and models until calls.release()
  holdVersions?: boolean; // hold the reply to the versions until calls.releaseVersions()
};

async function mockApi(page: Page, options: Options = {}) {
  const gate = (hold?: boolean) => { let release = () => {}; return { wait: hold ? new Promise<void>((resolve) => { release = resolve; }) : null, release: () => release() }; };
  const reads = gate(options.hold);
  const versions = gate(options.holdVersions);
  const calls = { accuracy: [] as string[], models: [] as string[], versions: [] as string[], types: [] as string[], release: reads.release, releaseVersions: versions.release };
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const collection = path.match(/^\/api\/collections\/(\d+)$/);
    if (collection) {
      const id = Number(collection[1]);
      if (options.series === null && id === 1) return route.fulfill({ status: 500, json: { detail: "No series." } });
      return route.fulfill({ json: { ...COLLECTION, id, name: id === 2 ? "Strathfieldsaye Estate Diaries" : COLLECTION.name } });
    }
    if (path === "/api/collections") return route.fulfill({ json: [COLLECTION] });
    if (path === "/api/reviewers") return route.fulfill({ json: [{ id: 1, name: "Ben" }] });
    if (path === "/api/transcription-models") {
      calls.models.push(url.search);
      await reads.wait;
      return options.models === null ? route.fulfill({ status: 500, json: { detail: "No models." } })
        : route.fulfill({ json: { configured: options.configured === undefined ? SAVED : options.configured, models: options.models ?? [] } });
    }
    if (path === "/api/accuracy") {
      calls.accuracy.push(url.search);
      await reads.wait;
      return options.accuracy === null ? route.fulfill({ status: 500, json: { detail: "No accuracy." } }) : route.fulfill({ json: options.accuracy ?? [] });
    }
    if (path === "/api/instruction-versions") {
      calls.versions.push(url.search);
      await versions.wait;
      return options.versions === null ? route.fulfill({ status: 500, json: { detail: "No versions." } }) : route.fulfill({ json: options.versions ?? VERSIONS });
    }
    if (path === "/api/page-types") {
      calls.types.push(url.search);
      return options.types === null ? route.fulfill({ status: 500, json: { detail: "No page types." } }) : route.fulfill({ json: options.types ?? TYPES });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return calls;
}

const OPEN = "/?series=1&view=accuracy";
const tabs = (page: Page) => page.getByRole("navigation", { name: "Series" }).getByRole("link");
const compare = (page: Page) => page.getByRole("table", { name: "Read so far and next run" });
// A row of the comparison by its row header, and its cells: what was read so far, what the next run will use, and the action.
const line = (page: Page, label: string) => compare(page).locator("tbody tr").filter({ has: page.getByRole("rowheader", { name: label, exact: true }) });
const leftOf = (page: Page, label: string) => line(page, label).getByRole("cell").nth(0);
const rightOf = (page: Page, label: string) => line(page, label).getByRole("cell").nth(1);
const actionOf = (page: Page, label: string) => line(page, label).getByRole("cell").nth(2);
const byType = (page: Page) => page.getByRole("table", { name: "By page type" });
const allSetUps = (page: Page) => page.getByRole("table", { name: "All set-ups" });
const cells = (table: Locator, row: number) => table.locator("tbody tr").nth(row).getByRole("cell");
const TYPE_HEADERS = ["Page type", "Pages read", "Time a page", "Reviewed", "Accuracy"];
const NEXT_TYPE_HEADERS = [...TYPE_HEADERS, "Next run accuracy"];
const badges = (scope: Locator) => scope.locator("[data-slot=badge]");
const notMeasured = (page: Page) => rightOf(page, "Accuracy").getByText("Not measured yet", { exact: true });
const disclosure = (page: Page) => page.getByRole("button", { name: /^All set-ups/ });
const noSidewaysScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
const y = async (locator: Locator) => (await locator.boundingBox())!.y;
const chosen = (dialog: Locator) => dialog.locator('button[aria-pressed="true"]');
const terms = (dialog: Locator) => dialog.locator("dl dt");
const field = (dialog: Locator, term: string) => dialog.locator(`dt:text-is("${term}") + dd`);

test("the series' tabs are Items, Accuracy and Setup, with Accuracy the one shown, under the series' name", async ({ page }) => {
  await mockApi(page, { models: [MODEL], accuracy: [ROW] });
  await page.goto(OPEN);
  await expect(page.locator("h1")).toHaveText("Wilfred Prest Survey");
  await expect(tabs(page)).toHaveText(["Items", "Accuracy", "Setup"]);
  for (const [i, href] of ["/?series=1", "/?series=1&view=accuracy", "/?series=1&view=setup"].entries())
    await expect(tabs(page).nth(i)).toHaveAttribute("href", href);
  await expect(tabs(page).nth(1)).toHaveAttribute("aria-current", "page");
  await expect(tabs(page).first()).not.toHaveAttribute("aria-current", "page");
  await expect(tabs(page).last()).not.toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { level: 2 })).toHaveText("Accuracy");
  await expect(page.getByRole("heading", { level: 3 })).toHaveText(["By page type"]);
});

test("the series' accuracy, models and page types are asked for with the series, the versions for all, and the links go to the series", async ({ page }) => {
  const calls = await mockApi(page, { models: [MODEL], accuracy: [ROW] });
  await page.goto("/?series=2&view=accuracy");
  await expect(page.locator("h1")).toHaveText("Strathfieldsaye Estate Diaries");
  await expect(tabs(page).nth(1)).toHaveAttribute("href", "/?series=2&view=accuracy");
  await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%");
  await expect(actionOf(page, "Accuracy").getByRole("link", { name: "Review more pages" })).toHaveAttribute("href", "/?series=2");
  await expect(actionOf(page, "Model").getByRole("link", { name: "Change model" })).toHaveAttribute("href", "/?view=settings&tab=transcription");
  const edit = compare(page).getByRole("link", { name: "Edit templates" });
  await expect(edit).toHaveCount(3);
  expect(await edit.evaluateAll((links) => links.map((link) => link.getAttribute("href")))).toEqual(Array(3).fill("/?series=2&view=setup"));
  expect([...new Set(calls.accuracy)]).toEqual(["?collection=2"]);
  expect([...new Set(calls.models)]).toEqual(["?collection=2"]);
  expect([...new Set(calls.types)]).toEqual(["?collection=2"]);
  expect([...new Set(calls.versions)]).toEqual(["?collection=2"]);
});

test("without a series the Accuracy view is home, which asks which", async ({ page }) => {
  await mockApi(page);
  await page.goto("/?view=accuracy");
  await expect(page.getByRole("heading", { name: "Series", level: 1 })).toBeVisible();
  await expect(tabs(page)).toHaveCount(0);
});

test("one table compares what was read so far with the next run, a row for the model, the prompt, each page type's template and the accuracy", async ({ page }) => {
  await mockApi(page, { models: [MODEL, CODED_READ], accuracy: BOTH });
  await page.goto(OPEN);
  const table = compare(page);
  await expect(table.getByRole("columnheader")).toHaveText(["Setting", "Read so far", "Next run", "Change"]);
  await expect(table.locator("th .sr-only")).toHaveText(["Setting", "Change"]); // no visible words over the row names or the actions
  await expect(table.getByRole("rowheader")).toHaveText(["Model", "Prompt", "Main page template", "Coded page template", "Notes page template", "Accuracy"]); // Unknown has no template
  await expect(table.getByRole("rowheader").first()).toHaveAttribute("scope", "row");
  for (const name of ["Read so far", "Next run"]) await expect(page.getByRole("heading", { name })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Read so far" })).toHaveCount(0);
  await expect(page.locator("svg.lucide-arrow-right")).toHaveCount(0);
  for (const gone of ["Next reads use", "By model", "Set-ups"]) await expect(page.getByText(gone, { exact: true })).toHaveCount(0);

  await expect(leftOf(page, "Model")).toHaveText("sonnet · claude · low effort");
  await expect(rightOf(page, "Model")).toContainText("claude-saved-model · claude · high effort");
  await expect(badges(rightOf(page, "Model"))).toHaveText("changed");
  const change = actionOf(page, "Model").getByRole("link", { name: "Change model" });
  await expect(change).toHaveAttribute("href", "/?view=settings&tab=transcription");
  await expect(change).toHaveAttribute("data-slot", "button");
  await expect(change).toHaveAttribute("data-variant", "outline");
  await expect(change).toHaveAttribute("data-size", "sm");

  await expect(leftOf(page, "Prompt").getByRole("button")).toHaveText("v1");
  await expect(leftOf(page, "Prompt").getByRole("button")).toHaveAccessibleName("Prompt v1");
  await expect(rightOf(page, "Prompt").getByRole("button")).toHaveText("v2");
  await expect(rightOf(page, "Prompt").getByRole("button")).toHaveAccessibleName("Prompt v2");
  await expect(badges(rightOf(page, "Prompt"))).toHaveText("changed");
  await expect(actionOf(page, "Prompt").getByRole("button")).toHaveText("View");
  await expect(actionOf(page, "Prompt").getByRole("button")).toHaveAttribute("data-variant", "outline");

  for (const [row, was, now, differs] of [["Main page template", "v1", "v2", true], ["Coded page template", "v1", "v1", false], ["Notes page template", null, "v1", false]] as const) {
    if (was) {
      await expect(leftOf(page, row).getByRole("button")).toHaveText(was);
      await expect(leftOf(page, row).getByRole("button")).toHaveAccessibleName(`${row} ${was}`);
    } else {
      await expect(leftOf(page, row)).toHaveText("—"); // the left never read it
      await expect(leftOf(page, row).getByRole("button")).toHaveCount(0);
    }
    await expect(rightOf(page, row).getByRole("button")).toHaveText(now);
    await expect(rightOf(page, row).getByRole("button")).toHaveAccessibleName(`${row} ${now}`);
    await expect(badges(rightOf(page, row))).toHaveCount(differs ? 1 : 0);
    const edit = actionOf(page, row).getByRole("link", { name: "Edit templates" });
    await expect(edit).toHaveAttribute("href", "/?series=1&view=setup");
    await expect(edit).toHaveAttribute("data-slot", "button");
    await expect(edit).toHaveAttribute("data-variant", "outline");
    await expect(edit).toHaveAttribute("data-size", "sm");
  }
  await expect(badges(table)).toHaveCount(3); // the model, the prompt and the main template
  await expect(badges(table).first()).toHaveClass(/bg-amber-100/);

  const percent = leftOf(page, "Accuracy").getByTestId("accuracy-percent");
  await expect(percent).toHaveText("90.0%"); // this set-up's: 8 of 80 fields, not "of" the pages read
  await expect(percent).toHaveClass(/text-2xl/);
  await expect(percent).toHaveClass(/font-semibold/);
  await expect(percent).toHaveClass(/tabular-nums/);
  const made = leftOf(page, "Accuracy").getByText("(8 of 80 fields, 5 pages)", { exact: true });
  await expect(made).toBeVisible();
  await expect(made).toHaveClass(/text-muted-foreground/);
  await expect(rightOf(page, "Accuracy")).toHaveText("Not measured yet");
  await expect(notMeasured(page)).toHaveClass(/text-muted-foreground/);
  await expect(page.getByTestId("next-accuracy-percent")).toHaveCount(0);
  const review = actionOf(page, "Accuracy").getByRole("link", { name: "Review more pages" });
  await expect(review).toHaveAttribute("href", "/?series=1");
  await expect(review).toHaveAttribute("data-slot", "button");
  await expect(review).toHaveAttribute("data-variant", "default"); // the primary one
  await expect(review).toHaveAttribute("data-size", "sm");

  const few = page.getByRole("status");
  await expect(few).toHaveText("Too few pages to rely on yet: review about 30.");
  await expect(few).toHaveClass(/text-muted-foreground/);
  const blanks = page.getByText("Blank fields count too, so pages with many blanks score higher.");
  await expect(blanks).toHaveClass(/text-muted-foreground/);
  const box = (await table.boundingBox())!;
  expect(await y(page.getByRole("heading", { level: 2 }))).toBeLessThan(box.y);
  expect(await y(few)).toBeGreaterThanOrEqual(box.y + box.height - 1); // the notes are under the table
  expect(await y(blanks)).toBeGreaterThan(await y(few));
  expect(await y(page.getByRole("heading", { name: "By page type" }))).toBeGreaterThan(await y(blanks));
  expect(await y(byType(page))).toBeGreaterThan(await y(page.getByRole("heading", { name: "By page type" })));
});

test("View opens the dialog on the newest prompt", async ({ page }) => {
  await mockApi(page, { models: [MODEL], accuracy: [ROW] });
  await page.goto(OPEN);
  await actionOf(page, "Prompt").getByRole("button", { name: "View", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Prompt", exact: true });
  await expect(chosen(dialog)).toContainText("v2");
  await expect(dialog).toContainText("Read the page as JSON, carefully.");
  await expect(dialog.getByRole("textbox")).toHaveCount(0); // the prompt is only viewed
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("the set-up on the left is the one with the most reviewed pages, not the one that read the most", async ({ page }) => {
  const GPT_ROW = { ...ROW, model: "gpt-x", effort: null, pages: 8, fields: 80, changed: 16 };
  await mockApi(page, { models: [MODEL, { ...MODEL, model: "opus", pages: 500 }], accuracy: [ROW, GPT_ROW] });
  await page.goto(OPEN);
  await expect(leftOf(page, "Model")).toHaveText("gpt-x · provider not recorded · effort not recorded");
  await expect(page.getByTestId("accuracy-percent")).toHaveText("80.0%");
  await expect(leftOf(page, "Accuracy")).toContainText("(16 of 80 fields, 8 pages)");
  await expect(leftOf(page, "Main page template").getByRole("button")).toHaveText("v1");
  await expect(cells(byType(page), 0)).toHaveText(["Main page", "—", "—", "8", "80.0%"], { useInnerText: true }); // it read none, as far as the models say
});

test("with as many reviewed pages in two set-ups, the one that read more is on the left", async ({ page }) => {
  await mockApi(page, { models: [MODEL, { ...MODEL, model: "opus", pages: 500 }], accuracy: [ROW, { ...ROW, model: "opus", changed: 6 }] });
  await page.goto(OPEN);
  await expect(leftOf(page, "Model")).toHaveText("opus · claude · low effort");
  await expect(page.getByTestId("accuracy-percent")).toHaveText("90.0%");
});

test("with no reviewed pages the set-up that read the most is on the left, which says none are reviewed and still offers to review", async ({ page }) => {
  await mockApi(page, { accuracy: [], models: [MODEL, { ...MODEL, model: "opus", pages: 300 }] });
  await page.goto(OPEN);
  await expect(leftOf(page, "Model")).toHaveText("opus · claude · low effort");
  await expect(leftOf(page, "Main page template").getByRole("button")).toHaveText("v1");
  await expect(leftOf(page, "Accuracy")).toHaveText("No reviewed pages yet");
  await expect(actionOf(page, "Accuracy").getByRole("link", { name: "Review more pages" })).toHaveAttribute("href", "/?series=1");
  await expect(page.getByTestId("accuracy-percent")).toHaveCount(0);
  await expect(page.getByRole("status")).toHaveCount(0); // no "too few" for none
  await expect(page.getByText("Blank fields count too")).toHaveCount(0);
  await expect(cells(byType(page), 0)).toHaveText(["Main page", "300", "21.5 s", "—", "not reviewed"], { useInnerText: true });
  await expect(notMeasured(page)).toBeVisible();
  await expect(disclosure(page)).toHaveText("All set-ups (2)"); // opus and sonnet
});

test("with nothing read or reviewed the left says so and offers to review, and the right still shows what the next run will use", async ({ page }) => {
  await mockApi(page, { accuracy: [], models: [] });
  await page.goto(OPEN);
  await expect(leftOf(page, "Accuracy")).toHaveText("No reviewed pages yet");
  await expect(actionOf(page, "Accuracy").getByRole("link", { name: "Review more pages" })).toBeVisible();
  await expect(compare(page).getByRole("rowheader")).toHaveText(["Model", "Prompt", "Main page template", "Coded page template", "Notes page template", "Accuracy"]);
  for (const row of ["Model", "Prompt", "Main page template", "Coded page template", "Notes page template"]) await expect(leftOf(page, row)).toHaveText("—");
  await expect(page.getByTestId("accuracy-percent")).toHaveCount(0);
  await expect(allSetUps(page)).toHaveCount(0);
  await expect(byType(page).locator("tbody tr")).toHaveCount(3); // the page types with a template, none of them read
  await expect(cells(byType(page), 0)).toHaveText(["Main page", "—", "—", "—", "not reviewed"], { useInnerText: true });
  await expect(disclosure(page)).toHaveCount(0);
  await expect(badges(page)).toHaveCount(0); // nothing to differ from
  await expect(rightOf(page, "Model")).toContainText("claude-saved-model · claude · high effort");
  await expect(rightOf(page, "Prompt").getByRole("button")).toHaveText("v2");
  for (const row of ["Main page template", "Coded page template", "Notes page template"]) await expect(rightOf(page, row).getByRole("button")).toHaveCount(1);
  await expect(page.getByRole("status")).toHaveCount(0);
  await expect(notMeasured(page)).toBeVisible();
});

test("with no model saved, no prompt version and no templates, the table says so and still links to where they are set", async ({ page }) => {
  await mockApi(page, { models: [], accuracy: [], configured: null, versions: [], types: [TYPES[3]] });
  await page.goto(OPEN);
  await expect(compare(page).getByRole("rowheader")).toHaveText(["Model", "Prompt", "Templates", "Accuracy"]); // one row for the templates there are none of
  await expect(rightOf(page, "Model")).toHaveText("No model chosen");
  await expect(rightOf(page, "Prompt")).toHaveText("From the files");
  await expect(actionOf(page, "Prompt").getByRole("button")).toHaveCount(0); // no prompt to view
  await expect(rightOf(page, "Templates")).toHaveText("None yet");
  await expect(byType(page)).toHaveCount(0); // nothing read, nothing reviewed and no page type with a template
  await expect(actionOf(page, "Model").getByRole("link", { name: "Change model" })).toHaveAttribute("href", "/?view=settings&tab=transcription");
  await expect(actionOf(page, "Templates").getByRole("link", { name: "Edit templates" })).toHaveAttribute("href", "/?series=1&view=setup");
});

// reads: how the pages the set-up on the left read were read; configured: the model saved
for (const [name, reads, configured, expected] of [
  ["nothing differs", { promptVersion: 7, templateVersion: 5 }, SONNET, { model: 0, prompt: 0, templates: 0 }],
  ["the model's name differs", { promptVersion: 7, templateVersion: 5 }, { ...SONNET, model: "opus" }, { model: 1, prompt: 0, templates: 0 }],
  ["only the effort differs", { promptVersion: 7, templateVersion: 5 }, { ...SONNET, effort: "high" }, { model: 1, prompt: 0, templates: 0 }],
  ["the prompt is older", { promptVersion: 2, templateVersion: 5 }, SONNET, { model: 0, prompt: 1, templates: 0 }],
  ["a template is older", { promptVersion: 7, templateVersion: 3 }, SONNET, { model: 0, prompt: 0, templates: 1 }],
] as const) {
  test(`the amber "changed" badges: ${name}`, async ({ page }) => {
    await mockApi(page, { models: [{ ...MODEL, ...reads }], accuracy: [{ ...ROW, ...reads }], configured });
    await page.goto(OPEN);
    await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%");
    await expect(badges(rightOf(page, "Model"))).toHaveCount(expected.model);
    await expect(badges(rightOf(page, "Prompt"))).toHaveCount(expected.prompt);
    await expect(badges(rightOf(page, "Main page template"))).toHaveCount(expected.templates);
    for (const row of ["Coded page template", "Notes page template"]) await expect(badges(rightOf(page, row))).toHaveCount(0); // the left never read them
    await expect(badges(compare(page).locator("tbody tr > td:first-of-type"))).toHaveCount(0); // none in the column of what was read so far
    const total = expected.model + expected.prompt + expected.templates;
    await expect(badges(compare(page))).toHaveCount(total);
    if (total) {
      await expect(badges(compare(page)).first()).toHaveText("changed");
      await expect(badges(compare(page)).first()).toHaveClass(/bg-amber-100/);
      await expect(badges(compare(page)).first()).toHaveClass(/text-amber-900/);
    }
  });
}

for (const [name, row, configured, measured] of [
  ["only older versions", ROW, SONNET, false],
  ["the newest prompt but an older template", { ...ROW, promptVersion: 7 }, SONNET, false],
  ["an older prompt but the newest template", { ...ROW, templateVersion: 5 }, SONNET, false],
  ["the newest template of another page type", { ...ROW, pageType: "coded", promptVersion: 7, templateVersion: 5 }, SONNET, false],
  ["the newest prompt and template under another model than the one saved", { ...ROW, promptVersion: 7, templateVersion: 5 }, SAVED, false],
  ["the newest prompt and template under the saved model with another effort", { ...ROW, promptVersion: 7, templateVersion: 5 }, { ...SONNET, effort: "high" }, false],
  ["the newest prompt and template under the saved model", { ...ROW, promptVersion: 7, templateVersion: 5 }, SONNET, true],
] as const) {
  test(`the next run ${measured ? "shows its accuracy" : "says it is not measured yet"} when the reviewed pages used ${name}`, async ({ page }) => {
    await mockApi(page, { models: [MODEL], accuracy: [row], configured });
    await page.goto(OPEN);
    await expect(page.getByTestId("accuracy-percent")).toBeVisible();
    await expect(page.getByTestId("next-accuracy-percent")).toHaveCount(measured ? 1 : 0);
    await expect(notMeasured(page)).toHaveCount(measured ? 0 : 1);
    await expect(rightOf(page, "Accuracy").getByTestId("next-accuracy-percent")).toHaveCount(measured ? 1 : 0);
  });
}

test("pages read with the next run's model, prompt and templates are measured on the right the way the left is, beside the old figure", async ({ page }) => {
  const NEXT = { ...NEXT_ROW, model: SAVED.model, effort: SAVED.effort, fields: 50, changed: 1 }; // 98.0%
  await mockApi(page, {
    models: [MODEL, { ...NEXTM, model: SAVED.model, effort: SAVED.effort }],
    accuracy: [{ ...ROW, pages: 5 }, NEXT, { ...NEXT, pageType: "coded", promptVersion: 2, templateVersion: 4, changed: 50 }], // the last has an older prompt
  });
  await page.goto(OPEN);
  await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%");
  await expect(leftOf(page, "Accuracy")).toContainText("(3 of 60 fields, 5 pages)");
  const next = rightOf(page, "Accuracy").getByTestId("next-accuracy-percent");
  await expect(next).toHaveText("98.0%");
  await expect(next).toHaveClass(/text-2xl/);
  await expect(next).toHaveClass(/font-semibold/);
  await expect(rightOf(page, "Accuracy")).toContainText("(1 of 50 fields, 4 pages)");
  await expect(rightOf(page, "Accuracy").getByText("(1 of 50 fields, 4 pages)", { exact: true })).toHaveClass(/text-muted-foreground/);
  await expect(page.getByRole("status")).toHaveText("Too few pages to rely on yet: review about 30."); // one note for the table
  await expect(page.getByText("Blank fields count too")).toHaveCount(1);
  await expect(notMeasured(page)).toHaveCount(0);
  await expect(badges(compare(page))).toHaveCount(3); // the model, the prompt and the main template
  const table = byType(page);
  await expect(table.getByRole("columnheader")).toHaveText(NEXT_TYPE_HEADERS);
  await expect(cells(table, 0)).toHaveText(["Main page", "120", "21.5 s", "5", "95.0%", "98.0%"], { useInnerText: true });
  await expect(cells(table, 1)).toHaveText(["Coded page", "—", "—", "—", "not reviewed", "not measured yet"], { useInnerText: true });
  expect(await y(next)).toBeGreaterThan(await y(rightOf(page, "Notes page template"))); // in the last row
});

for (const [pages, note] of [
  [1, "Too few pages to rely on yet: review about 30."],
  [29, "Too few pages to rely on yet: review about 30."],
  [30, null],
] as const) {
  test(`${pages} reviewed ${pages === 1 ? "page" : "pages"} ${note ? "carry a note that there are too few" : "carry no such note"}`, async ({ page }) => {
    await mockApi(page, { models: [MODEL], accuracy: [{ ...ROW, pages, fields: 100, changed: 10 }] });
    await page.goto(OPEN);
    await expect(page.getByTestId("accuracy-percent")).toHaveText("90.0%");
    await expect(leftOf(page, "Accuracy")).toContainText(`(10 of 100 fields, ${pages} ${pages === 1 ? "page" : "pages"})`);
    await expect(page.getByText("Blank fields count too, so pages with many blanks score higher.")).toBeVisible(); // whatever the number
    if (note) await expect(page.getByRole("status")).toHaveText(note);
    else await expect(page.getByRole("status")).toHaveCount(0);
  });
}

for (const [pages, note] of [[4, true], [30, false]] as const) {
  test(`the note of too few pages also counts the ${pages} pages reviewed with the next run: ${note ? "shown" : "not shown"}`, async ({ page }) => {
    const NEXT = { ...NEXT_ROW, model: SAVED.model, effort: SAVED.effort, pages }; // 90.0%
    await mockApi(page, { models: [MODEL, { ...NEXTM, model: SAVED.model, effort: SAVED.effort }], accuracy: [{ ...ROW, pages: 30 }, NEXT] });
    await page.goto(OPEN);
    await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%"); // 30 pages: enough on the left
    await expect(page.getByTestId("next-accuracy-percent")).toHaveText("90.0%");
    await expect(page.getByRole("status")).toHaveCount(note ? 1 : 0);
  });
}

test("By page type is one table across the bottom with a row for each page type: what the set-up on the left read and reviewed of it, and the next run's accuracy", async ({ page }) => {
  await mockApi(page, { models: [MODEL, CODED_READ, NEXTM, GPT], accuracy: BOTH });
  await page.goto(OPEN);
  const table = byType(page);
  await expect(page.getByRole("heading", { name: "By page type", level: 3 })).toBeVisible();
  await expect(table.getByRole("columnheader")).toHaveText(TYPE_HEADERS);
  await expect(table.getByRole("columnheader", { name: "Template" })).toHaveCount(0); // the comparison above has the templates
  await expect(table.getByRole("columnheader", { name: "Next run" })).toHaveCount(0); // nothing is measured, so no column
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await expect(cells(table, 0)).toHaveText(["Main page", "120", "21.5 s", "3", "95.0%"], { useInnerText: true }); // not NEXTM's 10 or GPT's 4
  await expect(cells(table, 1)).toHaveText(["Coded page", "20", "8.0 s", "2", "75.0%"], { useInnerText: true });
  await expect(cells(table, 2)).toHaveText(["Notes page", "—", "—", "—", "not reviewed"], { useInnerText: true }); // not read by the set-up on the left
  await expect(cells(table, 2).nth(4).locator(".text-muted-foreground")).toHaveText("not reviewed");
  for (const [i, align] of [[0, "left"], [1, "right"], [2, "right"], [3, "right"], [4, "right"]] as const) {
    await expect(table.getByRole("columnheader").nth(i)).toHaveCSS("text-align", align);
    if (i >= 1) await expect(cells(table, 0).nth(i)).toHaveCSS("font-variant-numeric", "tabular-nums");
  }
  await expect(table.getByRole("button")).toHaveCount(0);
  await expect(table.locator("[data-slot=badge]")).toHaveCount(0);
  await expect(table.getByRole("progressbar")).toHaveCount(0);
});

test("By page type shows under Next run accuracy the pages reviewed with the next run's model, prompt and template, and not measured yet otherwise", async ({ page }) => {
  const NEXT = { ...NEXT_ROW, model: SAVED.model, effort: SAVED.effort, fields: 50, changed: 1 }; // 98.0%
  await mockApi(page, { models: [MODEL, { ...NEXTM, model: SAVED.model, effort: SAVED.effort }], accuracy: [{ ...ROW, pages: 5 }, NEXT, { ...NEXT, pageType: "coded", promptVersion: 2, templateVersion: 4 }] });
  await page.goto(OPEN);
  const table = byType(page);
  await expect(table.getByRole("columnheader")).toHaveText(NEXT_TYPE_HEADERS);
  await expect(table.locator("tbody tr").locator("td:last-child")).toHaveText(["98.0%", "not measured yet", "not measured yet"]); // coded was reviewed with an older prompt
  await expect(cells(table, 0).nth(4)).toHaveText("95.0%"); // the left's own, not the next run's
});

test("By page type counts large numbers with separators and says so when the time of the pages read wasn't recorded", async ({ page }) => {
  await mockApi(page, { models: [{ ...MODEL, pages: 2978, averageSeconds: 33.8 }, { ...CODED_READ, pages: 2721, averageSeconds: null }], accuracy: BOTH });
  await page.goto(OPEN);
  const table = byType(page);
  await expect(cells(table, 0)).toHaveText(["Main page", "2,978", "33.8 s", "3", "95.0%"], { useInnerText: true });
  await expect(cells(table, 1)).toHaveText(["Coded page", "2,721", "Not recorded", "2", "75.0%"], { useInnerText: true });
});

test("By page type has the page types of the set-up on the left first, in its order, then the others with a newest template in the series' order", async ({ page }) => {
  await mockApi(page, { models: [{ ...CODED_READ, pages: 500 }, { ...MODEL, pages: 10 }], accuracy: [] });
  await page.goto(OPEN);
  await expect(byType(page).locator("tbody tr").locator("td:first-child")).toHaveText(["Coded page", "Main page", "Notes page"]); // not Unknown, which has no template
  await expect(compare(page).getByRole("rowheader")).toHaveText(["Model", "Prompt", "Coded page template", "Main page template", "Notes page template", "Accuracy"]); // the comparison has them in that order
});

test("By page type has a row for a page type with a newest template even when nothing was read or reviewed", async ({ page }) => {
  await mockApi(page, { models: [], accuracy: [], types: [TYPES[1]] });
  await page.goto(OPEN);
  await expect(byType(page).locator("tbody tr")).toHaveCount(1);
  await expect(cells(byType(page), 0)).toHaveText(["Coded page", "—", "—", "—", "not reviewed"], { useInnerText: true });
  await expect(compare(page).getByRole("rowheader")).toHaveText(["Model", "Prompt", "Coded page template", "Accuracy"]);
});

test("All set-ups is offered from two set-ups, so the one not on the left stays reachable, and not with one", async ({ page }) => {
  await mockApi(page, { models: [MODEL], accuracy: [ROW] });
  await page.goto(OPEN);
  await expect(page.getByTestId("accuracy-percent")).toBeVisible();
  await expect(disclosure(page)).toHaveCount(0);
  await expect(page.getByText(/All set-ups/)).toHaveCount(0);
  await expect(allSetUps(page)).toHaveCount(0);
  await expect(byType(page)).toBeVisible();
  await mockApi(page, { models: [MODEL, NEXTM], accuracy: [ROW, NEXT_ROW] });
  await page.goto(OPEN);
  await expect(page.getByTestId("accuracy-percent")).toBeVisible();
  await expect(disclosure(page)).toHaveCount(1);
});

test("with more than one set-up All set-ups is a closed collapsible button that opens the table of every row", async ({ page }) => {
  await mockApi(page, { models: [MODEL, NEXTM, GPT], accuracy: [ROW, NEXT_ROW, CODED, NOTES] });
  await page.goto(OPEN);
  const trigger = disclosure(page);
  await expect(trigger).toHaveText("All set-ups (3)");
  await expect(trigger).toHaveAttribute("data-slot", "collapsible-trigger");
  await expect(trigger).toHaveAttribute("data-variant", "ghost");
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("details")).toHaveCount(0);
  await expect(allSetUps(page)).toBeHidden();
  expect(await y(trigger)).toBeGreaterThan(await y(byType(page)));
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  const table = allSetUps(page);
  await expect(table).toBeVisible();
  await expect(table.getByRole("columnheader")).toHaveText(["Page type", "Model", "Prompt", "Template", "Pages read", "Reviewed", "Accuracy", "Time per page"]);
  await expect(table.locator("tbody tr")).toHaveCount(5);
  await expect(cells(table, 0)).toHaveText(["Main page", "sonnet claude · low effort", "v2", "v2", "10", "4", "90.0%", "12.0 s"], { useInnerText: true });
  await expect(cells(table, 1)).toHaveText(["Main page", "gpt-x codex · Not recorded", "Not recorded", "v2", "4", "—", "Not reviewed", "Not recorded"], { useInnerText: true });
  await expect(cells(table, 2)).toHaveText(["Main page", "sonnet claude · low effort", "v1", "v1", "120", "3", "95.0%", "21.5 s"], { useInnerText: true });
  await expect(cells(table, 3)).toHaveText(["Coded page", "sonnet Not recorded · low effort", "v1", "v1", "—", "2", "75.0%", "—"], { useInnerText: true });
  await expect(cells(table, 4)).toHaveText(["Notes page", "gpt-x Not recorded · Not recorded", "Not recorded", "Not recorded", "—", "1", "100.0%", "—"], { useInnerText: true });
  await expect(cells(table, 0).nth(1).locator(".text-muted-foreground")).toHaveText("claude · low effort"); // under the model's name
  for (const [i, align] of [[0, "left"], [1, "left"], [2, "left"], [3, "left"], [4, "right"], [5, "right"], [6, "right"], [7, "right"]] as const) {
    await expect(table.getByRole("columnheader").nth(i)).toHaveCSS("text-align", align);
    if (i >= 4) await expect(cells(table, 0).nth(i)).toHaveCSS("font-variant-numeric", "tabular-nums");
  }
  await expect(table.getByRole("progressbar")).toHaveCount(0);
  await expect(table.locator("[data-slot=badge]")).toHaveCount(0);
  await expect(page.getByText("Names joined by")).toHaveCount(0);
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(table).toBeHidden();
});

test("a page type's rows are together in All set-ups, the one read most first, and in it the newest template first, then the newest prompt", async ({ page }) => {
  await mockApi(page, {
    models: [{ ...MODEL, pages: 10 }, { ...MODEL, templateVersion: 5, pages: 10 }, { ...MODEL, promptVersion: 7, templateVersion: 5, pages: 10 },
      { ...MODEL, promptVersion: 7, pages: 10 }, { ...CODED_READ, model: "opus", pages: 500 }],
    accuracy: [],
  });
  await page.goto(OPEN);
  await expect(disclosure(page)).toHaveText("All set-ups (3)"); // by model, effort and prompt: sonnet with two prompts, and opus
  await disclosure(page).click();
  const table = allSetUps(page);
  await expect(table.locator("tbody tr")).toHaveCount(5);
  const order = await Promise.all([0, 1, 2, 3, 4].map(async (i) => (await cells(table, i).allInnerTexts()).filter((_, c) => [0, 2, 3].includes(c)).join(" ").replace(/\s+/g, " ")));
  expect(order).toEqual([
    "Coded page v1 v1",
    "Main page v2 v2", // template v2, prompt v2
    "Main page v1 v2", // template v2, prompt v1
    "Main page v2 v1", // template v1, prompt v2
    "Main page v1 v1",
  ]);
});

test("a name joined by + is explained under the All set-ups table, and only then", async ({ page }) => {
  await mockApi(page, { accuracy: [ROW], models: [MODEL, NEXTM, { ...MODEL, model: "sonnet+haiku" }] });
  await page.goto(OPEN);
  await disclosure(page).click();
  await expect(page.getByText("Names joined by")).toHaveText("Names joined by “+” indicate multiple models reported for a transcription, rather than one selectable model.");
});

test("two providers of one model, effort and versions are one set-up: pages added, the time weighted by the timed pages, the providers named", async ({ page }) => {
  await mockApi(page, {
    models: [{ ...MODEL, pages: 100, averageSeconds: 20 }, { ...MODEL, pages: 50, averageSeconds: 8 },
      { ...MODEL, provider: "codex", pages: 30, averageSeconds: null }, // no timing: its pages count, its time doesn't
      { ...MODEL, model: "opus", pages: 1 }, { ...MODEL, model: "haiku", pages: 1 }],
    accuracy: [ROW],
  });
  await page.goto(OPEN);
  await expect(leftOf(page, "Model")).toHaveText("sonnet · claude, codex · low effort");
  await expect(cells(byType(page), 0)).toHaveText(["Main page", "180", "16.0 s", "3", "95.0%"], { useInnerText: true }); // (100 × 20 + 50 × 8) / 150, not / 180
  await expect(disclosure(page)).toHaveText("All set-ups (3)");
  await disclosure(page).click();
  const table = allSetUps(page);
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await expect(cells(table, 0)).toHaveText(["Main page", "sonnet claude, codex · low effort", "v1", "v1", "180", "3", "95.0%", "16.0 s"], { useInnerText: true });
});

test("the set-ups wait for the versions: while they load nothing is split by a page type not yet known, and then there is one", async ({ page }) => {
  const calls = await mockApi(page, { holdVersions: true, models: [MODEL], accuracy: [ROW] });
  await page.goto(OPEN);
  await expect(rightOf(page, "Model")).toContainText("claude-saved-model"); // the models have arrived
  await expect(page.getByRole("status")).toHaveText("Loading accuracy…");
  await expect(leftOf(page, "Accuracy")).toHaveText("Loading accuracy…");
  await expect(page.getByTestId("accuracy-percent")).toHaveCount(0);
  await expect(byType(page)).toHaveCount(0);
  await expect(page.getByText("Not recorded")).toHaveCount(0); // the name of a page type that isn't known
  await expect(compare(page).getByRole("rowheader")).toHaveText(["Model", "Prompt", "Templates", "Accuracy"]); // no page type is known to have a row
  await expect(leftOf(page, "Model")).toHaveText("Loading…");
  await expect(rightOf(page, "Prompt")).toHaveText("Loading…");
  await expect(notMeasured(page)).toHaveCount(0);
  await expect(actionOf(page, "Templates").getByRole("link", { name: "Edit templates" })).toBeVisible();
  calls.releaseVersions();
  await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%");
  await expect(cells(byType(page), 0)).toHaveText(["Main page", "120", "21.5 s", "3", "95.0%"], { useInnerText: true });
  await expect(compare(page).getByRole("rowheader")).toHaveText(["Model", "Prompt", "Main page template", "Coded page template", "Notes page template", "Accuracy"]);
  await expect(page.getByText("Not recorded")).toHaveCount(0);
  await expect(page.getByRole("status")).toHaveCount(1); // only the note of too few pages
  await expect(page.getByRole("status")).toHaveText(/^Too few pages/);
});

test("a version's button opens its text, and says which version pages are read with from now on", async ({ page }) => {
  await mockApi(page, { accuracy: [ROW], models: [MODEL] });
  await page.goto(OPEN);
  const button = (side: typeof leftOf, row: string, name: string) => side(page, row).getByRole("button", { name, exact: true });

  await button(rightOf, "Main page template", "Main page template v2").click();
  const newest = page.getByRole("dialog", { name: "Main page template" });
  await expect(chosen(newest)).toContainText("v2");
  await expect(newest).toContainText('{"address": null, "number_of_dwelling": null}');
  await expect(field(newest, "Last updated")).not.toHaveText("Not recorded");
  await expect(field(newest, "By")).toHaveText("Ben");
  await expect(field(newest, "Status")).toHaveText("Current: pages read from now on use this version");
  await expect(field(newest, "Note")).toHaveText("dwelling added");
  await page.keyboard.press("Escape");
  await expect(newest).toHaveCount(0);

  await button(rightOf, "Prompt", "Prompt v2").click();
  const prompt = page.getByRole("dialog", { name: "Prompt" });
  await expect(chosen(prompt)).toContainText("v2");
  await expect(prompt).toContainText("Read the page as JSON, carefully.");
  await expect(terms(prompt)).toHaveText(["Last updated", "By", "Status"]); // no note, no row
  await expect(field(prompt, "Last updated")).toHaveText("Not recorded");
  await expect(field(prompt, "By")).toHaveText("From the files");
  await expect(field(prompt, "Status")).toHaveText("Current: pages read from now on use this version");
  await expect(prompt.getByRole("textbox")).toHaveCount(0); // the prompt is only viewed
  await page.keyboard.press("Escape");
  await expect(prompt).toHaveCount(0);

  await button(leftOf, "Main page template", "Main page template v1").click();
  const older = page.getByRole("dialog", { name: "Main page template" });
  await expect(chosen(older)).toContainText("v1");
  await expect(older).toContainText('{"address": null}');
  await expect(field(older, "Status")).toHaveText("Replaced by v2");
  await expect(terms(older)).toHaveText(["Last updated", "By", "Status"]);
  await page.keyboard.press("Escape");
  await expect(older).toHaveCount(0);

  await button(leftOf, "Prompt", "Prompt v1").click();
  const oldPrompt = page.getByRole("dialog", { name: "Prompt" });
  await expect(chosen(oldPrompt)).toContainText("v1");
  await expect(oldPrompt).toContainText("Read the page as JSON.");
  await expect(field(oldPrompt, "Status")).toHaveText("Replaced by v2");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(compare(page).getByRole("button")).toHaveCount(7); // closing it leaves the table as it was: the prompt twice and View, and the main template twice, coded and notes
  await expect(byType(page).getByRole("button")).toHaveCount(0);

  await button(rightOf, "Coded page template", "Coded page template v1").click();
  await expect(page.getByRole("dialog", { name: "Coded page template" })).toContainText("coded text 1");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

// The Main page template with three versions of known text, its page type naming the third the newest; the prompt has two.
const MAIN_V1 = "title\naddress\nowner\nrent";
const MAIN_V2 = "title\naddress\nowner\ndwellings\nrent";
const MAIN_V3 = "title\naddress\noccupier\ndwellings\nrent\nnotes";
const HISTORY = [
  version(2, "prompt", "Prompt", 1, { current: false, body: "Read the page as JSON." }),
  version(3, "main", "Main page", 1, { current: false, body: MAIN_V1 }),
  version(5, "main", "Main page", 2, { current: false, body: MAIN_V2, reviewer: "Ben", note: "dwellings added", createdAt: "2026-10-01T02:00:00+00:00" }),
  version(7, "prompt", "Prompt", 2, { body: "Read the page as JSON, carefully." }),
  version(8, "main", "Main page", 3, { body: MAIN_V3, reviewer: "Sandy", note: "owner is now occupier", createdAt: "2026-10-05T03:30:00+00:00" }),
];
const HISTORY_TYPES = [type("main", "Main page", 8)];
const when = (page: Page, iso: string) => page.evaluate((s) => new Date(s).toLocaleString(), iso);
const newestMain = (page: Page) => rightOf(page, "Main page template").getByRole("button", { name: "Main page template v3", exact: true });
const oldestMain = (page: Page) => leftOf(page, "Main page template").getByRole("button", { name: "Main page template v1", exact: true });

// Opens the Main page template at its newest version, from its button in the Next run column.
async function openHistory(page: Page, versions: object[] = HISTORY) {
  await mockApi(page, { accuracy: [ROW], models: [MODEL], versions, types: HISTORY_TYPES });
  await page.goto(OPEN);
  await newestMain(page).click();
  const dialog = page.getByRole("dialog", { name: "Main page template", exact: true });
  let last = "";
  await expect.poll(async () => { const now = JSON.stringify(await dialog.boundingBox()); const still = now === last; last = now; return still; }).toBe(true); // it has stopped opening
  return dialog;
}
const versionList = (dialog: Locator) => dialog.getByRole("group", { name: "Versions" });
const changesFrom = (dialog: Locator, n: number) => dialog.getByRole("group", { name: `Changes from v${n}` });
const lines = (group: Locator) => group.locator(":scope > div").allTextContents(); // raw, so a line's sign and spaces count
const showChanges = (dialog: Locator, n: number) => dialog.getByRole("switch", { name: `Show changes from v${n}` });

test("a version's dialog is named for the thing, not one version, and is wide", async ({ page }) => {
  const dialog = await openHistory(page);
  await expect(dialog.getByRole("heading")).toHaveText("Main page template");
  await expect(dialog).toBeFocused(); // focus starts on the dialog, not on a version
  const box = (await dialog.boundingBox())!;
  expect(box.width).toBeGreaterThan(900);
  expect(box.width).toBeLessThanOrEqual(1025);
  await page.keyboard.press("Escape");
  await rightOf(page, "Prompt").getByRole("button", { name: "Prompt v2", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Prompt", exact: true }).getByRole("heading")).toHaveText("Prompt");
});

test("the history lists the versions of its kind newest first as buttons, the one clicked chosen, the newest Current, with when, by whom and the note", async ({ page }) => {
  const dialog = await openHistory(page);
  const list = versionList(dialog);
  const buttons = list.getByRole("button");
  await expect(buttons).toHaveCount(3); // not the prompt's
  for (const [i, number] of [3, 2, 1].entries()) await expect(buttons.nth(i).getByText(/^v\d$/)).toHaveText(`v${number}`);
  for (const [i, pressed] of ["true", "false", "false"].entries()) await expect(buttons.nth(i)).toHaveAttribute("aria-pressed", pressed);
  for (const [i, variant] of ["secondary", "ghost", "ghost"].entries()) {
    await expect(buttons.nth(i)).toHaveAttribute("data-slot", "button"); // the chosen one is the secondary variant
    await expect(buttons.nth(i)).toHaveAttribute("data-variant", variant);
  }
  await expect(list.locator("button:not([data-slot=button])")).toHaveCount(0);
  await expect(list.locator("[data-slot=badge]")).toHaveCount(1);
  await expect(buttons.first().locator("[data-slot=badge]")).toHaveText("Current");
  await expect(buttons.nth(0)).toContainText(`${await when(page, "2026-10-05T03:30:00+00:00")} by Sandy`);
  await expect(buttons.nth(1)).toContainText(`${await when(page, "2026-10-01T02:00:00+00:00")} by Ben`);
  await expect(buttons.nth(2)).toContainText("from the files");
  await expect(buttons.nth(2)).not.toContainText("by ");
  const note = buttons.nth(0).getByText("owner is now occupier", { exact: true });
  await expect(note).toHaveClass(/text-muted-foreground/);
  expect(await y(note)).toBeGreaterThan(await y(buttons.nth(0).getByText("v3", { exact: true })));
  await expect(buttons.nth(1).getByText("dwellings added", { exact: true })).toBeVisible();
  await expect(buttons.nth(2)).not.toContainText(/\d\d/); // no date
  await expect(buttons.nth(2).locator("[data-slot=badge]")).toHaveCount(0);
});

test("choosing a version shows its text and its fields, the title staying, and the dialog opens on the version clicked", async ({ page }) => {
  const dialog = await openHistory(page);
  const [buttons, pre] = [versionList(dialog).getByRole("button"), dialog.locator("pre")];
  expect(await pre.textContent()).toBe(MAIN_V3);
  await expect(dialog.locator("dl")).toHaveCount(1);
  await expect(terms(dialog)).toHaveText(["Last updated", "By", "Status", "Note"]);
  await expect(terms(dialog).first()).toHaveClass(/text-muted-foreground/);
  await expect(field(dialog, "Last updated")).toHaveText(await when(page, "2026-10-05T03:30:00+00:00"));
  await expect(field(dialog, "By")).toHaveText("Sandy");
  await expect(field(dialog, "Status")).toHaveText("Current: pages read from now on use this version");
  await expect(field(dialog, "Note")).toHaveText("owner is now occupier");
  await expect(dialog.locator("[data-slot=dialog-description]")).toHaveCount(0); // the list is not a sentence
  await expect(dialog.getByText(/^Saved /)).toHaveCount(0);

  await buttons.nth(1).click();
  await expect(buttons.nth(1)).toHaveAttribute("aria-pressed", "true");
  await expect(buttons.nth(0)).toHaveAttribute("aria-pressed", "false");
  expect(await pre.textContent()).toBe(MAIN_V2);
  await expect(field(dialog, "Last updated")).toHaveText(await when(page, "2026-10-01T02:00:00+00:00"));
  await expect(field(dialog, "By")).toHaveText("Ben");
  await expect(field(dialog, "Status")).toHaveText("Replaced by v3");
  await expect(field(dialog, "Note")).toHaveText("dwellings added");
  await expect(dialog.locator("dl")).not.toContainText("owner is now occupier"); // the history still has it, on v3

  await buttons.nth(2).click();
  expect(await pre.textContent()).toBe(MAIN_V1);
  await expect(terms(dialog)).toHaveText(["Last updated", "By", "Status"]); // no note, no row
  await expect(field(dialog, "Last updated")).toHaveText("Not recorded");
  await expect(field(dialog, "By")).toHaveText("From the files");
  await expect(field(dialog, "Status")).toHaveText("Replaced by v3");
  await expect(dialog.getByRole("heading")).toHaveText("Main page template");
  await expect(page.getByRole("dialog")).toHaveCount(1);

  await page.keyboard.press("Escape"); // reopening goes to the version clicked, not the one last chosen
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await newestMain(page).click();
  await expect(chosen(dialog)).toContainText("v3");
  await page.keyboard.press("Escape");
  await oldestMain(page).click();
  await expect(chosen(dialog)).toContainText("v1");
  await expect(field(dialog, "Status")).toHaveText("Replaced by v3");
});

test("the switch offers changes from the version before, and is disabled as First version on the first", async ({ page }) => {
  const dialog = await openHistory(page);
  const buttons = versionList(dialog).getByRole("button");
  for (const [i, from] of [[0, 2], [1, 1]] as const) {
    await buttons.nth(i).click();
    await expect(showChanges(dialog, from)).toBeEnabled();
    await expect(showChanges(dialog, from)).not.toBeChecked();
    await expect(showChanges(dialog, from)).toHaveAttribute("data-slot", "switch");
    await expect(dialog.locator("label[data-slot=label]")).toHaveText(`Show changes from v${from}`);
    await expect(dialog.getByText("First version")).toHaveCount(0);
  }
  await buttons.nth(2).click();
  const first = dialog.getByRole("switch", { name: "First version", exact: true });
  await expect(first).toBeDisabled();
  await expect(first).not.toBeChecked();
  await expect(dialog.getByRole("switch")).toHaveCount(1);
  await expect(dialog.getByRole("checkbox")).toHaveCount(0);
  await expect(dialog.getByRole("switch", { name: /Show changes/ })).toHaveCount(0);
  await expect(dialog.locator("label[data-slot=label]")).toHaveClass(/text-muted-foreground/);
  await expect(dialog.locator("pre")).toBeVisible();
  await buttons.nth(0).click();
  await dialog.getByText("Show changes from v2", { exact: true }).click(); // its label turns it on
  await expect(showChanges(dialog, 2)).toBeChecked();
});

test("with changes on, the text is lines removed on red, added on green and unchanged muted, with the count above, against the version before", async ({ page }) => {
  const dialog = await openHistory(page);
  await showChanges(dialog, 2).check();
  await expect(dialog.locator("pre")).toHaveCount(0);
  const diff = changesFrom(dialog, 2);
  expect(await lines(diff)).toEqual(["  title", "  address", "- owner", "+ occupier", "  dwellings", "  rent", "+ notes"]);
  await expect(dialog.getByText("+2 −1 lines", { exact: true })).toBeVisible();
  expect(await y(dialog.getByText("+2 −1 lines", { exact: true }))).toBeLessThan(await y(diff));
  const row = (text: string) => diff.getByText(text, { exact: true });
  await expect(row("- owner")).toHaveClass(/bg-red-100/);
  await expect(row("+ occupier")).toHaveClass(/bg-green-100/);
  await expect(row("+ notes")).toHaveClass(/bg-green-100/);
  for (const same of ["title", "rent"]) {
    const unchanged = diff.locator(":scope > div").filter({ hasText: new RegExp(`^\\s*${same}$`) });
    await expect(unchanged).toHaveClass(/text-muted-foreground/);
    await expect(unchanged).not.toHaveClass(/bg-(red|green)/);
  }
  expect(await y(row("- owner"))).toBeLessThan(await y(row("+ occupier"))); // the removed line comes first

  const buttons = versionList(dialog).getByRole("button");
  await buttons.nth(1).click(); // v2 against v1; the switch stays on
  await expect(showChanges(dialog, 1)).toBeChecked();
  expect(await lines(changesFrom(dialog, 1))).toEqual(["  title", "  address", "  owner", "+ dwellings", "  rent"]);
  await expect(dialog.getByText("+1 −0 lines", { exact: true })).toBeVisible();

  await buttons.nth(2).click(); // nothing before v1: the plain text, the switch disabled
  await expect(dialog.getByRole("switch", { name: "First version" })).toBeDisabled();
  expect(await dialog.locator("pre").textContent()).toBe(MAIN_V1);
  await expect(dialog.getByText(/ lines$/)).toHaveCount(0);

  await buttons.nth(0).click(); // and back: still on
  await expect(showChanges(dialog, 2)).toBeChecked();
  expect(await lines(changesFrom(dialog, 2))).toHaveLength(7);
  await showChanges(dialog, 2).uncheck();
  await expect(dialog.locator("pre")).toBeVisible();
  await expect(changesFrom(dialog, 2)).toHaveCount(0);
  await buttons.nth(1).click();
  await expect(showChanges(dialog, 1)).not.toBeChecked(); // off stays off
  await expect(dialog.locator("pre")).toBeVisible();
});

test("the switch starts off at every opening, however it was left, and stays as set while another version is chosen within one", async ({ page }) => {
  const dialog = await openHistory(page);
  await expect(showChanges(dialog, 2)).not.toBeChecked();
  await showChanges(dialog, 2).check();
  await expect(changesFrom(dialog, 2)).toBeVisible();
  await versionList(dialog).getByRole("button").nth(1).click();
  await expect(showChanges(dialog, 1)).toBeChecked(); // kept within the opening
  await versionList(dialog).getByRole("button").nth(0).click();
  await expect(showChanges(dialog, 2)).toBeChecked();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await newestMain(page).click(); // open, switch on, close, reopen: off
  await expect(showChanges(dialog, 2)).not.toBeChecked();
  await expect(dialog.locator("pre")).toBeVisible();
  await expect(changesFrom(dialog, 2)).toHaveCount(0);
  await showChanges(dialog, 2).check();
  await expect(changesFrom(dialog, 2)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await rightOf(page, "Prompt").getByRole("button", { name: "Prompt v2", exact: true }).click(); // another dialog is off too
  const prompt = page.getByRole("dialog", { name: "Prompt", exact: true });
  await expect(prompt.getByRole("switch", { name: "Show changes from v1" })).not.toBeChecked();
  await prompt.getByRole("switch").check();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await oldestMain(page).click(); // from the oldest version, then to a newer one
  await expect(dialog.getByRole("switch", { name: "First version" })).toBeDisabled();
  await versionList(dialog).getByRole("button").nth(1).click();
  await expect(showChanges(dialog, 1)).not.toBeChecked();
  await expect(dialog.locator("pre")).toBeVisible();
});

const numbered = (n: number, edited: number[] = []) => Array.from({ length: n }, (_, i) => `line ${i + 1}${edited.includes(i + 1) ? " edited" : ""}`).join("\n");
const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => `  line ${from + i}`);
const edit = (n: number) => [`- line ${n}`, `+ line ${n} edited`];
for (const [name, before, after, expected, summary] of [
  ["a change between long runs folds each run to three lines beside it", numbered(30), numbered(30, [5, 25]),
    [...range(1, 4), ...edit(5), ...range(6, 8), "⋯ 13 unchanged lines", ...range(22, 24), ...edit(25), ...range(26, 30)], "+2 −2 lines"],
  ["a long run at an end keeps its three lines beside the change only", numbered(30), numbered(30, [15]),
    ["⋯ 11 unchanged lines", ...range(12, 14), ...edit(15), ...range(16, 18), "⋯ 12 unchanged lines"], "+1 −1 lines"],
  ["a run of six stays whole and a run of seven folds", numbered(16), numbered(16, [1, 8, 16]),
    [...edit(1), ...range(2, 7), ...edit(8), ...range(9, 11), "⋯ 1 unchanged line", ...range(13, 15), ...edit(16)], "+3 −3 lines"],
  ["text with nothing changed is one marker", numbered(30), numbered(30), ["⋯ 30 unchanged lines"], "+0 −0 lines"],
  ["CRLF in one text and LF in the other make no changes of their own", "a\r\nb\r\nc", "a\nb\nc\nd", ["  a", "  b", "  c", "+ d"], "+1 −0 lines"],
  ["the same text in CRLF and in LF has no changes", "a\r\nb\r\nc", "a\nb\nc", ["  a", "  b", "  c"], "+0 −0 lines"],
  ["lines that repeat are matched by the longest common run", "a\nb\na\nb", "b\na\nb\na", ["- a", "  b", "  a", "  b", "+ a"], "+1 −1 lines"],
  ["a blank line is a line", "a\n\nb", "a\n\nc", ["  a", "  ", "- b", "+ c"], "+1 −1 lines"],
  ["an empty text has no lines, so the text after it is only added", "", "x\ny\nz", ["+ x", "+ y", "+ z"], "+3 −0 lines"],
  ["a text emptied is only removed", "x\ny", "", ["- x", "- y"], "+0 −2 lines"],
  ["two empty texts have no lines", "", "", [], "+0 −0 lines"],
  ["a newline at the end ends the last line and adds none", "a\nb\n", "a\nb\nc\n", ["  a", "  b", "+ c"], "+1 −0 lines"],
  ["the same text with and without a newline at the end has no changes", "a\nb\n", "a\nb", ["  a", "  b"], "+0 −0 lines"],
  ["a CRLF at the end ends the last line too", "a\r\nb\r\n", "a\nb", ["  a", "  b"], "+0 −0 lines"],
  ["a second newline at the end is a blank line", "a\n", "a\n\n", ["  a", "+ "], "+1 −0 lines"],
  ["a lone newline is one blank line", "", "\n", ["+ "], "+1 −0 lines"],
] as [string, string, string, string[], string][]) {
  test(`with changes on, ${name}`, async ({ page }) => {
    await mockApi(page, { accuracy: [ROW], models: [MODEL],
      versions: [version(2, "prompt", "Prompt", 1, { current: false, body: before }), version(7, "prompt", "Prompt", 2, { body: after })] });
    await page.goto(OPEN);
    await rightOf(page, "Prompt").getByRole("button", { name: "Prompt v2", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Prompt", exact: true });
    await showChanges(dialog, 1).check();
    expect(await lines(changesFrom(dialog, 1))).toEqual(expected);
    await expect(dialog.getByText(summary, { exact: true })).toBeVisible();
  });
}

test("on a phone the history sits above the text, and the dialog with its changes fits the width", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const wide = HISTORY.map((v) => (v.kind === "main" ? { ...v, body: `${v.body}\n${"x".repeat(150)} ${v.number} ${"y".repeat(150)}`, note: v.note && `${v.note} ${"n".repeat(120)}` } : v));
  const dialog = await openHistory(page, wide);
  await expect(dialog).toBeVisible();
  await showChanges(dialog, 2).check();
  const diff = changesFrom(dialog, 2);
  await expect(diff).toBeVisible();
  const [list, check, box] = [(await versionList(dialog).boundingBox())!, (await showChanges(dialog, 2).boundingBox())!, (await dialog.boundingBox())!];
  expect(list.y + list.height).toBeLessThanOrEqual(check.y + 1); // above the text, not beside it
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(375);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(812);
  expect(await noSidewaysScroll(page)).toBe(true);
  for (const part of [dialog, diff, versionList(dialog), dialog.locator("dl")]) expect(await part.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  await showChanges(dialog, 2).uncheck();
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true); // a long word scrolls inside the text, not the dialog
  expect(await noSidewaysScroll(page)).toBe(true);
});

test("on a wide screen the history is beside the text, on its left", async ({ page }) => {
  const dialog = await openHistory(page);
  const [list, check] = [(await versionList(dialog).boundingBox())!, (await showChanges(dialog, 2).boundingBox())!];
  expect(list.x + list.width).toBeLessThanOrEqual(check.x + 1);
  expect(Math.abs(list.y - (await y(dialog.locator("dl"))))).toBeLessThan(2);
});

test("accuracy that can't be loaded says so, and the models, versions and what was read still show", async ({ page }) => {
  await mockApi(page, { accuracy: null, models: [MODEL] });
  await page.goto(OPEN);
  await expect(page.getByRole("alert")).toHaveText("Accuracy could not be loaded.");
  await expect(page.getByTestId("accuracy-percent")).toHaveCount(0);
  await expect(page.getByText("No reviewed pages yet")).toHaveCount(0); // that isn't known
  await expect(leftOf(page, "Model")).toHaveText("sonnet · claude · low effort");
  await expect(leftOf(page, "Accuracy")).toHaveText("—");
  await expect(rightOf(page, "Accuracy")).toHaveText("—");
  await expect(cells(byType(page), 0)).toHaveText(["Main page", "120", "21.5 s", "—", "—"], { useInnerText: true }); // not reviewed isn't known either
  await expect(actionOf(page, "Accuracy").getByRole("link", { name: "Review more pages" })).toBeVisible();
  await expect(rightOf(page, "Prompt").getByRole("button")).toHaveText("v2");
  await expect(notMeasured(page)).toHaveCount(0); // nor is that
  await expect(page.getByRole("status")).toHaveCount(0);
  await expect(actionOf(page, "Model").getByRole("link", { name: "Change model" })).toBeVisible();
});

test("models that can't be loaded say so, and the accuracy, the prompt and templates and the reviewed rows still show", async ({ page }) => {
  await mockApi(page, { accuracy: BOTH, models: null });
  await page.goto(OPEN);
  await expect(page.getByRole("alert")).toHaveText("The models could not be loaded.");
  await expect(rightOf(page, "Model")).toHaveText("Not loaded");
  await expect(actionOf(page, "Model").getByRole("link", { name: "Change model" })).toHaveAttribute("href", "/?view=settings&tab=transcription");
  await expect(rightOf(page, "Prompt").getByRole("button")).toHaveText("v2");
  for (const row of ["Main page template", "Coded page template", "Notes page template"]) await expect(rightOf(page, row).getByRole("button")).toHaveCount(1);
  await expect(page.getByTestId("accuracy-percent")).toHaveText("90.0%");
  await expect(leftOf(page, "Accuracy")).toContainText("(8 of 80 fields, 5 pages)");
  await expect(rightOf(page, "Accuracy")).toHaveText("—");
  await expect(leftOf(page, "Model")).toHaveText("sonnet · provider not recorded · low effort");
  await expect(cells(byType(page), 0)).toHaveText(["Coded page", "—", "—", "2", "75.0%"], { useInnerText: true }); // the next run's accuracy can't be told
  await expect(cells(byType(page), 1)).toHaveText(["Main page", "—", "—", "3", "95.0%"], { useInnerText: true });
  await expect(notMeasured(page)).toHaveCount(0);
});

test("versions that can't be loaded say so above everything, show the prompt and templates as not loaded, and All set-ups shows the ids", async ({ page }) => {
  await mockApi(page, { versions: null, models: [MODEL, NEXTM, GPT], accuracy: [ROW] });
  await page.goto(OPEN);
  await expect(page.getByRole("alert")).toHaveText("The prompt and template versions could not be loaded.");
  expect(await y(page.getByRole("alert"))).toBeLessThan(await y(page.getByRole("heading", { level: 2 })));
  await expect(compare(page).getByRole("rowheader")).toHaveText(["Model", "Prompt", "Main page template", "Accuracy"]); // the page types known without the versions
  for (const row of ["Prompt", "Main page template"]) {
    await expect(leftOf(page, row)).toHaveText("Not loaded");
    await expect(rightOf(page, row)).toHaveText("Not loaded");
  }
  await expect(compare(page).getByRole("button")).toHaveCount(0); // no prompt to view, no version to open
  await expect(rightOf(page, "Model")).toContainText("claude-saved-model · claude · high effort");
  await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%");
  await expect(rightOf(page, "Accuracy")).toHaveText("—");
  await expect(notMeasured(page)).toHaveCount(0);
  await expect(actionOf(page, "Model").getByRole("link", { name: "Change model" })).toBeVisible();
  await expect(actionOf(page, "Main page template").getByRole("link", { name: "Edit templates" })).toHaveAttribute("href", "/?series=1&view=setup");
  await disclosure(page).click();
  await expect(byType(page).getByRole("button")).toHaveCount(0);
  await expect(cells(byType(page), 0)).toHaveText(["Not recorded", "120", "21.5 s", "—", "not reviewed"], { useInnerText: true });
  await expect(cells(byType(page), 1)).toHaveText(["Main page", "—", "—", "3", "95.0%"], { useInnerText: true });
  await expect(allSetUps(page).getByRole("button")).toHaveCount(0);
  const reviewed = allSetUps(page).locator("tbody tr").filter({ hasText: "95.0%" }).getByRole("cell");
  await expect(reviewed).toHaveText(["Main page", "sonnet Not recorded · low effort", "2", "3", "—", "3", "95.0%", "—"], { useInnerText: true }); // the template's id
});

test("page types that can't be loaded say so, show the next run's templates as not loaded, and still link to Edit templates", async ({ page }) => {
  await mockApi(page, { types: null, models: [NEXTM], accuracy: [ROW] });
  await page.goto(OPEN);
  await expect(page.getByRole("alert")).toHaveText("The page types could not be loaded.");
  await expect(compare(page).getByRole("rowheader")).toHaveText(["Model", "Prompt", "Main page template", "Accuracy"]); // only the page types of the set-up on the left
  await expect(leftOf(page, "Main page template").getByRole("button")).toHaveText("v1"); // named by its versions' label
  await expect(rightOf(page, "Main page template")).toHaveText("Not loaded");
  await expect(rightOf(page, "Prompt").getByRole("button")).toHaveText("v2");
  await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%");
  await expect(rightOf(page, "Accuracy")).toHaveText("—");
  await expect(notMeasured(page)).toHaveCount(0);
  await expect(byType(page).locator("tbody tr")).toHaveCount(1); // only the page types of the set-up on the left
  await expect(cells(byType(page), 0)).toHaveText(["Main page", "—", "—", "3", "95.0%"], { useInnerText: true });
  await expect(actionOf(page, "Main page template").getByRole("link", { name: "Edit templates" })).toHaveAttribute("href", "/?series=1&view=setup");
  await expect(actionOf(page, "Model").getByRole("link", { name: "Change model" })).toBeVisible();
});

test("page types and versions that both can't be loaded say so, and Change model, Edit templates and Review more pages are still there", async ({ page }) => {
  await mockApi(page, { types: null, versions: null, models: [MODEL], accuracy: [ROW] });
  await page.goto(OPEN);
  await expect(page.getByRole("alert")).toHaveText(["The prompt and template versions could not be loaded.", "The page types could not be loaded."]);
  await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%");
  await expect(leftOf(page, "Prompt")).toHaveText("Not loaded");
  await expect(actionOf(page, "Model").getByRole("link", { name: "Change model" })).toHaveAttribute("href", "/?view=settings&tab=transcription");
  await expect(compare(page).getByRole("link", { name: "Edit templates" })).toHaveAttribute("href", "/?series=1&view=setup");
  await expect(actionOf(page, "Accuracy").getByRole("link", { name: "Review more pages" })).toHaveAttribute("href", "/?series=1");
});

test("a series that can't be loaded says so, and the rest still shows", async ({ page }) => {
  await mockApi(page, { series: null, models: [MODEL], accuracy: [ROW] });
  await page.goto(OPEN);
  await expect(page.getByRole("alert")).toHaveText("The series could not be loaded.");
  await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%");
  await expect(actionOf(page, "Main page template").getByRole("link", { name: "Edit templates" })).toBeVisible();
});

test("while accuracy and the models load it says so", async ({ page }) => {
  const calls = await mockApi(page, { hold: true, models: [MODEL], accuracy: [ROW] });
  await page.goto(OPEN);
  await expect(page.getByRole("status")).toHaveText(["Loading models…", "Loading accuracy…"]);
  await expect(rightOf(page, "Model").getByRole("status")).toHaveText("Loading models…");
  await expect(leftOf(page, "Accuracy").getByRole("status")).toHaveText("Loading accuracy…");
  await expect(leftOf(page, "Model")).toHaveText("Loading…");
  await expect(rightOf(page, "Accuracy")).toHaveText("Loading…");
  await expect(page.getByTestId("accuracy-percent")).toHaveCount(0);
  await expect(notMeasured(page)).toHaveCount(0);
  await expect(actionOf(page, "Accuracy").getByRole("link", { name: "Review more pages" })).toBeVisible();
  await expect(actionOf(page, "Templates").getByRole("link", { name: "Edit templates" })).toBeVisible();
  calls.release();
  await expect(page.getByTestId("accuracy-percent")).toHaveText("95.0%");
  await expect(page.getByRole("status").filter({ hasText: /^Loading/ })).toHaveCount(0);
  await expect(page.getByText(/^Loading/)).toHaveCount(0);
  await expect(rightOf(page, "Model")).toContainText("claude-saved-model");
});

test("on a phone the table scrolls inside its own container and nothing scrolls the page sideways", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockApi(page, {
    models: [{ ...MODEL, model: LONG }, GPT, NEXTM, CODED_READ],
    accuracy: [{ ...ROW, model: LONG, pages: 10 }, CODED, NOTES, NEXT_ROW],
    configured: { ...SAVED, model: LONG + "-saved" },
  });
  await page.goto(OPEN);
  await expect(page.getByTestId("accuracy-percent")).toBeVisible();
  await expect(leftOf(page, "Model")).toContainText(LONG);
  expect(await noSidewaysScroll(page)).toBe(true);
  await disclosure(page).click();
  await expect(allSetUps(page)).toBeVisible();
  expect(await noSidewaysScroll(page)).toBe(true);
  for (const [table, scrolls] of [[compare(page), true], [byType(page), false], [allSetUps(page), true]] as const) {
    const container = table.locator("xpath=..");
    await expect(container).toHaveAttribute("data-slot", "table-container");
    const box = (await container.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(375);
    if (scrolls) expect(await container.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true); // the table scrolls in it
  }
  const action = actionOf(page, "Accuracy").getByRole("link", { name: "Review more pages" });
  await action.scrollIntoViewIfNeeded();
  await expect(action).toBeVisible();
});

test("a version's text fits a phone's width", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockApi(page, { versions: [version(2, "prompt", "Prompt", 1, { body: "word ".repeat(400) })], models: [MODEL], accuracy: [ROW] });
  await page.goto(OPEN);
  await leftOf(page, "Prompt").getByRole("button", { name: "Prompt v1", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Prompt" });
  await expect(dialog).toBeVisible();
  const box = (await dialog.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(375);
  expect(await noSidewaysScroll(page)).toBe(true);
});
