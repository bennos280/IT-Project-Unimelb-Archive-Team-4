// Exercises the export dialog and downloaded JSON with an isolated API.
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const demo = JSON.parse(
  readFileSync(
    new URL("../../../frontend/public/us7-demo/survey.json", import.meta.url),
    "utf8",
  ),
);

test("downloads backend correction instead of an unsaved on-screen edit", async ({
  page,
}) => {
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url()).pathname;
    if (url.startsWith("/api/survey/")) return route.fulfill({ json: demo });
    if (url === "/api/reviewers")
      return route.fulfill({ json: [{ reviewer_id: 1, name: "Reviewer" }] });
    return route.fulfill({
      json: {
        reviews: {
          [demo.pages[0].id]: {
            address: {
              value: "Saved address",
              original: "Old address",
              reviewer: "Reviewer",
              reviewerId: 1,
              savedAt: "2026-10-07T00:00:00Z",
            },
          },
        },
        revisions: { [demo.pages[0].id]: 1 },
      },
    });
  });
  await page.goto(`/?survey=${demo.id}`);
  await page
    .getByLabel("Reviewer name", { exact: true })
    .selectOption("Reviewer");
  await page.getByRole("button", { name: "Edit Address", exact: true }).click();
  await page
    .getByLabel("Reviewed value", { exact: true })
    .fill("Unsaved address");
  await page.getByRole("button", { name: "Apply review", exact: true }).click();
  await page.getByRole("button", { name: "Export", exact: true }).click();
  await expect(page.getByText(/Unsaved edits are excluded/)).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  const file = await downloaded;
  const payload = JSON.parse(readFileSync((await file.path())!, "utf8"));
  expect(
    payload.surveys[0].pages[0].fields.find(
      (f: { id: string }) => f.id === "address",
    ).value,
  ).toBe("Saved address");
});

test("shows backend export failure and permits retry", async ({ page }) => {
  let fail = false;
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url()).pathname;
    if (url.startsWith("/api/survey/")) return route.fulfill({ json: demo });
    if (url === "/api/reviewers") return route.fulfill({ json: [] });
    return fail
      ? route.fulfill({ status: 500, json: { detail: "Reviews unavailable" } })
      : route.fulfill({ json: { reviews: {}, revisions: {} } });
  });
  await page.goto(`/?survey=${demo.id}`);
  await page.getByRole("button", { name: "Export", exact: true }).click();
  fail = true;
  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Reviews unavailable");
  fail = false;
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  await downloaded;
  await expect(page.getByText("Export file prepared")).toBeVisible();
});
