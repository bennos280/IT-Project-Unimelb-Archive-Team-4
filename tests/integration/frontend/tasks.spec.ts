import { test, expect, type Page } from "@playwright/test";
import { serveItems } from "./items-mock";

// The Tasks link in the header, the Tasks page (each task with its series' name) and the dashboard's banner follow GET /api/jobs. The API is intercepted: nothing reaches a real backend.
type Task = {
  id: number; kind: "items" | "bundle" | "page" | "train"; label: string; status: "waiting" | "running" | "done" | "failed";
  step: string | null; done: number; total: number; unit: "items" | "pages"; error: string | null;
  updatedAt: string; collectionId: number | null; series: string | null; href: string | null;
};
const task = (extra: Partial<Task>): Task => ({
  id: 1, kind: "items", label: "Adding items", status: "running", step: "adding", done: 0, total: 0, unit: "items", error: null,
  updatedAt: "2026-10-19T03:04:05+00:00", collectionId: 2, series: "Missing, Wounded and Prisoner Of War Cards", href: "/?collection=2",
  ...extra,
});
const ADDING = task({
  id: 31, label: "Adding Missing, Wounded and Prisoner Of War Cards' items", done: 12400, total: 60772,
});
const TRANSCRIBING = task({
  id: 32, kind: "bundle", label: "Transcribing Box Hill 00", step: "transcribe", done: 40, total: 227, unit: "pages",
  collectionId: 1, series: "Wilfred Prest Survey", href: "/?collection=1&bundle=216412",
});
const QUEUED = task({ id: 33, label: "Adding Shipping manifests' items matching \"Davis\"", status: "waiting", step: null, collectionId: 3, series: "Shipping manifests",
  href: "/?collection=3" });
const READING = task({ id: 35, kind: "page", label: "Reading page 216412_00005 again", unit: "pages", step: null, collectionId: null, series: null, href: null });
const FINISHED = task({
  id: 28, kind: "bundle", label: "Transcribing Box Hill 01", status: "done", step: null, done: 227, total: 227, unit: "pages",
  collectionId: 1, series: "Wilfred Prest Survey", href: "/?collection=1&bundle=216413",
});
const FAILED = task({
  id: 27, kind: "train", label: "Training page sorting", status: "failed", step: null, collectionId: null, series: null, href: null,
  error: "The archive timed out.",
});
const EVERYTHING = [ADDING, TRANSCRIBING, QUEUED, READING, FINISHED, FAILED];

// A series as GET /api/collections lists it, with nothing in it yet.
const series = (id: number, name: string) => ({
  id, name, recordName: "survey", grouped: true, archiveSeries: null, archiveIdentifier: null, archiveTitle: null, archiveItems: null,
  bundles: 0, running: 0, failed: 0, pages: 0, reviewable: 0, reviewed: 0, unknownPages: 0, flagged: 0, pageTypes: 0, templates: 0,
});

type Jobs = Task[] | (() => Task[]) | { status: number; detail: string };
async function mock(page: Page, jobs: Jobs = []) {
  await page.route("**/api/**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/jobs") {
      if (!Array.isArray(jobs) && typeof jobs !== "function") return route.fulfill({ status: jobs.status, json: { detail: jobs.detail } });
      return route.fulfill({ json: typeof jobs === "function" ? jobs() : jobs });
    }
    const served = serveItems([{ bundle: "b", name: "216412", pages: [] }], request);
    if (served) return route.fulfill(served);
    if (path === "/api/collections") return route.fulfill({ json: [series(1, "Wilfred Prest Survey"), series(2, "Missing, Wounded and Prisoner Of War Cards")] });
    if (path === "/api/collections/1") return route.fulfill({ json: { id: 1, name: "Wilfred Prest Survey", recordName: "survey", grouped: true, archiveSeries: 499420, pageTypes: 3, templates: 3, pages: 2, unknownPages: 0, bundles: 1, running: 0 } });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
}

const tasksButton = (page: Page) => page.getByRole("banner").locator('a[href="/?view=tasks"]');
const rows = (page: Page) => page.locator("tbody").getByRole("row");
const row = (page: Page, label: string) => rows(page).filter({ hasText: label });

test("the Tasks link counts the tasks waiting or running, and shows no count when there are none", async ({ page }) => {
  await mock(page, EVERYTHING);
  await page.goto("/");
  await expect(tasksButton(page)).toHaveAccessibleName("Tasks, 4 active");
  await expect(tasksButton(page)).toContainText("4");
  await page.unroute("**/api/**");
  await mock(page, [FINISHED, FAILED]);
  await page.goto("/");
  await expect(tasksButton(page)).toHaveAccessibleName("Tasks");
  await expect(tasksButton(page)).toHaveText(""); // its icon alone
});

for (const url of ["/", "/?collection=1", "/?collection=1&bundle=216412", "/?collection=1&view=setup", "/?view=settings", "/?view=import", "/?survey=216417_1", "/?view=tasks"]) {
  test(`the Tasks link is in the header of ${url}`, async ({ page }) => {
    await mock(page, [ADDING]);
    await page.goto(url);
    await expect(tasksButton(page)).toHaveAccessibleName("Tasks, 1 active");
  });
}

test("the count follows the server every few seconds", async ({ page }) => {
  let jobs = [ADDING, TRANSCRIBING];
  await mock(page, () => jobs);
  await page.goto("/");
  await expect(tasksButton(page)).toHaveAccessibleName("Tasks, 2 active");
  jobs = [{ ...ADDING, status: "done" }];
  await expect(tasksButton(page)).toHaveAccessibleName("Tasks", { timeout: 9000 });
});

test("the Tasks link opens the Tasks page, a table of the active tasks first, then the recent ones", async ({ page }) => {
  await mock(page, EVERYTHING);
  await page.goto("/");
  await tasksButton(page).click();
  await expect(page).toHaveURL("/?view=tasks");
  await expect(page.getByRole("heading", { name: "Tasks", level: 1 })).toBeVisible();
  await expect(page.getByRole("columnheader")).toHaveText(["Task", "Series", "Status", "Progress", "Updated", "Open"]);
  await expect(rows(page)).toHaveText([
    /Adding Missing, Wounded/, /Transcribing Box Hill 00/, /Adding Shipping manifests/, /Reading page 216412_00005 again/,
    /Transcribing Box Hill 01/, /Training page sorting/,
  ]);

  const adding = row(page, "Adding Missing, Wounded");
  await expect(adding.getByRole("cell").nth(1)).toHaveText("Missing, Wounded and Prisoner Of War Cards");
  await expect(adding).toContainText("Running");
  await expect(adding).toContainText("12,400 of 60,772 read");
  await expect(adding.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "12400");
  await expect(adding.getByRole("progressbar")).toHaveAttribute("aria-valuemax", "60772");
  await expect(adding.getByRole("link", { name: "Adding Missing, Wounded and Prisoner Of War Cards' items" })).toHaveAttribute("href", "/?view=tasks&task=31");

  const transcribing = row(page, "Transcribing Box Hill 00");
  await expect(transcribing.getByRole("cell").nth(1)).toHaveText("Wilfred Prest Survey");
  await expect(transcribing).toContainText("Transcribing pages · 40 of 227 pages");
  await expect(transcribing.getByRole("link")).toHaveAttribute("href", "/?view=tasks&task=32");

  const queued = row(page, "Adding Shipping manifests");
  await expect(queued.getByRole("cell").nth(1)).toHaveText("Shipping manifests"); // the task names its series: GET /api/collections lists no such series
  await expect(queued).toContainText("Waiting to start");
  await expect(queued.getByRole("progressbar")).toBeVisible();

  const reading = row(page, "Reading page 216412_00005 again");
  await expect(reading).toContainText("Starting…");
  await expect(reading.getByRole("link")).toHaveAttribute("href", "/?view=tasks&task=35"); // every task opens its own page

  const finished = row(page, "Transcribing Box Hill 01");
  await expect(finished).toContainText("Done");
  await expect(finished).toContainText("227 of 227 pages");
  await expect(finished.getByRole("progressbar")).toHaveCount(0);

  const failed = row(page, "Training page sorting");
  await expect(failed).toContainText("Failed");
  await expect(failed.getByText("The archive timed out.")).toHaveClass(/text-destructive/);
  await expect(failed.getByRole("cell").nth(4)).not.toBeEmpty(); // when it was last updated
});

// A task as GET /api/jobs/<id>/log gives it: the task, when it started, its lines in the worker's log, oldest first, and the rest.
type Extra = { added: number | null; skipped: number | null; seriesItems: number | null; workerRunning: boolean | null };
const logged = (task: Task, startedAt: string | null, log: [string, string][], extra: Partial<Extra> = {}) => ({
  ...task, startedAt, log: log.map(([time, text]) => ({ time, text })), added: null, skipped: null, seriesItems: null, workerRunning: true,
  ...extra,
});
const stat = (page: Page, label: string) => page.locator('[data-slot="card"]').filter({ hasText: label });
const summary = (page: Page) => page.getByTestId("task-summary");
const progress = (page: Page) => page.getByTestId("task-progress");
const logRows = (page: Page) => page.locator("section tbody tr");

test("a task opens its own page: a line of its status, series and times, how far it has got, what it has added, and its log", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-10-19T03:20:00+00:00"));
  await mock(page, EVERYTHING);
  const started = "2026-10-19T03:00:00+00:00";
  await page.route("**/api/jobs/31/log", (route) => route.fulfill({ json: logged(
    { ...ADDING, updatedAt: "2026-10-19T03:20:00+00:00" }, started,
    [[started, "started: items"], ["2026-10-19T03:00:01+00:00", "step: adding"], ["2026-10-19T03:19:58+00:00", "box 517 of 2,540: 12,400 read, 12,350 added"]],
    { added: 12350, skipped: 50, seriesItems: 12351 },
  ) }));
  await page.goto("/?view=tasks");
  await row(page, "Adding Missing, Wounded").click();
  await expect(page).toHaveURL("/?view=tasks&task=31");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(ADDING.label);
  await expect(page.locator('[data-slot="breadcrumb-item"]')).toHaveText(["Tasks", ADDING.label]);
  const [since, updated, finish] = await page.evaluate(() => {
    const left = (60772 - 12400) / (12400 / 1199); // seconds: 12,400 read since the adding step began, 1,199 seconds before the update
    return [new Date("2026-10-19T03:00:00Z").toLocaleTimeString(), new Date("2026-10-19T03:20:00Z").toLocaleTimeString(),
      new Date(Date.parse("2026-10-19T03:20:00Z") + left * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })];
  }); // in the browser's words: today's times without their date
  await expect(summary(page)).toHaveText(
    `RunningMissing, Wounded and Prisoner Of War Cards · started ${since}, running for 20 min · updated ${updated}`);
  await expect(progress(page)).toContainText("12,400 of 60,772 read");
  await expect(progress(page)).toContainText("20%");
  await expect(progress(page)).toContainText(`About 1 h 18 min left · done around ${finish} · 10 items a second`);
  await expect(stat(page, "Added")).toContainText("12,350");
  await expect(stat(page, "Skipped")).toContainText("50");
  await expect(stat(page, "In the series now")).toContainText("12,351");
  await expect(page.getByRole("link", { name: "Open the series" })).toHaveAttribute("href", "/?collection=2");
  await expect(logRows(page)).toHaveText([/Box 517 of 2,540: 12,400 read, 12,350 added/, /Adding items/, /Started/]);
  await expect(logRows(page).first()).toContainText(await page.evaluate(() => new Date("2026-10-19T03:19:58Z").toLocaleTimeString()));
  await expect(page.getByRole("alert")).toHaveCount(0); // the worker is running
});

test("a finished task's page says how long it took to its last line, with no time left or speed, and only its progress card", async ({ page }) => {
  await mock(page, []);
  await page.route("**/api/jobs/28/log", (route) => route.fulfill({ json: logged(
    { ...FINISHED, updatedAt: "2026-10-19T09:00:00+00:00" }, "2026-10-19T03:00:00+00:00", // updated later: a worker restart's stamp
    [["2026-10-19T03:00:00+00:00", "started: bundle data/216413/x.pdf"], ["2026-10-19T03:01:00+00:00", "step: transcribe"],
      ["2026-10-19T04:50:00+00:00", "done"]], { workerRunning: false }) }));
  await page.goto("/?view=tasks&task=28");
  await expect(summary(page)).toContainText("took 1 h 50 min");
  await expect(progress(page)).toHaveText("227 of 227 pages100%");
  await expect(page.locator('[data-slot="card"]')).toHaveCount(1); // nothing added
  await expect(page.getByRole("alert")).toHaveCount(0); // it doesn't need the worker any more
  await expect(page.getByRole("link", { name: "Open the item" })).toHaveAttribute("href", "/?collection=1&bundle=216413");
  await expect(logRows(page)).toHaveText([/Done/, /Transcribing pages/, /Started/]);
});

test("the log says each step in words, and a failed task's error is shown", async ({ page }) => {
  await mock(page, []);
  await page.route("**/api/jobs/32/log", (route) => route.fulfill({ json: logged({ ...TRANSCRIBING, status: "failed", error: "The model refused." }, null, [
    ["2026-10-19T03:00:00+00:00", "started: bundle data/216412/x.pdf"], ["2026-10-19T03:00:01+00:00", "step: split"],
    ["2026-10-19T03:01:00+00:00", "step: validate"], ["2026-10-19T03:02:00+00:00", "failed during transcribe"],
    ["2026-10-19T03:03:00+00:00", "failed during None"], ["2026-10-19T03:04:00+00:00", "stopped during split"],
  ]) }));
  await page.goto("/?view=tasks&task=32");
  await expect(page.locator("section tbody tr td:nth-child(2)")).toHaveText([
    "Stopped while preparing page images (downloads PDF if needed)", "Failed", "Failed while transcribing pages",
    "Checking the transcriptions' fields", "Preparing page images (downloads PDF if needed)", "Started",
  ]);
  await expect(page.getByRole("alert")).toHaveText("The model refused.");
});

for (const [status, text] of [
  ["waiting", "The worker isn't running, so this task won't start. Start it with uv run worker."],
  ["running", "The worker isn't running, so this task has stopped. Start it with uv run worker, then run the task again."],
] as const) {
  test(`a ${status} task's page says when the worker isn't running, without a time left`, async ({ page }) => {
    await mock(page, []);
    const started = "2026-10-19T03:00:00+00:00";
    await page.route("**/api/jobs/31/log", (route) => route.fulfill({ json: logged({ ...ADDING, status, updatedAt: "2026-10-19T03:20:00+00:00" },
      status === "running" ? started : null, status === "running" ? [[started, "started: items"]] : [], { workerRunning: false }) }));
    await page.goto("/?view=tasks&task=31");
    await expect(page.getByRole("alert")).toHaveText(text);
    await expect(summary(page)).not.toContainText("running for");
    await expect(progress(page)).not.toContainText("left");
  });
}

test("with no word from a worker yet, a waiting task's page doesn't warn, and says it hasn't started or logged anything", async ({ page }) => {
  await mock(page, []);
  await page.route("**/api/jobs/33/log", (route) => route.fulfill({ json: logged(QUEUED, null, [], { workerRunning: null }) }));
  await page.goto("/?view=tasks&task=33");
  await expect(summary(page)).toContainText("Shipping manifests · not started yet");
  await expect(progress(page)).toHaveText("Waiting to start");
  await expect(logRows(page)).toHaveText(["Nothing logged for this task."]);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("a task that isn't there says so", async ({ page }) => {
  await mock(page, []);
  await page.route("**/api/jobs/99/log", (route) => route.fulfill({ status: 404, json: { detail: "There's no task 99." } }));
  await page.goto("/?view=tasks&task=99");
  await expect(page.getByText("Couldn't load the task: There's no task 99.")).toBeVisible();
});

test("with no tasks the Tasks page says so", async ({ page }) => {
  await mock(page, []);
  await page.goto("/?view=tasks");
  await expect(page.getByText("No tasks yet.")).toBeVisible();
  await expect(rows(page)).toHaveText(["No tasks yet."]);
});

test("if the tasks can't be fetched the last list stays, with a note", async ({ page }) => {
  let jobs: Jobs = [ADDING];
  await mock(page, () => (Array.isArray(jobs) ? jobs : []));
  await page.goto("/?view=tasks");
  await expect(rows(page)).toHaveText([/Adding Missing, Wounded/]);
  await page.unroute("**/api/**");
  jobs = { status: 500, detail: "Jobs unavailable" };
  await mock(page, jobs);
  await expect(page.getByText("Couldn't refresh the tasks: Jobs unavailable")).toBeVisible({ timeout: 9000 });
  await expect(rows(page)).toHaveText([/Adding Missing, Wounded/]);
  await expect(tasksButton(page)).toHaveAccessibleName("Tasks, 1 active");
});

test("if the tasks have never loaded the Tasks page says only why", async ({ page }) => {
  await mock(page, { status: 500, detail: "Jobs unavailable" });
  await page.goto("/?view=tasks");
  await expect(page.getByText("Couldn't refresh the tasks: Jobs unavailable")).toBeVisible();
  await expect(page.getByText("No tasks yet.")).toHaveCount(0);
  await expect(page.getByRole("table")).toHaveCount(0);
});

const banner = (page: Page) => page.getByRole("status").filter({ hasText: /items from the archive/ });

for (const [state, jobs, text] of [
  ["waiting", [task({ status: "waiting", step: null, collectionId: 1, href: "/?collection=1" })], "Waiting to add items from the archive."],
  ["running", [task({ done: 12400, total: 60772, collectionId: 1, href: "/?collection=1" })], "Adding items from the archive: 12,400 of 60,772."],
  ["starting", [task({ collectionId: 1, href: "/?collection=1" })], "Adding items from the archive…"],
] as const) {
  test(`the dashboard's banner says when its items are ${state}`, async ({ page }) => {
    await mock(page, [...jobs]);
    await page.goto("/?collection=1");
    await expect(banner(page)).toHaveText(text);
    await expect(page.getByTestId("stat-total-pages")).toBeVisible(); // above the stats
  });
}

test("the dashboard's banner is for its own series' adding job only", async ({ page }) => {
  await mock(page, [
    ADDING, QUEUED, // other series
    TRANSCRIBING, // this series, but not adding items
    task({ id: 40, status: "done", step: null, collectionId: 1, href: "/?collection=1" }), // finished
  ]);
  await page.goto("/?collection=1");
  await expect(page.getByTestId("stat-total-pages")).toBeVisible();
  await expect(tasksButton(page)).toHaveAccessibleName("Tasks, 3 active");
  await expect(banner(page)).toHaveCount(0);
});
