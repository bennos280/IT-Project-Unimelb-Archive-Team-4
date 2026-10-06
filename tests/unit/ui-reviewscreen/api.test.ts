// Tests the real US7 API adapter using mocked fetch responses.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import {
  getSurvey,
  getReviewers,
  getReviews,
  createReviewer,
  saveReviews,
} from "../../../frontend/src/review-screen/api";
import type { Survey } from "../../../frontend/src/review-screen/model";

// Loads a fresh copy of the demo survey so changes in one test
// do not affect the data used by another test.
const demo = (): Survey =>
  JSON.parse(
    readFileSync(
      new URL("../../../frontend/public/us7-demo/survey.json", import.meta.url),
      "utf8",
    ),
  );
const fetchMock = vi.fn<typeof fetch>();

// Creates a JSON response with a successful or error HTTP status.
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });

// Resets previous mock calls and replaces fetch before every test.
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

// Restores the original globals after each test.
afterEach(() => vi.unstubAllGlobals());

describe("getSurvey", () => {
  // Checks the requested URL and abort signal, and confirms that valid
  // main, notes, and coded page data is returned unchanged.
  it("requests the selected survey and preserves main/notes/coded data", async () => {
    const source = demo();
    fetchMock.mockResolvedValueOnce(json(source));
    const signal = new AbortController().signal;

    expect(await getSurvey(source.id, signal)).toEqual(source);
    expect(fetchMock).toHaveBeenCalledWith(`/api/survey/${source.id}`, {
      signal,
    });
  });

  // Checks that missing flags become an empty list and an unavailable
  // image path gets a placeholder without changing extracted values.
  it("fills missing flags and unavailable image paths without changing field values", async () => {
    const source = demo();
    const response = {
      ...source,
      pages: source.pages.map(({ flags: _flags, ...page }) => ({
        ...page,
        imageUrl: "local-scan.jpg",
      })),
    };

    fetchMock.mockResolvedValueOnce(json(response));
    const loaded = await getSurvey(source.id);

    loaded.pages.forEach((page, index) => {
      expect(page.flags).toEqual([]);
      expect(page.imageUrl).toBe("/image-not-connected");
      expect(page.fields).toEqual(source.pages[index].fields);
    });
  });

  // Checks that data belonging to a different survey is rejected.
  it("rejects data for a different survey", async () => {
    fetchMock.mockResolvedValueOnce(json(demo()));

    await expect(getSurvey("another-survey")).rejects.toThrow(/another survey/);
  });

  // Checks that two pages cannot share the same ID in a survey response.
  it("rejects duplicate page IDs", async () => {
    const source = demo();
    source.pages[1].id = source.pages[0].id;
    fetchMock.mockResolvedValueOnce(json(source));

    await expect(getSurvey(source.id)).rejects.toThrow(/duplicate survey page/);
  });

  // Checks that the backend's not-found explanation reaches the caller.
  it("shows backend not-found errors", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "Survey not found" }, 404));

    await expect(getSurvey("missing")).rejects.toThrow("Survey not found");
  });

  // Checks that a server error still produces a useful message
  // when its response body is not JSON.
  it("shows a useful message for non-JSON server errors", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("Internal Server Error", { status: 500 }),
    );

    await expect(getSurvey("216417")).rejects.toThrow("Request failed (500).");
  });

  // Checks that an AbortError reaches the caller.
  // This simulates cancellation rather than cancelling a live request.
  it("propagates cancellation", async () => {
    fetchMock.mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));

    await expect(getSurvey("216417")).rejects.toMatchObject({
      name: "AbortError",
    });
  });
});

// Checks that the backend's reviewer_id becomes the frontend's id.
it("maps reviewer_id into the frontend id", async () => {
  fetchMock.mockResolvedValueOnce(json([{ reviewer_id: 2, name: "Lachlan" }]));

  expect(await getReviewers()).toEqual([{ id: 2, name: "Lachlan" }]);
});

// Checks that surrounding whitespace is removed and an existing
// reviewer is reused without making a second request.
it("reuses an existing reviewer without creating another", async () => {
  fetchMock.mockResolvedValueOnce(json([{ reviewer_id: 2, name: "Lachlan" }]));
  expect(await createReviewer(" Lachlan ")).toEqual({ id: 2, name: "Lachlan" });
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

// Checks that an empty reviewer name is rejected before calling the API.
it("rejects an empty reviewer name without a request", async () => {
  await expect(createReviewer("  ")).rejects.toThrow("Enter a reviewer name.");

  expect(fetchMock).not.toHaveBeenCalled();
});

// Checks that saved reviews and page revisions are returned unchanged.
it("loads saved reviews and revisions unchanged", async () => {
  const stored = {
    reviews: { p1: {} },
    revisions: { p1: 3 },
  };
  fetchMock.mockResolvedValueOnce(json(stored));

  expect(await getReviews("216417")).toEqual(stored);
});

describe("saveReviews", () => {
  // Supplies a survey, a registered reviewer, and a successful save
  // response for the tests below.
  function arrange() {
    const source = demo();

    fetchMock.mockImplementation(async (url, options) => {
      if (String(url).includes("/survey/")) return json(source);
      if (url === "/api/reviewers")
        return json([{ reviewer_id: 1, name: "Test reviewer" }]);
      if (options?.method === "POST")
        return json({ revision: 3, savedAt: "2026-10-05T00:00:00Z" });
      throw new Error(`Unexpected request ${url}`);
    });

    return source;
  }

  // Runs four cases to check that corrected text, "/", "[?]", and null
  // are sent unchanged, with the original value, reviewer details,
  // and the proposed next page revision.
  it.each(["Corrected address", "/", "[?]", null])(
    "sends the selected value %j without changing its meaning",
    async (value) => {
      const source = arrange();
      const page = source.pages[0];

      await saveReviews(source.id, page.id, 2, {
        address: { value, reviewerId: 1 },
      });

      const post = fetchMock.mock.calls.find(
        ([, options]) => options?.method === "POST",
      );
      const body = JSON.parse(post![1]!.body as string);

      expect(body).toEqual({
        reviews: {
          [page.id]: {
            address: {
              value,
              original: page.fields.find((f) => f.id === "address")!.value,
              reviewer: "Test reviewer",
              reviewerId: 1,
              savedAt: "",
            },
          },
        },
        revisions: { [page.id]: 3 },
      });
    },
  );

  // Checks that saving an empty set of changes is rejected
  // without making any API requests.
  it("does not send an empty save", async () => {
    await expect(saveReviews("216417", "p1", 0, {})).rejects.toThrow(
      /no unsaved reviews/i,
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  // Checks that a field missing from the selected page is rejected
  // before a save request is posted.
  it("does not submit an unknown field", async () => {
    const source = arrange();

    await expect(
      saveReviews(source.id, source.pages[0].id, 0, {
        missing: { value: "x", reviewerId: 1 },
      }),
    ).rejects.toThrow(/not found on this page/);

    expect(
      fetchMock.mock.calls.some(([, options]) => options?.method === "POST"),
    ).toBe(false);
  });

  // Checks that an unregistered reviewer is rejected
  // before a save request is posted.
  it("does not submit an unknown reviewer", async () => {
    const source = arrange();

    await expect(
      saveReviews(source.id, source.pages[0].id, 0, {
        address: { value: "x", reviewerId: 99 },
      }),
    ).rejects.toThrow("Unknown reviewer.");

    expect(
      fetchMock.mock.calls.some(([, options]) => options?.method === "POST"),
    ).toBe(false);
  });
});
