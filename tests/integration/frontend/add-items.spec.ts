import { test, expect, type Locator, type Page } from "@playwright/test";

type Item = { node: number; title: string; identifier: string; scanned: boolean; added: boolean };
const item = (node: number, title: string, extra: Partial<Item> = {}): Item =>
  ({ node, title, identifier: `UMA-IT-${node}`, scanned: true, added: false, ...extra });
const DIARY_A = item(637675, "Strathfieldsaye Estate Diary 1878-1883");
const DIARY_B = item(637677, "Strathfieldsaye Estate Diary 1884-1890");
const LEDGER = item(637679, "Strathfieldsaye Estate Ledger", { scanned: false });
const LETTERS = item(637681, "Strathfieldsaye Estate Letters", { added: true });
const ALL = [DIARY_A, DIARY_B, LEDGER, LETTERS];
const listing = (items: Item[], extra: { page?: number; pages?: number; total?: number } = {}) =>
  ({ json: { items, page: 1, pages: 1, total: items.length, ...extra } });
const REFUSAL = "The archive has no PDF of this item.";
const TOO_MANY = "There are 29,326 items in this list, more than 1,000 to add at once. Search to narrow it down.";
// A page of 24 items; each page's numbering carries on from the one before.
const entries = (page: number) =>
  Array.from({ length: 24 }, (_, i) => item(1000 + (page - 1) * 24 + i, `Diary ${(page - 1) * 24 + i + 1}`));
const twoPages = (url: URL) => {
  const n = Number(url.searchParams.get("page"));
  return listing(entries(n), { page: n, pages: 2, total: 48 });
};

type Mock = {
  archiveSeries?: number | null;
  archiveItems?: number | null; // how many items the series had when linked; the list's size by default
  existing?: boolean; // the series already has an item
  listed?: (url: URL) => { status?: number; json: unknown }; // GET archive-items
  refuse?: Record<number, string>; // nodes the POST refuses, with the reason
  all?: { status?: number; json: unknown }; // POST items/all
  gate?: Promise<void>; // POST items/all waits for this before answering
  items?: { status: number; json: unknown }; // POST items answers with this alone
  lateAdded?: number[]; // nodes the list shows as added once an add has been posted
  hold?: (url: URL) => Promise<void> | undefined; // GET archive-items waits for this before answering
};

// The API is intercepted: no requests reach the real backend or the archive.
async function mock(page: Page, options: Mock = {}) {
  const calls = { listed: [] as URL[], posted: [] as unknown[], postedAll: [] as unknown[], bundles: 0 };
  const onList: Item[] = options.existing ? [LETTERS] : [];
  const refuse = options.refuse ?? {};
  // The dashboard polls every 5 s; with that off, a request for its list after an add is the add's own refresh.
  await page.addInitScript(() => {
    const real = window.setInterval.bind(window);
    window.setInterval = ((handler: TimerHandler, ms?: number, ...args: unknown[]) =>
      ms === 5000 ? 0 : real(handler, ms, ...args)) as typeof window.setInterval;
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/collections/1")
      return route.fulfill({
        json: {
          id: 1, name: "Estate diaries", recordName: "diary", grouped: false,
          archiveSeries: options.archiveSeries === undefined ? 499420 : options.archiveSeries,
          archiveTitle: "Strathfieldsaye Estate",
          archiveItems: options.archiveItems === undefined ? ALL.length : options.archiveItems,
        },
      });
    if (path === "/api/progress") return route.fulfill({ json: [] });
    if (path === "/api/bundles") {
      calls.bundles++;
      return route.fulfill({
        json: onList.map((i) => ({
          bundle: String(i.node), name: String(i.node), archive: { identifier: i.identifier, title: i.title },
          pdf: `${i.node}.pdf`, loaded: false, surveys: [], job: null,
        })),
      });
    }
    if (path === "/api/collections/1/archive-items") {
      calls.listed.push(url);
      await options.hold?.(url);
      const late = calls.posted.length > 0 ? options.lateAdded ?? [] : [];
      const result: { status?: number; json: unknown } = options.listed?.(url) ??
        listing(ALL.map((i) => ({ ...i, added: i.added || late.includes(i.node) || onList.some((b) => b.node === i.node) })));
      return route.fulfill({ status: result.status ?? 200, json: result.json });
    }
    if (path === "/api/collections/1/items" && request.method() === "POST") {
      const body = request.postDataJSON() as { nodes: number[] };
      calls.posted.push(body);
      if (options.items) return route.fulfill(options.items);
      const found = body.nodes.map((node) => ALL.find((i) => i.node === node)!);
      const added = found.filter((i) => !refuse[i.node]);
      onList.push(...added);
      return route.fulfill({
        json: {
          added: added.map(({ node, title }) => ({ node, title })),
          refused: found.filter((i) => refuse[i.node]).map((i) => ({ node: i.node, reason: refuse[i.node] })),
        },
      });
    }
    if (path === "/api/collections/1/items/all" && request.method() === "POST") {
      calls.postedAll.push(request.postDataJSON());
      await options.gate;
      const result: { status?: number; json: unknown } = options.all ?? { json: { added: 2, skipped: 2 } };
      if (!result.status) onList.push(DIARY_A, DIARY_B);
      return route.fulfill({ status: result.status ?? 200, json: result.json });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  await page.goto("/?collection=1");
  return calls;
}
type Calls = Awaited<ReturnType<typeof mock>>;

const dialog = (page: Page) => page.getByRole("dialog", { name: "Add items" });
const selectAll = (d: Locator) => d.getByRole("checkbox", { name: "Select all on this page", exact: true });
const emptyStateButton = (page: Page) => page.getByRole("table").getByRole("button", { name: "Add items", exact: true });
const chooseInstead = (d: Locator) => d.getByRole("button", { name: "Choose items instead", exact: true });
const lastParams = (calls: Calls) => Object.fromEntries(calls.listed[calls.listed.length - 1].searchParams);
const expectRefreshed = (calls: Calls, before: number) => expect.poll(() => calls.bundles).toBeGreaterThan(before);
// Opens the dialog from the empty state and on to the list of items.
async function openList(page: Page) {
  await emptyStateButton(page).click();
  const d = dialog(page);
  await chooseInstead(d).click();
  return d;
}

test("an empty series says so, and its Add items button opens the dialog", async ({ page }) => {
  await mock(page);
  await expect(page.getByText("No items yet.", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Add items from the archive to start. Set up the series' page types first, so its pages can be read."),
  ).toBeVisible();
  await expect(page.getByText("No items match your filters.")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add items", exact: true })).toHaveCount(2); // header and empty state
  await emptyStateButton(page).click();
  await expect(dialog(page)).toBeVisible();
  await expect(dialog(page)).toHaveAccessibleDescription("Choose items from the archive to add to Estate diaries.");
});

test("a series with no archive series linked says so without offering to add items", async ({ page }) => {
  await mock(page, { archiveSeries: null });
  await expect(page.getByText("No items yet.", { exact: true })).toBeVisible();
  await expect(page.getByText("This series isn't linked to the archive, so it has no items to add.")).toBeVisible();
  await expect(page.getByText("Add items from the archive to start.", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add items", exact: true })).toHaveCount(0);
});

test("a filter that matches nothing is not the empty state", async ({ page }) => {
  await mock(page, { existing: true });
  await expect(page.getByRole("link", { name: LETTERS.title, exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add items", exact: true })).toHaveCount(1); // header only
  await page.getByLabel("Search items").fill("zzz");
  await expect(page.getByText("No items match your filters.")).toBeVisible();
  await expect(page.getByText("No items yet.")).toHaveCount(0);
});

test("the dialog opens ready to add everything, and asks the archive for a list only when told to", async ({ page }) => {
  const calls = await mock(page);
  await emptyStateButton(page).click();
  const d = dialog(page);
  await expect(d.getByText("Estate diaries has 4 items on the archive.")).toBeVisible();
  await expect(d.getByText("Items with no scans online are skipped.")).toBeVisible();
  const all = d.getByRole("button", { name: "Add all 4 items", exact: true });
  await expect(all).toBeEnabled();
  await expect(all).toBeFocused();
  await expect(d.getByRole("textbox")).toHaveCount(0);
  await expect(d.getByRole("checkbox")).toHaveCount(0);
  expect(calls.listed).toEqual([]);
  await chooseInstead(d).click();
  await expect(d.getByRole("checkbox", { name: DIARY_A.title })).toBeVisible();
  expect(calls.listed).toHaveLength(1);
  expect(lastParams(calls)).toEqual({ page: "1" });
  await expect(d.getByRole("textbox", { name: "Search archive items" })).not.toBeFocused();
});

test("a series whose size isn't known offers to add every item", async ({ page }) => {
  const calls = await mock(page, { archiveItems: null });
  await emptyStateButton(page).click();
  const d = dialog(page);
  await expect(d.getByText("Add every item this series has on the archive.")).toBeVisible();
  await d.getByRole("button", { name: "Add all items", exact: true }).click();
  await expect(d.getByText("Added 2 items.", { exact: false })).toBeVisible();
  expect(calls.postedAll).toEqual([{ search: "" }]);
});

test("a series of one item reads Add 1 item", async ({ page }) => {
  const calls = await mock(page, { archiveItems: 1 });
  await emptyStateButton(page).click();
  const d = dialog(page);
  await expect(d.getByText("Estate diaries has 1 item on the archive.")).toBeVisible();
  await d.getByRole("button", { name: "Add 1 item", exact: true }).click();
  await expect(d.getByText("Added 2 items.", { exact: false })).toBeVisible();
  expect(calls.postedAll).toEqual([{ search: "" }]);
});

test("a series of over 1,000 items can't be added at once, and its list counts the real size", async ({ page }) => {
  const calls = await mock(page, {
    archiveItems: 60772,
    listed: (url) => listing([DIARY_A], { pages: 417, total: url.searchParams.get("search") ? 12 : 10000 }),
  });
  await emptyStateButton(page).click();
  const d = dialog(page);
  await expect(
    d.getByText("60,772 items: too many to add at once. Choose items instead, or search for the ones you want."),
  ).toBeVisible();
  await expect(d.getByRole("button", { name: "Add all 60,772 items", exact: true })).toBeDisabled();
  await expect(d).toBeFocused(); // the primary button is off, so the dialog has focus
  expect(calls.postedAll).toEqual([]);
  await chooseInstead(d).click();
  // The archive lists 10,000 at most, so the label counts the series' own 60,772.
  await expect(d.getByText("10,000 items", { exact: true })).toBeVisible();
  await expect(d.getByText("Showing the first 10,000; search to find others.")).toBeVisible();
  await expect(d.getByRole("button", { name: "Add all 60,772 items", exact: true })).toBeDisabled();
  await expect(d.getByRole("button", { name: "Add all 10,000 items" })).toHaveCount(0);
  await expect(d.getByText("Over 1,000 items: search to narrow the list, or tick the ones you want.")).toBeVisible();
  await d.getByRole("textbox", { name: "Search archive items" }).fill("diary");
  await d.getByRole("button", { name: "Search", exact: true }).click();
  await expect(d.getByRole("button", { name: "Add all 12 items", exact: true })).toBeEnabled();
});

test("Add all adds the whole series without listing it, shows progress, then the result, and refreshes at once", async ({ page }) => {
  let release = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  const calls = await mock(page, { gate });
  await emptyStateButton(page).click();
  const d = dialog(page);
  const before = calls.bundles;
  await d.getByRole("button", { name: "Add all 4 items", exact: true }).click();
  await expect(d.getByText("Adding items… a long list can take a minute.")).toBeVisible();
  for (const name of ["Cancel", "Adding…", "Choose items instead"])
    await expect(d.getByRole("button", { name, exact: true })).toBeDisabled();
  release();
  await expect(d.getByText("Added 2 items. 2 were skipped (no scans online, or already listed).", { exact: true })).toBeVisible();
  await expect(d.getByRole("button")).toHaveCount(1); // only Done
  await expectRefreshed(calls, before);
  expect(calls.postedAll).toEqual([{ search: "" }]);
  expect(calls.posted).toEqual([]);
  expect(calls.listed).toEqual([]);
  await d.getByRole("button", { name: "Done", exact: true }).click();
  await expect(d).toHaveCount(0);
  for (const entry of [DIARY_A, DIARY_B])
    await expect(page.getByRole("link", { name: entry.title, exact: true })).toBeVisible();
});

for (const [outcome, text] of [
  [{ added: 17, skipped: 0 }, "Added 17 items."],
  [{ added: 1, skipped: 1 }, "Added 1 item. 1 was skipped (no scans online, or already listed)."],
  [{ added: 15, skipped: 3 }, "Added 15 items. 3 were skipped (no scans online, or already listed)."],
] as const) {
  test(`after adding all, the dialog says "${text}"`, async ({ page }) => {
    await mock(page, { all: { json: outcome } });
    await emptyStateButton(page).click();
    const d = dialog(page);
    await d.getByRole("button", { name: "Add all 4 items", exact: true }).click();
    await expect(d.getByText(text, { exact: true })).toBeVisible();
    await d.getByRole("button", { name: "Done", exact: true }).click();
    await expect(d).toHaveCount(0);
  });
}

for (const [status, detail] of [[400, TOO_MANY], [502, "Couldn't reach the archive (timed out)"]] as const) {
  test(`adding all shows a ${status} and leaves the dialog open`, async ({ page }) => {
    const calls = await mock(page, { all: { status, json: { detail } } });
    await emptyStateButton(page).click();
    const d = dialog(page);
    await d.getByRole("button", { name: "Add all 4 items", exact: true }).click();
    await expect(d.getByRole("alert")).toContainText(detail);
    await expect(d).toBeVisible();
    expect(calls.postedAll).toEqual([{ search: "" }]);
    await expect(d.getByRole("button", { name: "Add all 4 items", exact: true })).toBeEnabled();
    await expect(chooseInstead(d)).toBeEnabled();
  });
}

test("the list shows the page's items, with unscanned and added ones disabled", async ({ page }) => {
  const calls = await mock(page, { existing: true });
  await page.getByRole("button", { name: "Add items", exact: true }).click();
  const d = dialog(page);
  await chooseInstead(d).click();
  await expect(d.getByRole("checkbox")).toHaveCount(5); // the four items and Select all
  for (const [entry, note] of [
    [DIARY_A, ""], [DIARY_B, ""], [LEDGER, " · No scans online"], [LETTERS, " · Added"],
  ] as const) {
    const box = d.getByRole("checkbox", { name: entry.title, exact: true });
    await expect(box).toHaveAccessibleDescription(`${entry.identifier} · ${entry.node}${note}`);
    if (note) await expect(box).toBeDisabled();
    else await expect(box).toBeEnabled();
  }
  await expect(d.getByText("4 items", { exact: true })).toBeVisible();
  await expect(d.getByText("Page 1 of 1")).toBeVisible();
  await expect(d.getByRole("button", { name: "Previous", exact: true })).toBeDisabled();
  await expect(d.getByRole("button", { name: "Next", exact: true })).toBeDisabled();
  await expect(d.getByText("Showing the first 10,000")).toHaveCount(0);
  await expect(d.getByText("Over 1,000 items", { exact: false })).toHaveCount(0);
  await expect(d.getByRole("button", { name: "Add all 4 items", exact: true })).toBeEnabled(); // nothing ticked
  expect(lastParams(calls)).toEqual({ page: "1" });
});

test("switching to the list and back keeps what was ticked, and Add all instead adds the whole series", async ({ page }) => {
  const calls = await mock(page);
  const d = await openList(page);
  await d.getByRole("checkbox", { name: DIARY_A.title }).check();
  await d.getByRole("textbox", { name: "Search archive items" }).fill("diary");
  await d.getByRole("button", { name: "Search", exact: true }).click();
  await expect.poll(() => lastParams(calls)).toEqual({ page: "1", search: "diary" });
  await d.getByRole("button", { name: "Add all instead", exact: true }).click();
  await expect(d.getByText("Estate diaries has 4 items on the archive.")).toBeVisible();
  await expect(d.getByRole("textbox")).toHaveCount(0);
  await chooseInstead(d).click();
  await expect(d.getByRole("checkbox", { name: DIARY_A.title })).toBeChecked();
  await expect(d.getByRole("button", { name: "Add 1 item", exact: true })).toBeEnabled();
  expect(calls.listed).toHaveLength(3);
  expect(lastParams(calls)).toEqual({ page: "1" }); // the list starts afresh
  await d.getByRole("button", { name: "Add all instead", exact: true }).click();
  // The whole series, whatever was searched or ticked.
  await d.getByRole("button", { name: "Add all 4 items", exact: true }).click();
  await expect(d.getByText("Added 2 items.", { exact: false })).toBeVisible();
  expect(calls.postedAll).toEqual([{ search: "" }]);
  expect(calls.posted).toEqual([]);
});

test("searching sends the text from page 1 on Enter or the Search button, and not while typing", async ({ page }) => {
  const calls = await mock(page, {
    listed: (url) => listing([DIARY_A], { page: Number(url.searchParams.get("page")), pages: 3, total: 60 }),
  });
  const d = await openList(page);
  await d.getByRole("button", { name: "Next", exact: true }).click();
  await expect.poll(() => lastParams(calls)).toEqual({ page: "2" });
  const requests = calls.listed.length;
  const box = d.getByRole("textbox", { name: "Search archive items" });
  await box.pressSequentially("diary");
  await box.press("Enter");
  await expect.poll(() => lastParams(calls)).toEqual({ page: "1", search: "diary" });
  expect(calls.listed.length).toBe(requests + 1);
  await box.fill("ledger");
  await d.getByRole("button", { name: "Search", exact: true }).click();
  await expect.poll(() => lastParams(calls)).toEqual({ page: "1", search: "ledger" });
});

test("Next and Previous change page and keep what was chosen", async ({ page }) => {
  const second = item(637683, "Strathfieldsaye Estate Account Book");
  const calls = await mock(page, {
    listed: (url) => {
      const n = Number(url.searchParams.get("page"));
      return listing(n === 1 ? [DIARY_A, DIARY_B] : [second], { page: n, pages: 2, total: 30 });
    },
  });
  const d = await openList(page);
  await expect(d.getByText("30 items", { exact: true })).toBeVisible();
  await expect(d.getByText("Page 1 of 2")).toBeVisible();
  await expect(d.getByRole("button", { name: "Previous", exact: true })).toBeDisabled();
  await d.getByRole("checkbox", { name: DIARY_A.title }).check();
  await d.getByRole("button", { name: "Next", exact: true }).click();
  await expect.poll(() => lastParams(calls)).toEqual({ page: "2" });
  await expect(d.getByText("Page 2 of 2")).toBeVisible();
  await expect(d.getByRole("button", { name: "Next", exact: true })).toBeDisabled();
  await d.getByRole("checkbox", { name: second.title }).check();
  await expect(d.getByRole("button", { name: "Add 2 items", exact: true })).toBeEnabled();
  await d.getByRole("button", { name: "Previous", exact: true }).click();
  await expect.poll(() => lastParams(calls)).toEqual({ page: "1" });
  await expect(d.getByRole("checkbox", { name: DIARY_A.title })).toBeChecked();
});

test("no more than 25 can be chosen at a time", async ({ page }) => {
  await mock(page, { listed: twoPages });
  const d = await openList(page);
  await expect(d.getByRole("checkbox", { name: /^Diary \d+$/ })).toHaveCount(24);
  for (const box of await d.getByRole("checkbox", { name: /^Diary \d+$/ }).all()) await box.check();
  await expect(d.getByRole("button", { name: "Add 24 items", exact: true })).toBeEnabled();
  await expect(d.getByText("Add up to 25 at a time")).toHaveCount(0);
  await d.getByRole("button", { name: "Next", exact: true }).click();
  await d.getByRole("checkbox", { name: "Diary 25", exact: true }).check();
  await expect(d.getByText("Add up to 25 at a time")).toBeVisible();
  await expect(d.getByRole("button", { name: "Add 25 items", exact: true })).toBeEnabled();
  await expect(d.getByRole("checkbox", { name: "Diary 26", exact: true })).toBeDisabled();
  await expect(d.getByRole("checkbox", { name: "Diary 25", exact: true })).toBeEnabled();
  await d.getByRole("checkbox", { name: "Diary 25", exact: true }).uncheck();
  await expect(d.getByText("Add up to 25 at a time")).toHaveCount(0);
  await expect(d.getByRole("checkbox", { name: "Diary 26", exact: true })).toBeEnabled();
});

test("a result of 10,000 or more says only the first 10,000 are listed", async ({ page }) => {
  await mock(page, { listed: () => listing([DIARY_A], { pages: 417, total: 10000 }) });
  const d = await openList(page);
  await expect(d.getByText("10,000 items", { exact: true })).toBeVisible();
  await expect(d.getByText("Showing the first 10,000; search to find others.")).toBeVisible();
});

test("adding two items posts them, closes the dialog and refreshes the list at once", async ({ page }) => {
  const calls = await mock(page);
  const d = await openList(page);
  await d.getByRole("checkbox", { name: DIARY_A.title }).check();
  await d.getByRole("checkbox", { name: DIARY_B.title }).check();
  const before = calls.bundles;
  await d.getByRole("button", { name: "Add 2 items", exact: true }).click();
  await expect(d).toHaveCount(0);
  expect(calls.posted).toEqual([{ nodes: [DIARY_A.node, DIARY_B.node] }]);
  await expectRefreshed(calls, before);
  for (const entry of [DIARY_A, DIARY_B]) {
    const row = page.getByRole("row").filter({ has: page.getByRole("link", { name: entry.title, exact: true }) });
    await expect(row.getByRole("button", { name: "Transcribe", exact: true })).toBeVisible();
  }
  await expect(page.getByText("No items yet.")).toHaveCount(0);
});

test("a refused item is explained, the added one is unchecked and the list refreshes", async ({ page }) => {
  const calls = await mock(page, { refuse: { [DIARY_B.node]: REFUSAL } });
  const d = await openList(page);
  await d.getByRole("checkbox", { name: DIARY_A.title }).check();
  await d.getByRole("checkbox", { name: DIARY_B.title }).check();
  const before = calls.bundles;
  await d.getByRole("button", { name: "Add 2 items", exact: true }).click();
  await expect(d.getByRole("alert")).toContainText(`${DIARY_B.title}: ${REFUSAL}`);
  await expect(d.getByRole("alert")).not.toContainText(DIARY_A.title);
  await expect(d).toBeVisible();
  await expectRefreshed(calls, before);
  const added = d.getByRole("checkbox", { name: DIARY_A.title });
  await expect(added).toBeDisabled();
  await expect(added).not.toBeChecked();
  await expect(added).toHaveAccessibleDescription(`${DIARY_A.identifier} · ${DIARY_A.node} · Added`);
  await expect(d.getByRole("checkbox", { name: DIARY_B.title })).toBeChecked();
  await expect(d.getByRole("button", { name: "Add 1 item", exact: true })).toBeEnabled();
});

test("an archive that can't be reached shows why, and Try again asks again", async ({ page }) => {
  let down = true;
  const calls = await mock(page, {
    listed: () => down
      ? { status: 502, json: { detail: "Couldn't reach the archive (timed out)" } }
      : listing(ALL),
  });
  const d = await openList(page);
  await expect(d.getByRole("alert")).toContainText("Couldn't reach the archive (timed out)");
  await expect(d.getByRole("checkbox")).toHaveCount(0);
  const requests = calls.listed.length;
  down = false;
  await d.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(d.getByRole("checkbox")).toHaveCount(5);
  expect(calls.listed.length).toBe(requests + 1);
  await expect(d.getByRole("alert")).toHaveCount(0);
});

test("Select all on this page ticks only the items that can be added, and follows the boxes", async ({ page }) => {
  await mock(page);
  const d = await openList(page);
  const all = selectAll(d);
  await expect(all).toBeEnabled();
  await expect(all).not.toBeChecked();
  await all.check();
  for (const entry of [DIARY_A, DIARY_B]) await expect(d.getByRole("checkbox", { name: entry.title })).toBeChecked();
  for (const entry of [LEDGER, LETTERS]) await expect(d.getByRole("checkbox", { name: entry.title })).not.toBeChecked();
  await expect(d.getByRole("button", { name: "Add 2 items", exact: true })).toBeEnabled();
  await all.uncheck();
  await expect(d.getByRole("checkbox", { name: DIARY_A.title })).not.toBeChecked();
  await expect(d.getByRole("button", { name: "Add all 4 items", exact: true })).toBeEnabled();
  await d.getByRole("checkbox", { name: DIARY_A.title }).check();
  await expect(all).not.toBeChecked();
  await d.getByRole("checkbox", { name: DIARY_B.title }).check();
  await expect(all).toBeChecked();
});

test("Select all on this page is disabled when nothing on the page can be added", async ({ page }) => {
  await mock(page, { listed: () => listing([LEDGER, LETTERS]) });
  const d = await openList(page);
  await expect(d.getByRole("checkbox", { name: LEDGER.title })).toBeDisabled();
  await expect(selectAll(d)).toBeDisabled();
});

test("Select all on this page stops at the 25 cap, and unticking it leaves other pages' items", async ({ page }) => {
  await mock(page, { listed: twoPages });
  const d = await openList(page);
  await selectAll(d).check();
  await expect(d.getByRole("button", { name: "Add 24 items", exact: true })).toBeEnabled();
  await expect(d.getByText("Add up to 25 at a time")).toHaveCount(0);
  await d.getByRole("button", { name: "Next", exact: true }).click();
  await expect(d.getByText("Page 2 of 2")).toBeVisible();
  await selectAll(d).click(); // only the first of this page fits
  await expect(d.getByRole("button", { name: "Add 25 items", exact: true })).toBeEnabled();
  await expect(d.getByText("Add up to 25 at a time")).toBeVisible();
  await expect(d.getByRole("checkbox", { name: "Diary 25", exact: true })).toBeChecked();
  await expect(d.getByRole("checkbox", { name: "Diary 26", exact: true })).not.toBeChecked();
  await expect(d.getByRole("checkbox", { name: "Diary 26", exact: true })).toBeDisabled();
  await expect(selectAll(d)).not.toBeChecked();
  await d.getByRole("button", { name: "Previous", exact: true }).click();
  await expect(selectAll(d)).toBeChecked();
  await selectAll(d).uncheck();
  await expect(d.getByRole("button", { name: "Add 1 item", exact: true })).toBeEnabled();
  await expect(d.getByText("Add up to 25 at a time")).toHaveCount(0);
});

test("in the list with nothing ticked the footer adds the whole list, locking the list while it works", async ({ page }) => {
  let release = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  const calls = await mock(page, { gate, listed: twoPages });
  const d = await openList(page);
  await d.getByRole("button", { name: "Add all 48 items", exact: true }).click();
  await expect(d.getByText("Adding items… a long list can take a minute.")).toBeVisible();
  for (const name of ["Cancel", "Search", "Adding…", "Next", "Add all instead"])
    await expect(d.getByRole("button", { name, exact: true })).toBeDisabled();
  await expect(selectAll(d)).toBeDisabled();
  await expect(d.getByRole("checkbox", { name: "Diary 1", exact: true })).toBeDisabled();
  release();
  await expect(d.getByText("Added 2 items. 2 were skipped (no scans online, or already listed).", { exact: true })).toBeVisible();
  expect(calls.postedAll).toEqual([{ search: "" }]);
  expect(calls.posted).toEqual([]);
});

test("adding the list adds the submitted search's results, not text typed since", async ({ page }) => {
  const calls = await mock(page);
  const d = await openList(page);
  const box = d.getByRole("textbox", { name: "Search archive items" });
  await box.fill("diary");
  await box.press("Enter");
  await expect.poll(() => lastParams(calls)).toEqual({ page: "1", search: "diary" });
  await box.fill("ledger");
  await d.getByRole("button", { name: "Add all 4 items", exact: true }).click();
  await expect(d.getByText("Added 2 items.", { exact: false })).toBeVisible();
  expect(calls.postedAll).toEqual([{ search: "diary" }]);
});

test("ticking items switches the footer to adding just those, and unticking them back to the list", async ({ page }) => {
  const calls = await mock(page);
  const d = await openList(page);
  const box = d.getByRole("checkbox", { name: DIARY_A.title });
  await box.check();
  await expect(d.getByRole("button", { name: "Add all 4 items", exact: true })).toHaveCount(0);
  await box.uncheck();
  await expect(d.getByRole("button", { name: "Add all 4 items", exact: true })).toBeEnabled();
  await box.check();
  await d.getByRole("button", { name: "Add 1 item", exact: true }).click();
  await expect(d).toHaveCount(0);
  expect(calls.posted).toEqual([{ nodes: [DIARY_A.node] }]);
  expect(calls.postedAll).toEqual([]);
});

test("a list of one reads Add 1 item and still adds the list", async ({ page }) => {
  const calls = await mock(page, { listed: () => listing([DIARY_A]) });
  const d = await openList(page);
  await d.getByRole("button", { name: "Add 1 item", exact: true }).click();
  await expect(d.getByText("Added 2 items.", { exact: false })).toBeVisible();
  expect(calls.postedAll).toEqual([{ search: "" }]);
});

test("over 1,000 items the list's footer is off until a search narrows it or items are ticked", async ({ page }) => {
  await mock(page, {
    listed: (url) => listing([DIARY_A], { total: url.searchParams.get("search") ? 1000 : 1001 }),
  });
  const d = await openList(page);
  const hint = d.getByText("Over 1,000 items: search to narrow the list, or tick the ones you want.");
  await expect(d.getByRole("button", { name: "Add all 1,001 items", exact: true })).toBeDisabled();
  await expect(hint).toBeVisible();
  await d.getByRole("checkbox", { name: DIARY_A.title }).check();
  await expect(d.getByRole("button", { name: "Add 1 item", exact: true })).toBeEnabled();
  await expect(hint).toHaveCount(0);
  await d.getByRole("checkbox", { name: DIARY_A.title }).uncheck();
  await expect(d.getByRole("button", { name: "Add all 1,001 items", exact: true })).toBeDisabled();
  await d.getByRole("textbox", { name: "Search archive items" }).fill("diary");
  await d.getByRole("button", { name: "Search", exact: true }).click();
  await expect(d.getByRole("button", { name: "Add all 1,000 items", exact: true })).toBeEnabled();
  await expect(hint).toHaveCount(0);
});

test("an item refused as already listed leaves the selection once the list shows it added", async ({ page }) => {
  await mock(page, { refuse: { [DIARY_B.node]: "A series lists it already." }, lateAdded: [DIARY_B.node] });
  const d = await openList(page);
  await d.getByRole("checkbox", { name: DIARY_A.title }).check();
  await d.getByRole("checkbox", { name: DIARY_B.title }).check();
  await d.getByRole("button", { name: "Add 2 items", exact: true }).click();
  await expect(d.getByRole("alert")).toContainText(`${DIARY_B.title}: A series lists it already.`);
  const refused = d.getByRole("checkbox", { name: DIARY_B.title });
  await expect(refused).toBeDisabled();
  await expect(refused).not.toBeChecked();
  // Nothing is left ticked, so the footer is back to adding the list.
  await expect(d.getByRole("button", { name: "Add all 4 items", exact: true })).toBeEnabled();
});

test("paging keeps the old page up, dimmed, until the next arrives, and keeps focus on Next", async ({ page }) => {
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await mock(page, {
    listed: (url) => {
      const n = Number(url.searchParams.get("page"));
      return listing(entries(n), { page: n, pages: 3, total: 72 });
    },
    hold: (url) => (url.searchParams.get("page") === "2" ? held : undefined),
  });
  const d = await openList(page);
  const next = d.getByRole("button", { name: "Next", exact: true });
  await expect(d.getByText("Page 1 of 3")).toBeVisible();
  await next.focus();
  await page.keyboard.press("Enter");
  await expect(d.getByText("Loading items from the archive…")).toBeVisible();
  await expect(d.locator('[aria-busy="true"]')).toBeVisible();
  await expect(d.getByRole("checkbox", { name: "Diary 1", exact: true })).toBeVisible(); // still page 1
  await expect(next).toBeDisabled();
  release();
  await expect(d.getByText("Page 2 of 3")).toBeVisible();
  await expect(d.getByRole("checkbox", { name: "Diary 25", exact: true })).toBeVisible();
  await expect(d.locator('[aria-busy="true"]')).toHaveCount(0);
  await expect(next).toBeEnabled();
  await expect(next).toBeFocused();
});

for (const [status, detail] of [
  [409, "Another change to this series is in progress. Try again in a moment."],
  [502, "Couldn't reach the archive (timed out)"],
] as const) {
  test(`a ${status} on adding the ticked items shows why, leaves the dialog open and keeps them ticked`, async ({ page }) => {
    const calls = await mock(page, { items: { status, json: { detail } } });
    const d = await openList(page);
    await d.getByRole("checkbox", { name: DIARY_A.title }).check();
    await d.getByRole("checkbox", { name: DIARY_B.title }).check();
    const before = calls.bundles;
    await d.getByRole("button", { name: "Add 2 items", exact: true }).click();
    await expect(d.getByRole("alert")).toContainText(detail);
    await expect(d).toBeVisible();
    expect(calls.posted).toEqual([{ nodes: [DIARY_A.node, DIARY_B.node] }]);
    await expect(d.getByRole("checkbox", { name: DIARY_A.title })).toBeChecked();
    await expect(d.getByRole("checkbox", { name: DIARY_B.title })).toBeChecked();
    await expect(d.getByRole("button", { name: "Add 2 items", exact: true })).toBeEnabled();
    expect(calls.bundles).toBe(before); // nothing was added, so the dashboard isn't refreshed
  });
}
