// Real browser interactions with an isolated, per-test API fixture.
import { test as base, expect, type Page } from "@playwright/test";
import type { Survey } from "../../../frontend/src/review-screen/model";

// Defines the saved review returned by mock API.
type SavedReview = {
  value: string | null;
  original: string | null;
  reviewer: string;
  reviewerId: number;
  savedAt: string;
};

// Stores each test's simulated failures, successful save count,
// saved reviews, and page revisions.
type State = {
  failLoad: boolean;
  failSave: boolean;
  saves: number;
  reviews: Record<string, Record<string, SavedReview>>;
  revisions: Record<string, number>;
};
// Small sample survey for browser tests; no demo JSON or database is needed.
const demo: Survey = {
  id: "test-survey",
  title: "Test survey",
  pages: [
    {
      id: "test-bundle/p0",
      type: "main",
      imageUrl: "/test-images/main.jpg",
      fields: [
        { id: "address", label: "Address", group: "Address", value: "10 Sample Street" },
        { id: "municipality", label: "Municipality", group: "Address", value: null },
      ],
      flags: [
        {
          id: "address-uncertain",
          fieldId: "address",
          kind: "uncertain",
          reason: "The handwriting needs checking.",
        },
      ],
    },
    {
      id: "test-bundle/p1",
      type: "notes",
      imageUrl: "/test-images/notes.jpg",
      fields: [
        { id: "text", label: "Notes", group: "Notes", value: "Interview notes." },
      ],
      flags: [],
    },
    {
      id: "test-bundle/p2",
      type: "coded",
      imageUrl: "/test-images/coded.jpg",
      fields: [
        { id: "number_of_dwelling", label: "Number of dwelling", group: "Left column", value: "12" },
      ],
      flags: [],
    },
  ],
};

// Creates a fresh mock API for each test so reviews and reviewers
// are isolated and API requests never reach the real backend.
const test = base.extend<{ api: State }>({
  api: async ({ page }, use) => {
    const state: State = {
      failLoad: false,
      failSave: false,
      saves: 0,
      reviews: {},
      revisions: {},
    };
    const people = [{ reviewer_id: 1, name: "Test reviewer" }];
    // Serve a predictable image so viewer tests do not depend on demo scan files.
    await page.route("**/test-images/*.jpg", (route) => route.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><rect width="1200" height="800" fill="white"/></svg>',
    }));
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const reply = (body: unknown, status = 200) =>
        route.fulfill({ status, json: body });
      if (path.startsWith("/api/survey/"))
        return state.failLoad
          ? reply({ detail: "Test survey unavailable" }, 500)
          : reply(demo);
      if (path === "/api/reviewers") {
        if (request.method() === "POST") {
          const payload = request.postDataJSON();
          const person = { reviewer_id: payload.id, name: payload.name };
          people.push(person);
          return reply(person);
        }
        return reply(people);
      }
      if (path.startsWith("/api/reviews/")) {
        if (request.method() === "POST") {
          if (state.failSave)
            return reply({ detail: "Page changed in another tab." }, 409);
          const payload = request.postDataJSON();
          const pageId = Object.keys(payload.reviews)[0];
          if (payload.revisions[pageId] !== (state.revisions[pageId] || 0) + 1)
            return reply({ detail: "Outdated revision" }, 409);
          const savedAt = "2026-10-05T01:00:00Z";
          for (const [fieldId, review] of Object.entries(
            payload.reviews[pageId] as Record<string, SavedReview>,
          )) {
            state.reviews[pageId] ??= {};
            state.reviews[pageId][fieldId] = { ...review, savedAt };
          }
          state.revisions[pageId] = payload.revisions[pageId];
          state.saves++;
          return reply({ revision: state.revisions[pageId], savedAt });
        }
        return reply({ reviews: state.reviews, revisions: state.revisions });
      }
      // Never allow a test API write through to a real server.
      return reply({ detail: `Unhandled test route: ${path}` }, 404);
    });
    await use(state);
  },
});

// Finds the Address row using its edit button.
const address = (page: Page) =>
  page.locator("tr.field").filter({
    has: page.getByRole("button", { name: "Edit Address", exact: true }),
  });

// Opens Address, enters a value, and applies an unsaved review.
// The caller must select a reviewer first.
async function edit(page: Page, value: string) {
  await page.getByRole("button", { name: "Edit Address", exact: true }).click();
  await page.getByLabel("Reviewed value", { exact: true }).fill(value);
  await page.getByRole("button", { name: "Apply review", exact: true }).click();
}

// Opens the demo survey and waits for the review screen before each test.
test.beforeEach(async ({ page, api }) => {
  expect(api.saves).toBe(0);
  await page.goto(`/?survey=${demo.id}`);
  await expect(address(page)).toBeVisible();
});

// Checks page navigation, matching field counts and scan URLs, successful
// image loading, and disabled navigation buttons at the first and last pages.
test("Next/Previous show matching page data and image", async ({ page }) => {
  await expect(
    page.getByRole("button", { name: "Previous page", exact: true }),
  ).toBeDisabled();
  for (let index = 0; index < demo.pages.length; index++) {
    const source = demo.pages[index];
    await expect(page.locator(".page-heading h2")).toContainText(source.id);
    await expect(page.locator("tr.field")).toHaveCount(source.fields.length);
    await expect(page.locator(".scan-stage img")).toHaveAttribute(
      "src",
      source.imageUrl,
    );
    await expect
      .poll(() =>
        page
          .locator(".scan-stage img")
          .evaluate(
            (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
          ),
      )
      .toBe(true);
    if (index < demo.pages.length - 1)
      await page
        .getByRole("button", { name: "Next page", exact: true })
        .click();
  }
  await expect(
    page.getByRole("button", { name: "Next page", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Previous page", exact: true })
    .click();
  await expect(page.locator(".page-heading h2")).toContainText(
    demo.pages[1].id,
  );
});

// Checks that Address remains visible when searched, an unmatched search
// shows an empty state, and Clear filters restores every field.
test("Search and Clear filters return expected rows", async ({ page }) => {
  await page.getByRole("textbox", { name: "Search fields" }).fill("Address");
  await expect(address(page)).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search fields" })
    .fill("no-match-987654321");
  await expect(page.getByText("No fields match your filters.")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.locator("tr.field")).toHaveCount(
    demo.pages[0].fields.length,
  );
});

// Checks that the flag filter shows only flagged fields and expanding
// the first flag displays its explanation from the fixture.
test("Flag filter and disclosure show the reason", async ({ page }) => {
  await page
    .getByRole("combobox", { name: "Filter fields" })
    .selectOption("flagged");
  await expect(page.locator("tr.field")).toHaveCount(
    new Set(demo.pages[0].flags.map((f) => f.fieldId)).size,
  );
  const disclosure = page.locator(".flag-details").first();
  await disclosure.locator("summary").click();
  await expect(disclosure.locator(".flag-reason p").first()).toHaveText(
    demo.pages[0].flags[0].reason,
  );
});

// Checks the zoom buttons change the displayed percentage and Fit to Page
// fits the complete scan inside the viewer without significant overflow.
test("Zoom and Fit to Page change the image scale", async ({ page }) => {
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(page.locator(".zoom output")).toHaveText("125%");
  await page.getByRole("button", { name: "Zoom out", exact: true }).click();
  await expect(page.locator(".zoom output")).toHaveText("100%");
  await expect(page.getByRole("button", { name: "Fit to Page" })).toBeEnabled();
  await page.getByRole("button", { name: "Fit to Page" }).click();
  await expect
    .poll(() =>
      page
        .locator(".image-viewport")
        .evaluate(
          (el) =>
            el.scrollWidth <= el.clientWidth + 2 &&
            el.scrollHeight <= el.clientHeight + 2,
        ),
    )
    .toBe(true);
});

// Checks that selecting Address shows its named highlight and zooms to 200%.
// This does not check whether the highlight's coordinates are correct.
test("Clicking Address highlights its scan area", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Fit to Page" })).toBeEnabled();
  await address(page).locator(".locate-field").click();
  await expect(page.locator(".source-highlight")).toHaveAttribute(
    "aria-label",
    "Highlighted source: Address",
  );
  await expect(page.locator(".zoom output")).toHaveText("200%");
});

// Checks that applying a review requires a reviewer and cancelling the
// editor leaves the original value unchanged without saving.
test("Cancel discards draft text and reviewer is required", async ({
  page,
  api,
}) => {
  const original = await address(page).locator(".value").innerText();
  await page.getByRole("button", { name: "Edit Address", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Apply review" }),
  ).toBeDisabled();
  await page
    .getByLabel("Reviewed value", { exact: true })
    .fill("Cancelled text");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(address(page).locator(".value")).toHaveText(original);
  expect(api.saves).toBe(0);
});

// Checks that Apply creates an unsaved review, Save stores it in the mock
// API with revision 1, and refreshing reloads the saved correction.
test("Apply creates draft; Save persists and reload restores it", async ({
  page,
  api,
}) => {
  await page
    .getByRole("combobox", { name: "Reviewer name", exact: true })
    .selectOption("Test reviewer");
  await edit(page, "10 Test Street");
  await expect(address(page)).toContainText("Unsaved by: Test reviewer");
  expect(api.saves).toBe(0);
  await page
    .getByRole("button", { name: "Save Page Transcript", exact: true })
    .click();
  await expect(address(page)).toContainText("Reviewed by: Test reviewer");
  expect(api.reviews[demo.pages[0].id].address.value).toBe("10 Test Street");
  expect(api.revisions[demo.pages[0].id]).toBe(1);
  await page.reload();
  await expect(address(page).locator(".value")).toHaveText("10 Test Street");
  await expect(address(page)).toContainText("Reviewed by: Test reviewer");
});

// Checks that a rejected save displays the API error and retains the
// correction as unsaved so the reviewer does not lose their work.
test("Rejected save displays reason and retains unsaved correction", async ({
  page,
  api,
}) => {
  api.failSave = true;
  await page
    .getByRole("combobox", { name: "Reviewer name", exact: true })
    .selectOption("Test reviewer");
  await edit(page, "Keep this draft");
  await page
    .getByRole("button", { name: "Save Page Transcript", exact: true })
    .click();
  await expect(page.locator(".save-help")).toHaveText(
    "Page changed in another tab.",
  );
  await expect(address(page)).toContainText("Unsaved by: Test reviewer");
  await expect(address(page).locator(".value")).toHaveText("Keep this draft");
  expect(api.saves).toBe(0);
});

// Checks that reviewing all fields preserves an existing correction
// and saving stores a review for every field on the current page.
test("Review all preserves correction and saves all fields", async ({
  page,
  api,
}) => {
  await page
    .getByRole("combobox", { name: "Reviewer name", exact: true })
    .selectOption("Test reviewer");
  await edit(page, "Preserve this correction");
  await page
    .getByRole("button", { name: "Reviewed all fields on page", exact: true })
    .click();
  await expect(page.locator(".review-progress")).toHaveText("100% reviewed");
  await expect(address(page).locator(".value")).toHaveText(
    "Preserve this correction",
  );
  await page
    .getByRole("button", { name: "Save Page Transcript", exact: true })
    .click();
  await expect(
    page.locator(".field-status").filter({ hasText: "Reviewed by:" }),
  ).toHaveCount(demo.pages[0].fields.length);
  expect(Object.keys(api.reviews[demo.pages[0].id])).toHaveLength(
    demo.pages[0].fields.length,
  );
});

// Checks that a failed survey load displays an error and Try again
// restores the screen once the mock API succeeds.
test("Try again recovers from a failed survey request", async ({
  page,
  api,
}) => {
  api.failLoad = true;
  await page.reload();
  await expect(page.getByRole("alert")).toContainText(
    "Test survey unavailable",
  );
  api.failLoad = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(address(page)).toBeVisible();
});

// Checks that adding a reviewer makes their name the selected reviewer.
test("Add reviewer makes the new reviewer selectable", async ({ page }) => {
  await page.getByRole("button", { name: "Add reviewer", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New reviewer name" })
    .fill("New test reviewer");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Reviewer name", exact: true }),
  ).toHaveValue("New test reviewer");
});

// Tests pending reviews before page navigation.
// Uses the mocked API: no real database writes.
const leaveDialog = (page: Page) =>
  page.getByRole("dialog", {
    name: "Save your reviews before leaving?",
  });

test.describe("Unsaved navigation", () => {
  // Checks that Stay here and Escape dismiss the navigation warning
  // while retaining the unsaved correction without saving it.
  test("Stay here and Escape retain the unsaved review", async ({
    page,
    api,
  }) => {
    await page
      .getByLabel("Reviewer name", { exact: true })
      .selectOption("Test reviewer");

    await edit(page, "Pending address");
    await page.getByLabel("Next page", { exact: true }).click();

    await expect(leaveDialog(page)).toBeVisible();

    await leaveDialog(page).getByRole("button", { name: "Stay here" }).click();

    await expect(leaveDialog(page)).not.toBeVisible();
    await expect(address(page)).toContainText("Pending address");
    await expect(address(page)).toContainText("Unsaved by:");
    expect(api.saves).toBe(0);

    // Escape should also close the warning without losing changes.
    await page.getByLabel("Next page", { exact: true }).click();
    await expect(leaveDialog(page)).toBeVisible();
    await page.keyboard.press("Escape");

    await expect(leaveDialog(page)).not.toBeVisible();
    await expect(address(page)).toContainText("Pending address");
  });

  // Checks that Save and continue saves the correction and opens the next
  // page, then shows the saved correction when the reviewer returns.

  test("Save and continue saves before switching pages", async ({
    page,
    api,
  }) => {
    await page
      .getByLabel("Reviewer name", { exact: true })
      .selectOption("Test reviewer");

    await edit(page, "Saved before leaving");
    await page.getByLabel("Next page", { exact: true }).click();

    await leaveDialog(page)
      .getByRole("button", { name: "Save and continue" })
      .click();

    await expect(leaveDialog(page)).not.toBeVisible();
    await expect(page.locator(".page-heading h2")).toContainText(
      demo.pages[1].id,
    );

    expect(api.saves).toBe(1);
    expect(api.reviews[demo.pages[0].id].address.value).toBe(
      "Saved before leaving",
    );

    // Returning to the page should show the saved correction.
    await page.getByLabel("Previous page", { exact: true }).click();

    await expect(address(page).locator(".value")).toHaveText(
      "Saved before leaving",
    );
    await expect(address(page)).toContainText("Reviewed by:");
  });

  // Checks that discarding a newer unsaved correction restores the earlier
  // saved correction and does not create an additional save.
  test("Discard restores the previous saved correction", async ({
    page,
    api,
  }) => {
    await page
      .getByLabel("Reviewer name", { exact: true })
      .selectOption("Test reviewer");

    // Save a correction first.
    await edit(page, "Saved address");
    await page
      .getByRole("button", {
        name: "Save Page Transcript",
        exact: true,
      })
      .click();

    await expect(address(page)).toContainText("Reviewed by:");

    // Make another correction without saving it.
    await edit(page, "Discard this change");
    await page.getByLabel("Next page", { exact: true }).click();

    await leaveDialog(page)
      .getByRole("button", {
        name: "Discard reviews and continue",
      })
      .click();

    await expect(page.locator(".page-heading h2")).toContainText(
      demo.pages[1].id,
    );

    await page.getByLabel("Previous page", { exact: true }).click();

    // Discard must preserve the earlier saved correction.
    await expect(address(page).locator(".value")).toHaveText("Saved address");
    await expect(address(page)).toContainText("Reviewed by:");
    expect(api.saves).toBe(1);
  });

  // Checks that a failed Save and continue keeps the warning and current
  // page open, displays the error, and preserves the unsaved correction.
  test("Failed save keeps the current page and unsaved review", async ({
    page,
    api,
  }) => {
    api.failSave = true;

    await page
      .getByLabel("Reviewer name", { exact: true })
      .selectOption("Test reviewer");

    await edit(page, "Keep this draft");
    await page.getByLabel("Next page", { exact: true }).click();

    await leaveDialog(page)
      .getByRole("button", { name: "Save and continue" })
      .click();

    await expect(leaveDialog(page)).toBeVisible();
    await expect(leaveDialog(page).getByRole("status")).toContainText(
      "Page changed",
    );

    await expect(page.locator(".page-heading h2")).toContainText(
      demo.pages[0].id,
    );

    await leaveDialog(page).getByRole("button", { name: "Stay here" }).click();

    await expect(address(page).locator(".value")).toHaveText("Keep this draft");
    await expect(address(page)).toContainText("Unsaved by:");
    expect(api.saves).toBe(0);
  });

  // Checks that leaving the website with an unsaved review triggers the
  // browser's native beforeunload warning; the test accepts that warning.
  test("Leaving the website warns about unsaved reviews", async ({ page }) => {
    await page
      .getByLabel("Reviewer name", { exact: true })
      .selectOption("Test reviewer");

    await edit(page, "Unsaved departure");

    // Register the listener before navigating away.
    const dialogPromise = page.waitForEvent("dialog");
    const navigationPromise = page.goto("about:blank");

    const dialog = await dialogPromise;
    const dialogType = dialog.type();

    await dialog.accept();
    await navigationPromise;

    expect(dialogType).toBe("beforeunload");
  });
});
