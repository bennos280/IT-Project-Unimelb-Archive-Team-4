// Tests export values through the real US8 adapter with controlled HTTP responses.
import { afterEach, expect, it, vi } from "vitest";
import { loadSurveyExport } from "../../../frontend/src/export/exportService";
import { buildSurveyExport } from "../../../frontend/src/export/exportData";
import type { Survey } from "../../../frontend/src/review-screen/model";
const survey: Survey = {
  id: "another-survey",
  title: "Survey",
  pages: [
    {
      id: "page1",
      type: "main",
      imageUrl: "/scan.jpg",
      flags: [],
      fields: [
        {
          id: "address",
          label: "Address",
          group: "Address",
          value: "Original",
        },
        {
          id: "residents.0.relationship",
          label: "Relationship",
          group: "Resident 1",
          value: "Head",
        },
      ],
    },
    {
      id: "page2",
      type: "notes",
      imageUrl: "/notes.jpg",
      flags: [],
      fields: [{ id: "text", label: "Notes", group: "Notes", value: null }],
    },
  ],
};
afterEach(() => vi.unstubAllGlobals());
function responses(reviews: object, fail = false) {
  const fetch = vi.fn(async (url: RequestInfo | URL) => {
    if (String(url).startsWith("/api/survey/"))
      return new Response(JSON.stringify(survey));
    if (fail)
      return new Response(JSON.stringify({ detail: "Reviews unavailable" }), {
        status: 500,
      });
    return new Response(JSON.stringify({ reviews, revisions: { page1: 2 } }));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
// Empty and transcription marker values must survive JSON serialization unchanged.
it.each(["Correction", "", "/", "[?]", null])(
  "exports saved value %j from US8",
  async (value) => {
    const fetch = responses({
      page1: { address: { value, savedAt: "2026-10-07T00:00:00Z" } },
    });
    const result = JSON.parse(
      JSON.stringify(await loadSurveyExport(" another-survey ")),
    );
    expect(result.surveys[0].pages[0].fields[0].value).toBe(value);
    expect(result.surveys[0].pages[0].fields[1].value).toBe("Head");
    expect(result.surveys[0].status).toBe("ToBeReviewed");
    expect(fetch).toHaveBeenCalledWith("/api/reviews/another-survey", {});
  },
);
it("retains source IDs, notes and saved resident corrections", async () => {
  responses({
    page1: { "residents.0.relationship": { value: "Wife", savedAt: "now" } },
  });
  const result = await loadSurveyExport(survey.id);
  expect(result.surveys[0].pages[0]).toMatchObject({
    pageId: "page1",
    sourceImage: "/scan.jpg",
  });
  expect(result.surveys[0].pages[0].fields[1].value).toBe("Wife");
  expect(result.surveys[0].pages[1].fields[0].value).toBeNull();
});
it("does not substitute an unsaved draft for an extracted value", () => {
  expect(
    buildSurveyExport(survey, { page1: { address: { value: "Draft" } } })
      .pages[0].fields[0].value,
  ).toBe("Original");
});
it("rejects export when saved reviews cannot be loaded", async () => {
  responses({}, true);
  await expect(loadSurveyExport(survey.id)).rejects.toThrow(
    "Reviews unavailable",
  );
});
it("rejects blank survey IDs before requesting data", async () => {
  const fetch = responses({});
  await expect(loadSurveyExport(" ")).rejects.toThrow("Enter a survey ID");
  expect(fetch).not.toHaveBeenCalled();
});
