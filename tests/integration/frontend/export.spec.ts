// Tests the export dialog and downloaded JSON with an isolated API.
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const demo = {
  id: "export-test",
  title: "Export test",
  pages: [
    {
      id: "page0",
      type: "main",
      imageUrl: "/scan.png",
      flags: [],
      fields: [
        {
          id: "address",
          label: "Address",
          group: "Address",
          value: "Original",
        },
      ],
    },
  ],
};
const exported = {
  surveys: [
    {
      surveyId: demo.id,
      status: "Reviewed",
      pages: [
        {
          pageId: "page0",
          label: "main",
          status: "Reviewed",
          flags: [],
          fields: [
            {
              id: "address",
              label: "Address",
              group: "Address",
              value: "Saved address",
              status: "Reviewed",
            },
          ],
        },
      ],
    },
  ],
};

// The page actions menu loads its context on the review screen; export tests only need a valid one.
const pageActions = { bundleId: "bundle-test", surveyId: "export-test", category: "main", needsTranscription: false,
  revision: 0, hasReviews: false, job: null, surveys: [] };

// Confirms the downloaded JSON uses the saved backend correction and excludes an unsaved edit in the review screen.
test("downloads backend correction instead of an unsaved on-screen edit", async ({
  page,
}) => {
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url()).pathname;
    if (url.startsWith("/api/page-actions/")) return route.fulfill({ json: pageActions });
    if (url === "/api/export") return route.fulfill({ json: exported });
    if (url.startsWith("/api/survey/")) return route.fulfill({ json: demo });
    if (url === "/api/reviewers")
      return route.fulfill({ json: [{ id: 1, name: "Reviewer" }] });
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

// Checks that an export failure is shown to the reviewer and retrying successfully downloads the file.
test("shows backend export failure and permits retry", async ({ page }) => {
  let fail = false;
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url()).pathname;
    if (url.startsWith("/api/page-actions/")) return route.fulfill({ json: pageActions });
    if (url.startsWith("/api/survey/")) return route.fulfill({ json: demo });
    if (url === "/api/reviewers") return route.fulfill({ json: [] });
    if (url === "/api/export")
      return fail
        ? route.fulfill({ status: 500, json: { detail: "Export unavailable" } })
        : route.fulfill({ json: exported });
    return route.fulfill({ json: { reviews: {}, revisions: {} } });
  });
  await page.goto(`/?survey=${demo.id}`);
  await page.getByRole("button", { name: "Export", exact: true }).click();
  fail = true;
  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Export unavailable");
  fail = false;
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  await downloaded;
  await expect(page.getByText("Export file prepared")).toBeVisible();
});

// Checks that choosing a bundle sends its ID and downloads JSON with the matching bundle ID and filename.
test("downloads a selected bundle as JSON", async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/page-actions/")) return route.fulfill({ json: pageActions });
    if (url.pathname === "/api/export/bundles")
      return route.fulfill({ json: [{ id: "bundle-test", name: "123" }] });
    if (url.pathname === "/api/export") {
      expect(url.searchParams.get("bundle_id")).toBe("bundle-test");
      return route.fulfill({
        json: { bundleId: "bundle-test", ...exported, unassignedPages: [] },
      });
    }
    if (url.pathname.startsWith("/api/survey/"))
      return route.fulfill({ json: demo });
    if (url.pathname === "/api/reviewers") return route.fulfill({ json: [] });
    return route.fulfill({ json: { reviews: {}, revisions: {} } });
  });
  await page.goto(`/?survey=${demo.id}`);
  await page.getByRole("button", { name: "Export", exact: true }).click();
  await page.getByRole("radio", { name: /Export bundle JSON/ }).check();
  await expect(
    page.getByRole("button", { name: "Export JSON", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Bundle number").selectOption("bundle-test");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("bundle-bundle-test-export.json");
  expect(JSON.parse(readFileSync((await file.path())!, "utf8")).bundleId).toBe(
    "bundle-test",
  );
});

// Checks that dashboard export preselects the current bundle and requests its database ID rather than its display number.
test("dashboard exports the selected bundle ID rather than its display number", async ({
  page,
}) => {
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/page-actions/")) return route.fulfill({ json: pageActions });
    if (url.pathname === "/api/progress")
      return route.fulfill({
        json: [{ id: "db-bundle-abc", name: "123", pages: [] }],
      });
    if (url.pathname === "/api/bundles") return route.fulfill({ json: [] });
    if (url.pathname === "/api/export/bundles")
      return route.fulfill({ json: [{ id: "db-bundle-abc", name: "123" }] });
    if (url.pathname === "/api/export") {
      expect(url.searchParams.get("bundle_id")).toBe("db-bundle-abc");
      expect(url.searchParams.has("survey_id")).toBe(false);
      return route.fulfill({
        json: { bundleId: "db-bundle-abc", ...exported, unassignedPages: [] },
      });
    }
    return route.fulfill({
      status: 404,
      json: { detail: "Unexpected request" },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "123", exact: true }).click();
  await page.getByRole("button", { name: "Export", exact: true }).click();
  await expect(
    page.getByRole("radio", { name: /Export bundle JSON/ }),
  ).toBeChecked();
  await expect(page.getByLabel("Bundle number")).toHaveValue("db-bundle-abc");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("bundle-db-bundle-abc-export.json");
  expect(JSON.parse(readFileSync((await file.path())!, "utf8")).bundleId).toBe(
    "db-bundle-abc",
  );
});

// Checks that Current bundle on the review screen downloads the bundle identified by the survey response.
test("review screen exports its current bundle using the backend bundle ID", async ({
  page,
}) => {
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/page-actions/")) return route.fulfill({ json: pageActions });
    if (url.pathname.startsWith("/api/survey/"))
      return route.fulfill({ json: { ...demo, bundleId: "actual-bundle-id" } });
    if (url.pathname === "/api/export/bundles")
      return route.fulfill({ json: [{ id: "actual-bundle-id", name: "123" }] });
    if (url.pathname === "/api/export") {
      expect(url.searchParams.get("bundle_id")).toBe("actual-bundle-id");
      expect(url.searchParams.has("survey_id")).toBe(false);
      return route.fulfill({
        json: {
          ...exported,
          bundleId: "actual-bundle-id",
          unassignedPages: [],
        },
      });
    }
    if (url.pathname === "/api/reviewers") return route.fulfill({ json: [] });
    return route.fulfill({ json: { reviews: {}, revisions: {} } });
  });
  await page.goto(`/?survey=${demo.id}`);
  await page.getByRole("button", { name: "Export", exact: true }).click();
  await page.getByRole("radio", { name: /Current bundle/ }).check();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("bundle-actual-bundle-id-export.json");
  expect(JSON.parse(readFileSync((await file.path())!, "utf8")).bundleId).toBe(
    "actual-bundle-id",
  );
});

// The warning follows saved review status, rather than appearing on every export.
test("warns for unreviewed data and clears the warning for a reviewed selection", async ({
  page,
}) => {
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/page-actions/")) return route.fulfill({ json: pageActions });
    if (url.pathname.startsWith("/api/survey/"))
      return route.fulfill({ json: demo });
    if (
      url.pathname === "/api/reviewers" ||
      url.pathname === "/api/export/bundles"
    )
      return route.fulfill({ json: [] });
    if (url.pathname === "/api/export") {
      const payload = structuredClone(exported);
      if (url.searchParams.get("survey_id") === demo.id) {
        payload.surveys[0].status = "ToBeReviewed";
        payload.surveys[0].pages[0].status = "ToBeReviewed";
        payload.surveys[0].pages[0].fields[0].status = "ToBeReviewed";
      }
      return route.fulfill({ json: payload });
    }
    return route.fulfill({ json: { reviews: {}, revisions: {} } });
  });
  await page.goto(`/?survey=${demo.id}`);
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const warning = page.getByText(
    /This contains fields that are still awaiting review/,
  );
  await expect(warning).toBeVisible();
  await page.getByLabel("Survey ID *", { exact: true }).fill("reviewed-survey");
  await expect(warning).toBeHidden();
  await expect(
    page.getByRole("button", { name: "Export JSON", exact: true }),
  ).toBeEnabled();
});

// Both dashboard entry points use the same warning for surveys and bundles.
for (const selectedBundle of [false, true]) {
  test(`conditional export warning on ${selectedBundle ? "selected bundle" : "all bundles"} dashboard`, async ({
    page,
  }) => {
    await page.route("**/api/**", (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.startsWith("/api/page-actions/")) return route.fulfill({ json: pageActions });
      if (url.pathname === "/api/progress")
        return route.fulfill({
          json: [{ id: "pending", name: "123", pages: [] }],
        });
      if (url.pathname === "/api/bundles") return route.fulfill({ json: [] });
      if (url.pathname === "/api/export/bundles")
        return route.fulfill({
          json: [
            { id: "pending", name: "123" },
            { id: "reviewed", name: "456" },
          ],
        });
      if (url.pathname === "/api/export") {
        const pending =
          (url.searchParams.get("bundle_id") ??
            url.searchParams.get("survey_id")) === "pending";
        return route.fulfill({
          json: {
            ...exported,
            unassignedPages: pending
              ? [{ pageId: "loose", status: "ToBeReviewed" }]
              : [],
          },
        });
      }
      return route.fulfill({
        status: 404,
        json: { detail: "Unexpected request" },
      });
    });
    await page.goto("/");
    if (selectedBundle)
      await page.getByRole("button", { name: "123", exact: true }).click();
    await page.getByRole("button", { name: "Export", exact: true }).click();
    const warning = page.getByText(
      /This contains fields that are still awaiting review/,
    );
    if (!selectedBundle) {
      await expect(warning).toBeHidden();
      await page.getByLabel("Bundle number").selectOption("pending");
    }
    await expect(warning).toBeVisible();
    const checked = page.waitForResponse((response) =>
      response.url().includes("bundle_id=reviewed"),
    );
    await page.getByLabel("Bundle number").selectOption("reviewed");
    await checked;
    await expect(warning).toBeHidden();
    await page.getByRole("radio", { name: /Survey ID JSON/ }).check();
    await page.getByLabel("Survey ID *", { exact: true }).fill("pending");
    await expect(warning).toBeVisible();
    await page.getByLabel("Survey ID *", { exact: true }).fill("");
    await expect(warning).toBeHidden();
  });
}
