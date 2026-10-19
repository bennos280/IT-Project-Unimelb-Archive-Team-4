import { test, expect, type Page } from "@playwright/test";

// The API is intercepted: no requests reach the real backend, and the real claude and codex programs are never run.
const conn = (over: object = {}) => ({
  installed: true, signedIn: false, method: null, plan: null, version: null, warnings: [], error: null,
  login: { running: false, exitCode: null }, ...over,
});
const ready = (over: object = {}) => conn({ signedIn: true, method: "claude.ai", plan: "max", version: "2.1.288", ...over });

type State = { claude: ReturnType<typeof conn>; codex: ReturnType<typeof conn> };
type Defaults = { provider: string; model: string; effort: string };
const SAVED: Defaults = { provider: "claude", model: "claude-saved-model", effort: "high" };
const APP: Defaults = { provider: "codex", model: "gpt-app-model", effort: "medium" };
const FOLDERS = { data: "C:\\projects\\survey\\data", output: "C:\\projects\\survey\\output" };
type Options = {
  defaults?: Defaults | null; // the saved choice; null: nothing saved yet; left out: SAVED
  saveError?: string; // a 400 for PUT /transcription-defaults
  testReply?: object; // the body of a test request's reply
  testStatus?: number;
  gateTests?: boolean; // hold test replies until calls.release()
  transcriptionOptions?: object; // the body of GET /transcription-options; without it the request fails and the text boxes stay
};

async function mockApi(page: Page, state: State, options: Options = {}) {
  let defaults = options.defaults === undefined ? SAVED : options.defaults;
  let release = () => {};
  const gate = options.gateTests ? new Promise<void>((resolve) => { release = resolve; }) : null;
  const calls = {
    get: 0, post: [] as string[], delete: [] as string[], loginBody: [] as unknown[],
    put: [] as unknown[], deletes: 0, logout: [] as string[], logoutBody: [] as unknown[], tests: [] as string[], testBody: [] as unknown[],
    release: () => release(),
  };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const login = path.match(/^\/api\/connections\/(claude|codex)\/login$/);
    const logout = path.match(/^\/api\/connections\/(claude|codex)\/logout$/);
    const tested = path.match(/^\/api\/connections\/(claude|codex)\/test$/);
    if (path === "/api/transcription-defaults" && request.method() === "PUT") {
      calls.put.push(request.postDataJSON());
      if (options.saveError) return route.fulfill({ status: 400, json: { detail: options.saveError } });
      defaults = request.postDataJSON();
      return route.fulfill({ json: defaults });
    }
    if (path === "/api/transcription-defaults" && request.method() === "DELETE") {
      calls.deletes++;
      return route.fulfill({ status: 405, json: { detail: "Method Not Allowed" } });
    }
    if (path === "/api/folders") return route.fulfill({ json: FOLDERS });
    if (logout && request.method() === "POST") {
      calls.logout.push(logout[1]);
      calls.logoutBody.push(request.postDataJSON());
      state[logout[1] as keyof State] = conn({ version: state[logout[1] as keyof State].version });
      return route.fulfill({ json: state[logout[1] as keyof State] });
    }
    if (tested && request.method() === "POST") {
      calls.tests.push(tested[1]);
      calls.testBody.push(request.postDataJSON());
      await gate;
      return route.fulfill({ status: options.testStatus ?? 200, json: options.testReply ?? { ok: true, seconds: 3.2, model: "haiku", message: "Replied in 3.2 s" } });
    }
    if (path === "/api/connections") {
      calls.get++;
      return route.fulfill({ json: state });
    }
    if (login && request.method() === "POST") {
      calls.post.push(login[1]);
      calls.loginBody.push(request.postDataJSON());
      state[login[1] as keyof State].login = { running: true, exitCode: null };
      return route.fulfill({ status: 202, json: state[login[1] as keyof State].login });
    }
    if (login && request.method() === "DELETE") {
      calls.delete.push(login[1]);
      state[login[1] as keyof State].login = { running: false, exitCode: null };
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/transcription-options" && options.transcriptionOptions)
      return route.fulfill({ json: options.transcriptionOptions });
    if (path === "/api/transcription-models")
      return route.fulfill({ json: { configured: defaults, models: [] } });
    if (path === "/api/collections/1/items")
      return route.fulfill({ json: { items: [], page: 0, total: 0, all: 0, totals: { total: 0, reviewable: 0, unassigned: 0, reviewed: 0, ready: 0 } } });
    if (path === "/api/collections")
      return route.fulfill({ json: [{ id: 1, name: "Wilfred Prest Survey", archiveSeries: 499420, bundles: 0, pages: 0 }] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return calls;
}

const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const claudeModel = (value: string, group: string, label = value) => ({ value, label, group, efforts: EFFORTS, defaultEffort: null });
const OPTIONS = {
  claude: { available: true, error: null, efforts: EFFORTS, models: [
    claudeModel("claude-used-1", "used"), claudeModel("opus", "latest", "opus (latest)"), claudeModel("sonnet", "latest", "sonnet (latest)")] },
  codex: { available: true, error: null, efforts: ["low", "medium", "high"], models: [
    { value: "gpt-a", label: "GPT A", group: "listed", efforts: ["low", "medium"], defaultEffort: "medium" },
    { value: "gpt-b", label: "GPT B", group: "listed", efforts: ["high"], defaultEffort: "high" }] },
};

const claude = (page: Page) => page.getByRole("group", { name: "Claude Code" });
const codex = (page: Page) => page.getByRole("group", { name: "Codex CLI" });

test("each state shows its badge and actions, and no email or organisation", async ({ page }) => {
  const state: State = {
    claude: ready({ email: "someone@example.com", orgName: "Secret Org" }),
    codex: conn({ installed: false }),
  };
  await mockApi(page, state);
  await page.goto("/?view=settings");
  await expect(page.getByRole("heading", { name: "Accounts" })).toBeVisible();
  await expect(page.getByText("Uses your own Claude or ChatGPT subscription on this computer. Usage counts against it.")).toBeVisible();
  await expect(claude(page)).toContainText("Ready");
  await expect(claude(page)).toContainText("Max plan");
  await expect(claude(page).getByRole("button")).toHaveText(["Test connection", "Sign out"]);
  await expect(codex(page)).toContainText("Not installed");
  await expect(codex(page).getByRole("link", { name: /Install Codex CLI/ })).toHaveAttribute("href", "https://developers.openai.com/codex/cli");
  await expect(codex(page).getByRole("button", { name: "Check again" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/@example\.com|Secret Org/);

  state.claude = conn({ installed: false });
  await codex(page).getByRole("button", { name: "Check again" }).click();
  await expect(claude(page)).toContainText("Not installed");
  await expect(claude(page).getByRole("link", { name: /Install Claude Code/ })).toHaveAttribute("href", "https://code.claude.com/docs/en/setup");

  state.claude = conn();
  state.codex = ready({ method: "api_key", plan: null, warnings: ["Transcription is billed to this API key, not to your ChatGPT plan."] });
  await claude(page).getByRole("button", { name: "Check again" }).click();
  await expect(claude(page)).toContainText("Not signed in");
  await expect(claude(page).getByRole("button", { name: "Open Claude Code sign-in" })).toBeVisible();
  await expect(codex(page)).toContainText("Signed in with an API key");
  await expect(codex(page).getByRole("alert")).toContainText("billed to this API key");
  await expect(codex(page).getByRole("button", { name: "Open Codex sign-in" })).toBeVisible();
});

test("a failed status check is shown with a way to check again", async ({ page }) => {
  await mockApi(page, { claude: conn({ error: "The sign-in status check failed." }), codex: ready({ method: "chatgpt" }) });
  await page.goto("/?view=settings");
  await expect(claude(page)).toContainText("Status check failed");
  await expect(claude(page).getByRole("button", { name: "Check again" })).toBeVisible();
  await expect(codex(page)).toContainText("Ready");
});

test("signing in sends a JSON POST, polls while waiting, and switches to Ready", async ({ page }) => {
  await page.clock.install();
  const state: State = { claude: conn(), codex: ready({ method: "chatgpt" }) };
  const calls = await mockApi(page, state);
  await page.goto("/?view=settings");
  await claude(page).getByRole("button", { name: "Open Claude Code sign-in" }).click();
  await expect(claude(page).getByText("Finish signing in in the browser window that opened.")).toBeVisible();
  await expect(claude(page).getByRole("button", { name: "Cancel" })).toBeVisible();
  await expect(claude(page).locator("code")).toHaveText(["claude auth login"]);
  expect(calls.post).toEqual(["claude"]);
  expect(calls.loginBody).toEqual([{}]);
  await expect.poll(() => calls.get).toBeGreaterThan(1);

  const before = calls.get;
  await page.clock.runFor(2000);
  await expect.poll(() => calls.get).toBeGreaterThan(before);
  state.claude = ready({ login: { running: false, exitCode: 0 } });
  await page.clock.runFor(2000);
  await expect(claude(page)).toContainText("Ready");
  await expect(claude(page).getByText("Finish signing in")).toHaveCount(0);

  const settled = calls.get;
  await page.clock.runFor(10000);
  await page.evaluate(() => 0);
  expect(calls.get).toBe(settled);
});

test("no polling while nothing is signing in, and a window focus reloads", async ({ page }) => {
  await page.clock.install();
  const calls = await mockApi(page, { claude: conn(), codex: conn() });
  await page.goto("/?view=settings");
  await expect(claude(page)).toContainText("Not signed in");
  const loaded = calls.get;
  await page.clock.runFor(10000);
  await page.evaluate(() => 0);
  expect(calls.get).toBe(loaded);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => calls.get).toBe(loaded + 1);
});

test("Cancel sends a DELETE and returns to the sign-in button", async ({ page }) => {
  const calls = await mockApi(page, { claude: conn({ login: { running: true, exitCode: null } }), codex: conn() });
  await page.goto("/?view=settings");
  await claude(page).getByRole("button", { name: "Cancel" }).click();
  await expect(claude(page).getByRole("button", { name: "Open Claude Code sign-in" })).toBeVisible();
  expect(calls.delete).toEqual(["claude"]);
  await expect(claude(page).getByText("Finish signing in")).toHaveCount(0);
});

test("a sign-in that ended with an error while still signed out shows an alert", async ({ page }) => {
  await mockApi(page, { claude: conn(), codex: conn({ login: { running: false, exitCode: 1 } }) });
  await page.goto("/?view=settings");
  await expect(codex(page).getByRole("alert")).toHaveText("Sign-in didn't finish. Try again, or run codex login in a terminal.");
  await expect(codex(page).getByRole("button", { name: "Open Codex sign-in" })).toBeVisible();
  await expect(claude(page).getByRole("alert")).toHaveCount(0);
});

const field = (page: Page, name: string) => page.getByLabel(name, { exact: true });
const defaultsCard = (page: Page) => page.locator("[data-slot=card]", { hasText: "Save defaults" });

test("nothing is chosen until the team saves a choice: it says so and has no Reset button", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: conn() }, { defaults: null });
  await page.goto("/?view=settings");
  await expect(page.getByRole("heading", { name: "Transcription model" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Before you can transcribe" })).toBeVisible();
  await expect(page.getByText("Ready to transcribe")).toHaveCount(0);
  await expect(field(page, "Provider")).toHaveValue("");
  await expect(field(page, "Model")).toHaveValue("");
  await expect(field(page, "Effort")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Save defaults" })).toBeDisabled();
  await expect(page.getByRole("button", { name: /Reset/ })).toHaveCount(0);
  await expect(usedTag(page)).toHaveCount(0);
  expect(calls.put).toEqual([]);
});

test("the saved choice is shown with the section note and the ready line", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  await expect(page.getByText("Used for new transcriptions. Shared with the team.")).toBeVisible();
  await expect(readyLine(page)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Before you can transcribe" })).toHaveCount(0);
  await expect(field(page, "Provider")).toHaveValue("claude");
  await expect(field(page, "Model")).toHaveValue("claude-saved-model");
  await expect(field(page, "Effort")).toHaveValue("high");
  await expect(page.getByRole("button", { name: /Reset/ })).toHaveCount(0);
});

test("Save needs all three chosen, then sends them and shows Saved ✓", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt", version: "0.12.3" }) }, { defaults: null });
  await page.goto("/?view=settings");
  const save = page.getByRole("button", { name: "Save defaults" });
  await field(page, "Provider").selectOption("codex");
  await expect(field(page, "Model")).toHaveValue("");
  await expect(save).toBeDisabled();
  await field(page, "Model").fill(" gpt-app-model ");
  await expect(save).toBeDisabled(); // no effort yet
  await field(page, "Effort").fill("medium");
  await expect(save).toBeEnabled();
  await field(page, "Model").fill("");
  await expect(save).toBeDisabled();
  await field(page, "Model").fill(" gpt-app-model ");
  await save.click();
  await expect(readyLine(page)).toHaveText("Ready to transcribe · gpt-app-model · medium on Codex CLI");
  await expect(page.getByRole("status").filter({ hasText: "Saved ✓" })).toBeVisible();
  expect(calls.put).toEqual([{ provider: "codex", model: "gpt-app-model", effort: "medium" }]);
  await expect(field(page, "Provider")).toHaveValue("codex");
  await expect(field(page, "Model")).toHaveValue("gpt-app-model");
  await expect(page.getByRole("button", { name: /Reset/ })).toHaveCount(0);
  await expect(defaultsCard(page).getByRole("alert")).toHaveCount(0);
  await expect(save).toBeDisabled();
  expect(calls.deletes).toBe(0);
});

test("with the model lists, nothing is picked for you: the dropdowns start on Choose…", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) }, { defaults: null, transcriptionOptions: OPTIONS });
  await page.goto("/?view=settings");
  const save = page.getByRole("button", { name: "Save defaults" });
  for (const label of ["Provider", "Model", "Effort"]) await expect(field(page, label)).toHaveValue("");
  expect(await optionTexts(page, "Provider")).toEqual(["Choose…", "Claude", "Codex"]);
  await field(page, "Provider").selectOption("claude");
  expect(await optionTexts(page, "Model")).toEqual(["Choose…", "claude-used-1", "opus (latest)", "sonnet (latest)", "Other…"]);
  await expect(field(page, "Model")).toHaveValue("");
  await expect(field(page, "Effort")).toHaveValue("");
  await expect(save).toBeDisabled();
  await field(page, "Model").selectOption("opus");
  await expect(field(page, "Effort")).toHaveValue(""); // not filled in either
  expect(await optionTexts(page, "Effort")).toEqual(["Choose…", ...EFFORTS]);
  await expect(save).toBeDisabled();
  await field(page, "Effort").selectOption("low");
  expect(await optionTexts(page, "Effort")).toEqual(EFFORTS);
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByText("Saved ✓")).toBeVisible();
  expect(calls.put).toEqual([{ provider: "claude", model: "opus", effort: "low" }]);
});

test("a save the API refuses shows its message and keeps what was typed", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() }, { saveError: "Enter a valid model name." });
  await page.goto("/?view=settings");
  await field(page, "Model").fill("two words");
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(defaultsCard(page).getByRole("alert")).toHaveText("Enter a valid model name.");
  await expect(field(page, "Model")).toHaveValue("two words");
  await expect(readyLine(page)).toHaveText("Ready to transcribe · claude-saved-model · high on Claude Code");
  await expect(page.getByText("Saved ✓")).toHaveCount(0);
});

test("choosing a provider that isn't ready warns", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  await expect(defaultsCard(page).getByRole("alert")).toHaveCount(0);
  await field(page, "Provider").selectOption("codex");
  await expect(defaultsCard(page).getByRole("alert")).toContainText("Codex CLI isn't ready (not signed in)");
  await field(page, "Provider").selectOption("claude");
  await expect(defaultsCard(page).getByRole("alert")).toHaveCount(0);
});

test("a signed-in card shows plan and version, then buttons and the usage link", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt", plan: null, version: "0.12.3" }) });
  await page.goto("/?view=settings");
  await expect(claude(page).locator("[data-slot=card-description]")).toHaveText("Max plan · 2.1.288");
  await expect(codex(page).locator("[data-slot=card-description]")).toHaveText("ChatGPT plan · 0.12.3");
  await expect(claude(page).getByRole("button")).toHaveText(["Test connection", "Sign out"]);
  await expect(claude(page).getByRole("link", { name: "Check usage" })).toHaveAttribute("href", "https://claude.ai/settings/usage");
  await expect(codex(page).getByRole("link", { name: "Check usage" })).toHaveAttribute("href", "https://chatgpt.com/codex/settings/usage");
  for (const card of [claude(page), codex(page)]) {
    const link = card.getByRole("link", { name: "Check usage" });
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", /noopener/);
  }
});

test("no usage link for an API key or when not signed in, and no buttons unless signed in", async ({ page }) => {
  await mockApi(page, { claude: conn({ version: "2.1.288" }), codex: ready({ method: "api_key", plan: null }) });
  await page.goto("/?view=settings");
  await expect(claude(page)).toContainText("Not signed in");
  await expect(claude(page).locator("[data-slot=card-description]")).toHaveText("2.1.288");
  await expect(claude(page).getByRole("link", { name: "Check usage" })).toHaveCount(0);
  await expect(claude(page).getByRole("button", { name: /Test connection|Sign out/ })).toHaveCount(0);
  await expect(codex(page).getByRole("link", { name: "Check usage" })).toHaveCount(0);
  await expect(codex(page).getByRole("button", { name: "Test connection" })).toBeVisible();
});

test("an old Claude Code version is flagged", async ({ page }) => {
  const warning = "Claude Code 2.1.200 is older than 2.1.280, which transcription needs. Update it with: claude update";
  await mockApi(page, { claude: ready({ version: "2.1.200", warnings: [warning] }), codex: conn({ installed: false }) });
  await page.goto("/?view=settings");
  await expect(claude(page).getByRole("alert")).toHaveText(warning);
  await expect(claude(page).locator("[data-slot=card-description]")).toHaveText("Max plan · 2.1.200");
});

test("Sign out asks first, and Cancel sends nothing", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  await claude(page).getByRole("button", { name: "Sign out" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Sign out of Claude Code?" })).toBeVisible();
  await expect(dialog).toContainText("This signs Claude Code out on this computer, including in your terminal. Transcription with it stops until you sign in again.");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls.logout).toEqual([]);
  await expect(claude(page)).toContainText("Ready");
});

test("confirming Sign out sends a JSON POST and the card goes back to not signed in", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  await claude(page).getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(claude(page)).toContainText("Not signed in");
  await expect(claude(page).getByRole("button", { name: "Open Claude Code sign-in" })).toBeVisible();
  expect(calls.logout).toEqual(["claude"]);
  expect(calls.logoutBody).toEqual([{}]);
});

test("Test connection shows a spinner, then the time and model", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: conn() }, { gateTests: true });
  await page.goto("/?view=settings");
  await claude(page).getByRole("button", { name: "Test connection" }).click();
  await expect(claude(page).getByText("Waiting for a reply…")).toBeVisible();
  await expect(claude(page).getByRole("button", { name: "Test connection" })).toBeDisabled();
  calls.release();
  await expect(claude(page).getByText("Works · replied in 3.2 s (haiku)")).toBeVisible();
  await expect(claude(page).getByText("Waiting for a reply…")).toHaveCount(0);
  expect(calls.tests).toEqual(["claude"]);
  expect(calls.testBody).toEqual([{}]);
});

test("a failed test shows the message in an alert", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() },
    { testReply: { ok: false, seconds: 1.4, model: "haiku", message: "Not logged in. Please run /login" } });
  await page.goto("/?view=settings");
  await claude(page).getByRole("button", { name: "Test connection" }).click();
  await expect(claude(page).getByRole("alert")).toHaveText("Not logged in. Please run /login");
  await expect(claude(page).getByText(/^Works/)).toHaveCount(0);
});

test("a test the API refuses (another one running) shows the reason", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() }, { testStatus: 409, testReply: { detail: "A test is already running." } });
  await page.goto("/?view=settings");
  await claude(page).getByRole("button", { name: "Test connection" }).click();
  await expect(claude(page).getByRole("alert")).toHaveText("A test is already running.");
});

test("the app's name returns to the series list", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  await page.getByRole("link", { name: "PrestCribe" }).click();
  await expect(page.getByRole("heading", { name: "Series", level: 1 })).toBeVisible();
});

test("the top bar's Settings opens the settings page", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?collection=1");
  await page.getByRole("banner").getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/\?view=settings$/);
  await expect(page.getByRole("heading", { name: "Accounts" })).toBeVisible();
});

const optionTexts = (page: Page, label: string) => field(page, label).locator("option").allTextContents();
const groupLabels = (page: Page, label: string) => field(page, label).locator("optgroup").evaluateAll((groups) => groups.map((g) => g.getAttribute("label")));

test("the model dropdown groups used, latest and Other, and the effort dropdown lists the efforts", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) }, { defaults: { ...SAVED, model: "opus" }, transcriptionOptions: OPTIONS });
  await page.goto("/?view=settings");
  await expect(field(page, "Model")).toHaveValue("opus");
  expect(await groupLabels(page, "Model")).toEqual(["Used in this project", "Latest"]);
  expect(await optionTexts(page, "Model")).toEqual(["claude-used-1", "opus (latest)", "sonnet (latest)", "Other…"]);
  expect(await optionTexts(page, "Effort")).toEqual(EFFORTS);
  await expect(field(page, "Effort")).toHaveValue("high");
  await expect(page.getByLabel("Custom model name")).toHaveCount(0);
});

test("choosing a Codex model shows its efforts, and switching models keeps a supported effort and clears an unsupported one", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) }, { transcriptionOptions: OPTIONS });
  await page.goto("/?view=settings");
  await field(page, "Provider").selectOption("codex");
  expect(await groupLabels(page, "Model")).toEqual(["From Codex"]);
  await expect(field(page, "Model")).toHaveValue(""); // nothing picked for you
  await expect(field(page, "Effort")).toHaveValue("");
  await field(page, "Model").selectOption("gpt-a");
  expect(await optionTexts(page, "Effort")).toEqual(["Choose…", "low", "medium"]);
  await expect(field(page, "Effort")).toHaveValue(""); // not even the model's default
  await field(page, "Effort").selectOption("low");
  await field(page, "Model").selectOption("gpt-b");
  expect(await optionTexts(page, "Effort")).toEqual(["Choose…", "high"]);
  await expect(field(page, "Effort")).toHaveValue(""); // low isn't supported by gpt-b
  await expect(page.getByRole("button", { name: "Save defaults" })).toBeDisabled();
  await field(page, "Effort").selectOption("high");
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(page.getByText("Saved ✓")).toBeVisible();
  expect(calls.put).toEqual([{ provider: "codex", model: "gpt-b", effort: "high" }]);
});

test("changing provider clears the model and effort, and a supported effort is kept when the model changes", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) }, { defaults: { ...SAVED, model: "opus", effort: "max" }, transcriptionOptions: OPTIONS });
  await page.goto("/?view=settings");
  await field(page, "Model").selectOption("sonnet");
  await expect(field(page, "Effort")).toHaveValue("max");
  await field(page, "Provider").selectOption("codex");
  await expect(field(page, "Model")).toHaveValue("");
  await expect(field(page, "Effort")).toHaveValue("");
  await field(page, "Provider").selectOption("claude");
  await expect(field(page, "Model")).toHaveValue("");
  await expect(field(page, "Effort")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Save defaults" })).toBeDisabled();
});

test("Other… shows a text box and saves the custom name", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: conn() }, { defaults: { ...SAVED, model: "opus" }, transcriptionOptions: OPTIONS });
  await page.goto("/?view=settings");
  await field(page, "Model").selectOption({ label: "Other…" });
  const custom = page.getByLabel("Custom model name");
  await expect(custom).toHaveValue("");
  await expect(page.getByRole("button", { name: "Save defaults" })).toBeDisabled();
  await custom.fill(" claude-custom-9 ");
  await field(page, "Effort").selectOption("max");
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(page.getByText("Saved ✓")).toBeVisible();
  expect(calls.put).toEqual([{ provider: "claude", model: "claude-custom-9", effort: "max" }]);
  await expect(field(page, "Model").locator("option:checked")).toHaveText("Other…");
  await expect(page.getByLabel("Custom model name")).toHaveValue("claude-custom-9");
  await field(page, "Model").selectOption("sonnet");
  await expect(page.getByLabel("Custom model name")).toHaveCount(0);
});

test("a saved default that isn't in the list preselects Other… with its name", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() }, { defaults: { ...SAVED, model: "claude-saved-model", effort: "weird" }, transcriptionOptions: OPTIONS });
  await page.goto("/?view=settings");
  await expect(field(page, "Model").locator("option:checked")).toHaveText("Other…");
  await expect(page.getByLabel("Custom model name")).toHaveValue("claude-saved-model");
  expect(await optionTexts(page, "Effort")).toEqual([...EFFORTS, "weird"]); // what is saved is shown, not replaced
  await expect(field(page, "Effort")).toHaveValue("weird");
});

test("a provider whose options have an error falls back to text boxes and shows it", async ({ page }) => {
  const broken = { ...OPTIONS, codex: { available: true, models: [], efforts: [], error: "Couldn't read Codex's model list." } };
  const calls = await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) }, { transcriptionOptions: broken });
  await page.goto("/?view=settings");
  await expect(field(page, "Model").locator("optgroup").first()).toBeAttached(); // claude still has its dropdowns
  await field(page, "Provider").selectOption("codex");
  await expect(field(page, "Model")).toHaveValue("");
  await field(page, "Model").fill("gpt-typed");
  await field(page, "Effort").fill("medium");
  await expect(defaultsCard(page).getByText("Couldn't read Codex's model list.")).toBeVisible();
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(page.getByText("Saved ✓")).toBeVisible();
  expect(calls.put).toEqual([{ provider: "codex", model: "gpt-typed", effort: "medium" }]);
});

test("options that fail to load leave the text boxes", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  await expect(field(page, "Model")).toHaveValue("claude-saved-model");
  await expect(field(page, "Effort")).toHaveValue("high");
  await expect(field(page, "Model").locator("option")).toHaveCount(0);
  await expect(defaultsCard(page).getByText("The model lists couldn't be loaded.")).toBeVisible();
});

test("a model that lists no efforts uses its provider's", async ({ page }) => {
  const bare = { ...OPTIONS, codex: { ...OPTIONS.codex, models: [{ value: "gpt-c", label: "GPT C", group: "listed", efforts: [], defaultEffort: null }] } };
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) }, { transcriptionOptions: bare });
  await page.goto("/?view=settings");
  await field(page, "Provider").selectOption("codex");
  await field(page, "Model").selectOption("gpt-c");
  expect(await optionTexts(page, "Effort")).toEqual(["Choose…", "low", "medium", "high"]);
  await expect(field(page, "Effort")).toHaveValue("");
});

const NOTE = "Sends one tiny request on your plan.";
const usedTag = (scope: Page | ReturnType<typeof claude>) => scope.getByText("Used for transcription", { exact: true });
const cardLine = (card: ReturnType<typeof claude>) => card.locator("[data-slot=card-description]");

test("the page has a Settings heading and subtitle above the sections", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.getByText("Transcription model and accounts", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Accounts", level: 2 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Transcription model", level: 2 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Folders", level: 2 })).toBeVisible();
  await expect(page.getByRole("link", { name: "PrestCribe" })).toBeVisible();
});

test("the Used for transcription tag shows only once a choice is saved, then follows the saved provider", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) }, { defaults: null });
  await page.goto("/?view=settings");
  await expect(page.getByRole("heading", { name: "Before you can transcribe" })).toBeVisible();
  await expect(usedTag(page)).toHaveCount(0);

  await field(page, "Provider").selectOption("codex"); // an unsaved edit doesn't show the tag
  await field(page, "Model").fill("gpt-app-model");
  await field(page, "Effort").fill("medium");
  await expect(usedTag(page)).toHaveCount(0);
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(page.getByText("Saved ✓")).toBeVisible();
  await expect(usedTag(page)).toHaveCount(1);
  await expect(usedTag(codex(page))).toBeVisible();
  await expect(usedTag(claude(page))).toHaveCount(0);

  await field(page, "Provider").selectOption("claude"); // an unsaved edit doesn't move it
  await expect(usedTag(codex(page))).toBeVisible();
  await field(page, "Model").fill("claude-saved-model");
  await field(page, "Effort").fill("high");
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(usedTag(page)).toHaveCount(1);
  await expect(usedTag(claude(page))).toBeVisible();
  await expect(usedTag(codex(page))).toHaveCount(0);
});

test("the Used for transcription tag is on the saved provider's card from the start", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) });
  await page.goto("/?view=settings");
  await expect(usedTag(page)).toHaveCount(1);
  await expect(usedTag(claude(page))).toBeVisible();
  await expect(usedTag(codex(page))).toHaveCount(0);
});

test("the folders are shown read-only with their note", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() }, { defaults: null });
  await page.goto("/?view=settings");
  const footer = page.locator("footer", { has: page.getByRole("heading", { name: "Folders", level: 2 }) });
  await expect(footer).toContainText("Scans: " + FOLDERS.data);
  await expect(footer).toContainText("Results: " + FOLDERS.output);
  await expect(footer).toContainText("Inside the project folder.");
  await expect(footer.locator("code")).toHaveText([FOLDERS.data, FOLDERS.output]);
  await expect(footer.locator("input, button, select, textarea")).toHaveCount(0);
});

test("the line under each title is the plan and the version, leaving out what is unknown", async ({ page }) => {
  const state: State = { claude: ready(), codex: ready({ method: "chatgpt", plan: null, version: "0.163.0" }) };
  await mockApi(page, state);
  await page.goto("/?view=settings");
  await expect(cardLine(claude(page))).toHaveText("Max plan · 2.1.288");
  await expect(cardLine(codex(page))).toHaveText("ChatGPT plan · 0.163.0");

  state.claude = ready({ plan: "pro" });
  state.codex = ready({ method: "api_key", plan: null, version: "0.163.0" });
  await page.reload();
  await expect(cardLine(claude(page))).toHaveText("Pro plan · 2.1.288");
  await expect(cardLine(codex(page))).toHaveText("API key · 0.163.0");

  state.claude = ready({ plan: null });
  state.codex = ready({ method: "api_key", plan: null, version: null });
  await page.reload();
  await expect(cardLine(claude(page))).toHaveText("2.1.288");
  await expect(cardLine(codex(page))).toHaveText("API key");
});

test("Sign out is red, apart from the other buttons, and still asks before sending anything", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  const signOut = claude(page).getByRole("button", { name: "Sign out" });
  await expect(signOut).toHaveClass(/text-destructive/);
  const testButton = (await claude(page).getByRole("button", { name: "Test connection" }).boundingBox())!;
  const usage = (await claude(page).getByRole("link", { name: "Check usage" }).boundingBox())!;
  const out = (await signOut.boundingBox())!;
  expect(out.x).toBeGreaterThan(usage.x + usage.width + 40);
  expect(out.y).toBeLessThan(testButton.y + testButton.height);
  await signOut.click();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  expect(calls.logout).toEqual([]);
});

test("every badge keeps its text and has an icon that screen readers skip", async ({ page }) => {
  const state: State = { claude: ready(), codex: ready({ method: "api_key", plan: null }) };
  await mockApi(page, state);
  await page.goto("/?view=settings");
  const badge = (card: ReturnType<typeof claude>) => card.locator("[data-slot=badge]").filter({ hasNotText: "Used for transcription" });
  const states: [State["claude"], State["codex"], string, string][] = [
    [ready(), ready({ method: "api_key", plan: null }), "Ready", "Signed in with an API key"],
    [conn(), conn({ installed: false }), "Not signed in", "Not installed"],
    [conn({ error: "The sign-in status check failed." }), conn(), "Status check failed", "Not signed in"],
  ];
  for (const [c, x, claudeText, codexText] of states) {
    state.claude = c;
    state.codex = x;
    await page.reload();
    for (const [card, text] of [[claude(page), claudeText], [codex(page), codexText]] as const) {
      await expect(badge(card)).toHaveText(text);
      await expect(badge(card).locator("svg")).toHaveCount(1);
      await expect(badge(card).locator("svg")).toHaveAttribute("aria-hidden", "true");
    }
  }
});

test("Test connection explains itself in a tooltip on hover and on keyboard focus, and the note appears nowhere else", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) });
  await page.goto("/?view=settings");
  const button = claude(page).getByRole("button", { name: "Test connection" });
  const tip = page.locator("[data-slot=tooltip-content]");
  await expect(button).toHaveAccessibleDescription(NOTE); // also while the tooltip is closed
  await expect(tip).toHaveCount(0);
  await expect(page.locator("p", { hasText: NOTE })).toHaveCount(0);

  await button.hover();
  await expect(tip).toBeVisible();
  await expect(tip).toContainText(NOTE);
  await expect(button).toHaveAccessibleDescription(new RegExp(NOTE));
  await page.mouse.move(0, 0, { steps: 10 });
  await expect(tip).toHaveCount(0);

  await codex(page).getByRole("button", { name: "Test connection" }).focus();
  await expect(tip).toBeVisible();
  await expect(tip).toContainText(NOTE);
  await page.keyboard.press("Escape");
  await expect(tip).toHaveCount(0);
  await expect(page.locator("p", { hasText: NOTE })).toHaveCount(0);
});

test("Save is disabled until something changed, and Saved ✓ shows until the next edit", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) }, { transcriptionOptions: OPTIONS, defaults: { ...SAVED, model: "opus", effort: "high" } });
  await page.goto("/?view=settings");
  const save = page.getByRole("button", { name: "Save defaults" });
  await expect(field(page, "Model")).toHaveValue("opus");
  await expect(save).toBeDisabled();
  await field(page, "Effort").selectOption("low");
  await expect(save).toBeEnabled();
  await field(page, "Effort").selectOption("high");
  await expect(save).toBeDisabled();
  await expect(defaultsCard(page).locator("[role=status]")).toHaveText(""); // the live region is there before it has text

  await field(page, "Effort").selectOption("max");
  await save.click();
  await expect(page.getByRole("status").filter({ hasText: "Saved ✓" })).toBeVisible();
  await expect(save).toBeDisabled();
  await field(page, "Effort").selectOption("low");
  await expect(page.getByText("Saved ✓")).toHaveCount(0);
  await expect(save).toBeEnabled();

  await field(page, "Effort").selectOption("max");
  await field(page, "Model").selectOption({ label: "Other…" });
  await page.getByLabel("Custom model name").fill("claude-custom-9");
  await expect(save).toBeEnabled(); // custom text counts as a change
});

test("the defaults are one row across the page on a wide screen and stack on a phone", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) }, { transcriptionOptions: OPTIONS });
  const controls = async () => {
    const boxes = [];
    for (const l of [field(page, "Provider"), field(page, "Model"), field(page, "Effort"), page.getByRole("button", { name: "Save defaults" })]) boxes.push((await l.boundingBox())!);
    return boxes;
  };

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/?view=settings");
  await expect(field(page, "Model")).toBeVisible();
  const [provider, model, effort, save] = await controls();
  expect(Math.abs(model.y - provider.y)).toBeLessThan(4);
  expect(Math.abs(effort.y - provider.y)).toBeLessThan(4);
  expect(Math.abs(save.y + save.height - (provider.y + provider.height))).toBeLessThan(4);
  expect(provider.x).toBeLessThan(model.x);
  expect(model.x).toBeLessThan(effort.x);
  expect(effort.x).toBeLessThan(save.x);
  expect(model.width).toBeGreaterThan(provider.width);
  const card = (await defaultsCard(page).boundingBox())!;
  expect(save.x + save.width).toBeGreaterThan(card.x + card.width - 40); // the row spans the card

  await page.setViewportSize({ width: 375, height: 800 });
  const stacked = await controls();
  for (let i = 1; i < 4; i++) expect(stacked[i].y).toBeGreaterThan(stacked[i - 1].y + stacked[i - 1].height - 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("the tag stays on the saved provider's card when that provider isn't installed", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn({ installed: false }) }, { defaults: APP });
  await page.goto("/?view=settings");
  await expect(usedTag(page)).toHaveCount(1);
  await expect(usedTag(codex(page))).toBeVisible();
});

test("Save stays disabled for a name that differs only by spaces", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  const save = page.getByRole("button", { name: "Save defaults" });
  await field(page, "Model").fill("  claude-saved-model ");
  await expect(save).toBeDisabled();
  await field(page, "Model").fill("claude-saved-model2");
  await expect(save).toBeEnabled();
  await field(page, "Model").fill("");
  await expect(save).toBeDisabled(); // a change, but nothing to save
});

const checklist = (page: Page) => page.getByRole("region", { name: /transcribe$/ });
const checklistItems = (page: Page) => checklist(page).getByRole("listitem");
const readyLine = (page: Page) => page.getByRole("status").filter({ hasText: "Ready to transcribe" });

test("checklist: nothing chosen and nobody signed in lists both steps with links", async ({ page }) => {
  await mockApi(page, { claude: conn(), codex: conn() }, { defaults: null });
  await page.goto("/?view=settings");
  await expect(checklist(page).getByRole("heading", { name: "Before you can transcribe" })).toBeVisible();
  await expect(checklist(page).getByText("New transcriptions use")).toHaveCount(0);
  await expect(checklistItems(page)).toHaveCount(2);
  const [choose, signIn] = [checklistItems(page).nth(0), checklistItems(page).nth(1)];
  await expect(choose).toContainText("Not done");
  await expect(choose.getByRole("link", { name: "Choose a transcription model" })).toHaveAttribute("href", "#transcription-defaults");
  await expect(signIn).toContainText("Not done");
  await expect(signIn.getByRole("link", { name: "Sign in to Claude Code or the Codex CLI" })).toHaveAttribute("href", "#connections");
  for (const item of [choose, signIn]) {
    await expect(item.locator("svg")).toHaveAttribute("aria-hidden", "true");
    await expect(item.locator("svg.lucide-circle")).toHaveCount(1);
  }
  await expect(page.locator("section#transcription-defaults")).toHaveCount(1);
  await expect(page.locator("section#connections")).toHaveCount(1);
});

test("checklist: either provider signed in is enough while no model is chosen", async ({ page }) => {
  await mockApi(page, { claude: conn(), codex: ready({ method: "chatgpt" }) }, { defaults: null });
  await page.goto("/?view=settings");
  await expect(checklist(page).getByRole("heading", { name: "Before you can transcribe" })).toBeVisible();
  await expect(checklistItems(page).nth(0)).toContainText("Not done");
  await expect(checklistItems(page).nth(1)).toContainText("Done");
  await expect(checklistItems(page).nth(1).getByRole("link")).toHaveCount(0);
  await expect(checklistItems(page).nth(1).locator("svg.lucide-circle-check")).toHaveAttribute("aria-hidden", "true");
});

test("checklist: a chosen model whose provider isn't signed in links to Accounts", async ({ page }) => {
  await mockApi(page, { claude: conn(), codex: ready({ method: "chatgpt" }) }); // saved: claude
  await page.goto("/?view=settings");
  await expect(checklist(page).getByRole("heading", { name: "Before you can transcribe" })).toBeVisible();
  await expect(checklistItems(page).nth(0)).toContainText("Done");
  await expect(checklistItems(page).nth(0).getByRole("link")).toHaveCount(0);
  await expect(checklistItems(page).nth(1)).toContainText("Not done");
  await expect(checklistItems(page).nth(1).getByRole("link", { name: "Sign in to Claude Code" })).toHaveAttribute("href", "#connections");
  await expect(checklist(page).getByText("New transcriptions use")).toHaveCount(0);
});

test("checklist: a chosen provider that isn't installed counts as not signed in", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn({ installed: false }) }, { defaults: { provider: "codex", model: "gpt-app-model", effort: "medium" } });
  await page.goto("/?view=settings");
  await expect(checklist(page).getByRole("heading", { name: "Before you can transcribe" })).toBeVisible();
  await expect(checklistItems(page).nth(0)).toContainText("Done");
  await expect(checklistItems(page).nth(1)).toContainText("Not done");
  await expect(checklistItems(page).nth(1).getByRole("link", { name: "Sign in to Codex CLI" })).toHaveAttribute("href", "#connections");
});

test("checklist: all done is one status line with the model, effort and provider, and no card", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  await expect(readyLine(page)).toHaveText("Ready to transcribe · claude-saved-model · high on Claude Code");
  await expect(readyLine(page).getByText("Ready to transcribe", { exact: true })).toHaveClass(/font-medium/);
  await expect(readyLine(page).locator("svg.lucide-circle-check")).toHaveAttribute("aria-hidden", "true");
  await expect(checklist(page)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /transcribe$/ })).toHaveCount(0);
  await expect(page.getByText("Not done")).toHaveCount(0);
  const line = (await readyLine(page).boundingBox())!;
  const h1 = (await page.getByRole("heading", { name: "Settings", level: 1 }).boundingBox())!;
  const model = (await page.getByRole("heading", { name: "Transcription model" }).boundingBox())!;
  expect(line.y).toBeGreaterThan(h1.y);
  expect(line.y + line.height).toBeLessThan(model.y);
});

test("checklist: updates after saving a choice, without reloading", async ({ page }) => {
  const calls = await mockApi(page, { claude: ready(), codex: conn() }, { defaults: null });
  await page.goto("/?view=settings");
  await expect(checklist(page).getByRole("heading", { name: "Before you can transcribe" })).toBeVisible();
  const loaded = calls.get;

  await field(page, "Provider").selectOption("claude");
  await field(page, "Model").fill("sonnet");
  await field(page, "Effort").fill("low");
  await expect(checklist(page).getByRole("heading", { name: "Before you can transcribe" })).toBeVisible(); // unsaved edits change nothing
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(readyLine(page)).toHaveText("Ready to transcribe · sonnet · low on Claude Code");
  await expect(checklist(page)).toHaveCount(0);

  await field(page, "Provider").selectOption("codex");
  await field(page, "Model").fill("gpt-app-model");
  await field(page, "Effort").fill("medium");
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(checklist(page).getByRole("heading", { name: "Before you can transcribe" })).toBeVisible();
  await expect(checklistItems(page).nth(1).getByRole("link", { name: "Sign in to Codex CLI" })).toHaveAttribute("href", "#connections");
  expect(calls.get).toBe(loaded);
});

test("checklist: updates when a sign-in finishes", async ({ page }) => {
  await page.clock.install();
  const state: State = { claude: conn(), codex: conn() };
  await mockApi(page, state);
  await page.goto("/?view=settings");
  await expect(checklist(page).getByRole("heading", { name: "Before you can transcribe" })).toBeVisible();
  await claude(page).getByRole("button", { name: "Open Claude Code sign-in" }).click();
  await expect(claude(page).getByText("Finish signing in in the browser window that opened.")).toBeVisible();
  state.claude = ready({ login: { running: false, exitCode: 0 } });
  await page.clock.runFor(2000);
  await expect(readyLine(page)).toContainText("Ready to transcribe");
  await expect(checklist(page)).toHaveCount(0);
});

test("sections run Transcription model, Accounts, then the folders footer", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() });
  await page.goto("/?view=settings");
  const tops = [];
  for (const h of [page.getByRole("heading", { name: "Transcription model", level: 2 }), page.getByRole("heading", { name: "Accounts", level: 2 }), page.getByRole("heading", { name: "Folders", level: 2 })])
    tops.push((await h.evaluate((el) => el.closest("section, footer")!.getBoundingClientRect().top)));
  expect(tops[0]).toBeLessThan(tops[1]);
  expect(tops[1]).toBeLessThan(tops[2]);
  await expect(page.locator("footer", { has: page.getByRole("heading", { name: "Folders", level: 2 }) })).toBeVisible();
  await expect(page.locator("section#transcription-defaults + section#connections + footer")).toHaveCount(1);
});

test("the model row leaves no empty line under it until there is a message", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() }, { transcriptionOptions: OPTIONS, defaults: { ...SAVED, model: "opus" } });
  await page.goto("/?view=settings");
  const status = defaultsCard(page).locator("[role=status]");
  const save = page.getByRole("button", { name: "Save defaults" });
  await expect(status).toHaveText("");
  await expect(status).toHaveClass(/sr-only/);
  const gap = async () => {
    const card = (await defaultsCard(page).boundingBox())!;
    const button = (await save.boundingBox())!;
    return card.y + card.height - (button.y + button.height);
  };
  const empty = await gap();
  expect(empty).toBeLessThan(30); // the card's own padding, no reserved line
  await field(page, "Effort").selectOption("low");
  await save.click();
  await expect(status).toHaveText("Saved ✓");
  await expect(status).not.toHaveClass(/sr-only/);
  expect(await gap()).toBeGreaterThan(empty + 15);
  await field(page, "Effort").selectOption("high");
  await expect(status).toHaveText("");
  await expect(status).toHaveClass(/sr-only/);
  expect(await gap()).toBe(empty);
});

test("on a phone the ready line, the sections and the folders footer stack without sideways scroll", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: ready({ method: "chatgpt" }) });
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/?view=settings");
  await expect(readyLine(page)).toBeVisible();
  await expect(page.locator("footer").getByRole("heading", { name: "Folders" })).toBeAttached();
  await expect(page.locator("footer code")).toHaveCount(2);
  const [a, b] = [(await claude(page).boundingBox())!, (await codex(page).boundingBox())!];
  expect(b.y).toBeGreaterThan(a.y + a.height - 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("the ready line's status element is on the page before the line appears, and stays the same element", async ({ page }) => {
  await mockApi(page, { claude: ready(), codex: conn() }, { defaults: null });
  await page.goto("/?view=settings");
  await expect(checklist(page)).toBeVisible();
  const live = page.getByRole("heading", { name: "Settings", level: 1 }).locator("xpath=../following-sibling::*[@role='status']");
  await expect(live).toHaveCount(1);
  await expect(live).toHaveText("");
  await expect(live).toHaveClass(/sr-only/);
  const node = await live.elementHandle();
  await field(page, "Provider").selectOption("claude");
  await field(page, "Model").fill("sonnet");
  await field(page, "Effort").fill("low");
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(live).toHaveText("Ready to transcribe · sonnet · low on Claude Code");
  await expect(live).not.toHaveClass(/sr-only/);
  expect(await node!.evaluate((el) => el.isConnected)).toBe(true);
});
