import { test, expect, type Page } from "@playwright/test";

// Opening a PrestCribe file (/?view=import), on an intercepted API: nothing reaches the real backend or database.
const file = (name: string) => ({ name, mimeType: "application/octet-stream", buffer: Buffer.from("SQLite format 3\0") });

// The sizes of the bodies sent to POST /api/state, answered with reply.
async function mockState(page: Page, reply: { status: number; detail?: string }) {
  const sent: number[] = [];
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/state" && route.request().method() === "POST") {
      sent.push(route.request().postDataBuffer()?.length ?? 0);
      return route.fulfill({ status: reply.status, json: reply.detail ? { detail: reply.detail } : { opened: true } });
    }
    if (path === "/api/reviewers") return route.fulfill({ json: [{ id: 1, name: "Ben" }] });
    if (path === "/api/collections") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return sent;
}

test("a PrestCribe file is opened in place of everything here once asked, then home shows", async ({ page }) => {
  const sent = await mockState(page, { status: 200 });
  await page.goto("/?view=import");
  await expect(page.getByRole("heading", { name: "Open a PrestCribe file", level: 1 })).toBeVisible();
  const open = page.getByRole("button", { name: "Open", exact: true });
  await expect(open).toBeDisabled();
  await page.getByLabel("PrestCribe file").setInputFiles(file("wilfred-prest-survey.prestcribe"));
  page.once("dialog", (dialog) => { expect(dialog.message()).toContain("Replace everything here with wilfred-prest-survey.prestcribe?"); void dialog.dismiss(); });
  await open.click();
  expect(sent).toEqual([]); // not asked to
  page.once("dialog", (dialog) => void dialog.accept());
  await open.click();
  await expect(page.getByRole("heading", { name: "Series", level: 1 })).toBeVisible();
  expect(sent).toEqual([16]);
});

test("a file that isn't a PrestCribe file is refused with the server's reason", async ({ page }) => {
  await mockState(page, { status: 400, detail: "That isn't a PrestCribe file." });
  await page.goto("/?view=import");
  await page.getByLabel("PrestCribe file").setInputFiles(file("notes.txt"));
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("That isn't a PrestCribe file.");
});
