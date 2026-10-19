// Real browser interactions with an isolated, per-test API fixture.
import { test as base, expect, type Locator, type Page } from "@playwright/test";
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
  recordName: "survey", grouped: true,
  pages: [
    {
      id: "test-bundle/p0",
      type: "main",
      imageUrl: "/test-images/main.jpg",
      fields: [
        {
          id: "address",
          label: "Address",
          group: "Address",
          value: "10 Sample Street",
        },
        {
          id: "municipality",
          label: "Municipality",
          group: "Address",
          value: null,
        },
      ],
      flags: [
        {
          id: "address-uncertain",
          fieldId: "address",
          kind: "uncertain",
          reason: "The handwriting needs checking.",
        },
        {
          id: "address-invalid",
          fieldId: "address",
          kind: "invalid",
          reason: "Should look like 12 Smith St",
        },
      ],
    },
    {
      id: "test-bundle/p1",
      type: "notes",
      imageUrl: "/test-images/notes.jpg",
      fields: [
        {
          id: "text",
          label: "Notes",
          group: "Notes",
          value: "Interview notes.",
        },
      ],
      flags: [],
    },
    {
      id: "test-bundle/p2",
      type: "coded",
      imageUrl: "/test-images/coded.jpg",
      fields: [
        {
          id: "number_of_dwelling",
          label: "Number of dwelling",
          group: "Left column",
          value: "12",
        },
      ],
      flags: [],
    },
  ],
};

// Creates a fresh mock API for each test so reviews
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
    // Serve a predictable image so viewer tests do not depend on demo scan files.
    await page.route("**/test-images/*.jpg", (route) =>
      route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><rect width="1200" height="800" fill="white"/></svg>',
      }),
    );
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const reply = (body: unknown, status = 200) =>
        route.fulfill({ status, json: body });
      if (path.startsWith("/api/survey/"))
        return state.failLoad
          ? reply({ detail: "Test survey unavailable" }, 500)
          : reply(demo);
      if (path === "/api/reviewers") return reply([{ id: 1, name: "Ben" }]);
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

// Every field row, identified by its edit button.
const fieldRows = (page: Page) =>
  page.getByRole("row").filter({
    has: page.getByRole("button", { name: /^Edit / }),
  });

// Finds the Address row using its edit button.
const address = (page: Page) =>
  page.getByRole("row").filter({
    has: page.getByRole("button", { name: "Edit Address", exact: true }),
  });

// The page heading carries the current page ID.
const pageHeading = (page: Page) => page.locator("[data-page-id]");

// The scan image for the current page.
const scanImage = (page: Page) => page.getByRole("img", { name: /^Original / });

// The scrollable scan viewport.
const viewport = (page: Page) => page.getByLabel(/^Page scan\./);

// The zoom percentage between the zoom buttons.
const zoomLevel = (page: Page) =>
  page.getByRole("status").filter({ hasText: /^\d+%$/ });

// The field value shown in a row's value cell.
const valueOf = (row: Locator) => row.getByRole("cell").nth(1);

// Opens Address, enters a value, and applies an unsaved review.
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
    await expect(pageHeading(page)).toHaveAttribute("data-page-id", source.id);
    await expect(fieldRows(page)).toHaveCount(source.fields.length);
    await expect(scanImage(page)).toHaveAttribute(
      "src",
      source.imageUrl,
    );
    await expect
      .poll(() =>
        scanImage(page)
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
  await expect(pageHeading(page)).toHaveAttribute("data-page-id",
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
  await expect(fieldRows(page)).toHaveCount(
    demo.pages[0].fields.length,
  );
});

// Checks that the flag filter shows only flagged fields and expanding
// the first flag displays its explanation from the fixture.
test("Flag filter and disclosure show the reason", async ({ page }) => {
  await page
    .getByRole("combobox", { name: "Filter fields" })
    .selectOption("flagged");
  await expect(fieldRows(page)).toHaveCount(
    new Set(demo.pages[0].flags.map((f) => f.fieldId)).size,
  );
  const row = address(page);
  await row.getByRole("button", { name: "Uncertain values" }).click();
  await expect(row.getByText(demo.pages[0].flags[0].reason)).toHaveText(
    demo.pages[0].flags[0].reason,
  );
});

// A value that breaks its field's rule is flagged as that, and can be filtered to.
test("A field breaking its rule is flagged with why, and filtered to", async ({ page }) => {
  await page
    .getByRole("combobox", { name: "Filter fields" })
    .selectOption("invalid");
  await expect(fieldRows(page)).toHaveCount(1);
  const row = address(page);
  await row.getByRole("button", { name: "Breaks its field's rules" }).click();
  await expect(row.getByText("Should look like 12 Smith St")).toBeVisible();
});

// Checks the zoom buttons change the displayed percentage and Fit to Page
// fits the complete scan inside the viewer without significant overflow.
test("Zoom and Fit to Page change the image scale", async ({ page }) => {
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(zoomLevel(page)).toHaveText("125%");
  await page.getByRole("button", { name: "Zoom out", exact: true }).click();
  await expect(zoomLevel(page)).toHaveText("100%");
  await expect(page.getByRole("button", { name: "Fit to Page" })).toBeEnabled();
  await page.getByRole("button", { name: "Fit to Page" }).click();
  await expect
    .poll(() =>
      viewport(page)
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
  await address(page)
    .getByRole("button", { name: "Locate Address: Address in image" })
    .click();
  await expect(page.getByLabel(/^Highlighted source/)).toHaveAttribute(
    "aria-label",
    "Highlighted source: Address",
  );
  await expect(zoomLevel(page)).toHaveText("200%");
});

// Checks that a field with no mapped scan area shows the whole card and says why.
test("Clicking an annotation shows the whole card and a note", async ({ page }) => {
  const withAnnotation = structuredClone(demo);
  withAnnotation.pages[0].fields.push({
    id: "annotations.0",
    label: "Annotation",
    group: "Annotations",
    value: "Red star",
    location: "top-left, right of dwelling number",
  });
  await page.route("**/api/survey/**", (route) =>
    route.fulfill({ json: withAnnotation }),
  );
  await page.reload();
  const fit = page.getByRole("button", { name: "Fit to Page" });
  await expect(fit).toBeEnabled();
  await fit.click();
  const wholeCard = await zoomLevel(page).textContent();
  const locateAddress = address(page).getByRole("button", {
    name: "Locate Address: Address in image",
  });
  await locateAddress.click();
  await expect(zoomLevel(page)).toHaveText("200%");
  const annotation = page.getByRole("row").filter({
    has: page.getByRole("button", { name: "Edit Annotation", exact: true }),
  });
  await expect(annotation).toContainText("top-left, right of dwelling number");
  await annotation
    .getByRole("button", { name: "Locate Annotations: Annotation in image" })
    .click();
  const note = page
    .getByRole("status")
    .filter({ hasText: "Annotation: top-left, right of dwelling number" });
  await expect(note).toBeVisible();
  await expect(zoomLevel(page)).toHaveText(wholeCard!);
  await expect(page.getByLabel(/^Highlighted source/)).toHaveCount(0);
  // Zooming by hand hides the note; a mapped field still highlights and zooms.
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(note).toHaveCount(0);
  await locateAddress.click();
  await expect(page.getByLabel(/^Highlighted source/)).toHaveAttribute(
    "aria-label",
    "Highlighted source: Address",
  );
  await expect(zoomLevel(page)).toHaveText("200%");
});

// Checks that an annotation with an area highlights it, zooms to fit it (between 100% and 200%) and still shows the note.
test("Clicking an annotation with an area highlights the area and shows the note", async ({ page }) => {
  const withArea = structuredClone(demo);
  withArea.pages[0].fields.push({
    id: "annotations.0",
    label: "Annotation",
    group: "Annotations",
    value: "Red star",
    location: "right of the kitchen heading",
    area: "kitchen_block",
    areaLabel: "Kitchen",
    sourceRegion: { x: 0.5, y: 0.5, width: 0.5, height: 0.5 },
  });
  await page.route("**/api/survey/**", (route) =>
    route.fulfill({ json: withArea }),
  );
  await page.reload();
  await expect(page.getByRole("button", { name: "Fit to Page" })).toBeEnabled();
  const annotation = page.getByRole("row").filter({
    has: page.getByRole("button", { name: "Edit Annotation", exact: true }),
  });
  await expect(annotation).toContainText("Kitchen");
  await expect(annotation).toContainText("right of the kitchen heading");
  await annotation
    .getByRole("button", { name: "Locate Annotations: Annotation in image" })
    .click();
  await expect(page.getByLabel(/^Highlighted source/)).toHaveAttribute(
    "aria-label",
    "Highlighted source: Annotation",
  );
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Annotation: right of the kitchen heading" }),
  ).toBeVisible();
  await expect
    .poll(async () => parseInt((await zoomLevel(page).textContent()) ?? "0"))
    .toBe(170);
  // Zooming by hand keeps the new zoom and keeps the highlight.
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(zoomLevel(page)).toHaveText("195%");
  await page.waitForTimeout(500);
  await expect(zoomLevel(page)).toHaveText("195%");
  await expect(page.getByLabel(/^Highlighted source/)).toHaveCount(1);
});

// Checks that an annotation with its own region (a row of the residents table) highlights that region, not its whole area.
test("Clicking an annotation with a region highlights the region", async ({ page }) => {
  const withRegion = structuredClone(demo);
  withRegion.pages[0].fields.push({
    id: "annotations.0",
    label: "Annotation",
    group: "Annotations",
    value: "Red tick",
    location: "residential pref row (red)",
    area: "residents_table",
    areaLabel: "Residents table",
    sourceRegion: { x: 0.25, y: 0.5, width: 0.5, height: 0.125 },
  });
  await page.route("**/api/survey/**", (route) =>
    route.fulfill({ json: withRegion }),
  );
  await page.reload();
  await expect(page.getByRole("button", { name: "Fit to Page" })).toBeEnabled();
  await page
    .getByRole("button", { name: "Locate Annotations: Annotation in image" })
    .click();
  const highlight = page.getByLabel(/^Highlighted source/);
  await expect(highlight).toHaveAttribute(
    "style",
    /left: 25%; top: 50%; width: 50%; height: 12\.5%/,
  );
  await expect
    .poll(async () => parseInt((await zoomLevel(page).textContent()) ?? "0"))
    .toBe(170);
  // The highlight is the band, a small part of the page image.
  const band = await highlight.boundingBox();
  const image = await page.getByRole("img", { name: /^Original/ }).boundingBox();
  expect(band!.width / image!.width).toBeCloseTo(0.5, 1);
  expect(band!.height / image!.height).toBeCloseTo(0.125, 1);
});

// Checks that a field's own sourceRegion is used instead of the shared one, and that a wide one zooms less than 200%.
test("A field's own wide region is highlighted at a lower zoom", async ({ page }) => {
  const wide = structuredClone(demo);
  wide.pages[0].fields[1].sourceRegion = { x: 0, y: 0.3, width: 0.9, height: 0.4 };
  await page.route("**/api/survey/**", (route) => route.fulfill({ json: wide }));
  await page.reload();
  await expect(page.getByRole("button", { name: "Fit to Page" })).toBeEnabled();
  await page
    .getByRole("button", { name: "Locate Address: Municipality in image" })
    .click();
  await expect(page.getByLabel(/^Highlighted source/)).toHaveAttribute(
    "aria-label",
    "Highlighted source: Municipality",
  );
  await expect(zoomLevel(page)).toHaveText("100%");
});

// Checks that cancelling the editor leaves the original value unchanged
// without saving.
test("Cancel discards draft text", async ({
  page,
  api,
}) => {
  const original = await valueOf(address(page)).innerText();
  await page.getByRole("button", { name: "Edit Address", exact: true }).click();
  await page
    .getByLabel("Reviewed value", { exact: true })
    .fill("Cancelled text");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(valueOf(address(page))).toHaveText(original);
  expect(api.saves).toBe(0);
});

// Checks that Apply creates an unsaved review, Save stores it in the mock
// API with revision 1, and refreshing reloads the saved correction.
test("Apply creates draft; Save persists and reload restores it", async ({
  page,
  api,
}) => {
  await edit(page, "10 Test Street");
  await expect(address(page)).toContainText("Unsaved by: Ben");
  expect(api.saves).toBe(0);
  await page
    .getByRole("button", { name: "Save Page Transcript", exact: true })
    .click();
  await expect(address(page)).toContainText("Reviewed by: Ben");
  expect(api.reviews[demo.pages[0].id].address.value).toBe("10 Test Street");
  expect(api.revisions[demo.pages[0].id]).toBe(1);
  await page.reload();
  await expect(valueOf(address(page))).toHaveText("10 Test Street");
  await expect(address(page)).toContainText("Reviewed by: Ben");
});

// Checks that a rejected save displays the API error and retains the
// correction as unsaved so the reviewer does not lose their work.
test("Rejected save displays reason and retains unsaved correction", async ({
  page,
  api,
}) => {
  api.failSave = true;
  await edit(page, "Keep this draft");
  await page
    .getByRole("button", { name: "Save Page Transcript", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Page changed in another tab." }),
  ).toHaveText("Page changed in another tab.");
  await expect(address(page)).toContainText("Unsaved by: Ben");
  await expect(valueOf(address(page))).toHaveText("Keep this draft");
  expect(api.saves).toBe(0);
});

// Checks that reviewing all fields preserves an existing correction
// and saving stores a review for every field on the current page.
test("Review all preserves correction and saves all fields", async ({
  page,
  api,
}) => {
  await edit(page, "Preserve this correction");
  await page
    .getByRole("button", {
      name: "Mark all fields as reviewed",
      exact: true,
    })
    .click();
  await expect(page.getByText(/^\d+% reviewed$/)).toHaveText("100% reviewed");
  await expect(valueOf(address(page))).toHaveText(
    "Preserve this correction",
  );
  await page
    .getByRole("button", { name: "Save Page Transcript", exact: true })
    .click();
  await expect(
    fieldRows(page).filter({ hasText: "Reviewed by:" }),
  ).toHaveCount(demo.pages[0].fields.length);
  expect(Object.keys(api.reviews[demo.pages[0].id])).toHaveLength(
    demo.pages[0].fields.length,
  );
});

// Checks that marking all fields reviewed leaves a field another reviewer
// already saved with their value and name.
test("Review all keeps another reviewer's saved review", async ({
  page,
  api,
}) => {
  api.reviews[demo.pages[0].id] = {
    municipality: {
      value: "Saved earlier",
      original: null,
      reviewer: "Other reviewer",
      reviewerId: 2,
      savedAt: "2026-10-04T01:00:00Z",
    },
  };
  api.revisions[demo.pages[0].id] = 1;
  await page.reload();
  const municipality = fieldRows(page).filter({
    has: page.getByRole("button", { name: "Edit Municipality", exact: true }),
  });
  await expect(municipality).toContainText("Reviewed by: Other reviewer");
  await page
    .getByRole("button", {
      name: "Mark all fields as reviewed",
      exact: true,
    })
    .click();
  await expect(municipality).toContainText("Reviewed by: Other reviewer");
  await expect(valueOf(municipality)).toHaveText("Saved earlier");
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

// Checks that the status line says who the page is saved as.
test("The status line names the person working", async ({ page }) => {
  await expect(
    page.getByText("Save page transcript saves your reviews, as Ben.", {
      exact: true,
    }),
  ).toBeVisible();
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
    await edit(page, "Saved before leaving");
    await page.getByLabel("Next page", { exact: true }).click();

    await leaveDialog(page)
      .getByRole("button", { name: "Save and continue" })
      .click();

    await expect(leaveDialog(page)).not.toBeVisible();
    await expect(pageHeading(page)).toHaveAttribute("data-page-id",
      demo.pages[1].id,
    );

    expect(api.saves).toBe(1);
    expect(api.reviews[demo.pages[0].id].address.value).toBe(
      "Saved before leaving",
    );

    // Returning to the page should show the saved correction.
    await page.getByLabel("Previous page", { exact: true }).click();

    await expect(valueOf(address(page))).toHaveText(
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

    await expect(pageHeading(page)).toHaveAttribute("data-page-id",
      demo.pages[1].id,
    );

    await page.getByLabel("Previous page", { exact: true }).click();

    // Discard must preserve the earlier saved correction.
    await expect(valueOf(address(page))).toHaveText("Saved address");
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

    await edit(page, "Keep this draft");
    await page.getByLabel("Next page", { exact: true }).click();

    await leaveDialog(page)
      .getByRole("button", { name: "Save and continue" })
      .click();

    await expect(leaveDialog(page)).toBeVisible();
    await expect(leaveDialog(page).getByRole("status")).toContainText(
      "Page changed",
    );

    await expect(pageHeading(page)).toHaveAttribute("data-page-id",
      demo.pages[0].id,
    );

    await leaveDialog(page).getByRole("button", { name: "Stay here" }).click();

    await expect(valueOf(address(page))).toHaveText("Keep this draft");
    await expect(address(page)).toContainText("Unsaved by:");
    expect(api.saves).toBe(0);
  });

  // Checks that leaving the website with an unsaved review triggers the
  // browser's native beforeunload warning; the test accepts that warning.
  test("Leaving the website warns about unsaved reviews", async ({ page }) => {
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
