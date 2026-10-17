import { afterEach, expect, it, vi } from "vitest";
import { loadSurveyExport } from "../../../frontend/src/export/exportService";

afterEach(() => vi.unstubAllGlobals());

it.each(["Correction", "", "/", "[?]", null])(
  "returns the backend export unchanged for value %j",
  async (value) => {
    const payload = {
      surveys: [
        {
          surveyId: "survey /1",
          pages: [
            {
              fields: [{ id: "address", value }],
            },
          ],
        },
      ],
    };
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(payload)));
    vi.stubGlobal("fetch", fetch);
    expect(await loadSurveyExport(" survey /1 ")).toEqual(payload);
    expect(fetch).toHaveBeenCalledExactlyOnceWith(
      "/api/export?survey_id=survey%20%2F1",
      {},
    );
  },
);

it("reports backend export errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: "Survey not found" }), {
          status: 404,
        }),
      ),
  );
  await expect(loadSurveyExport("missing")).rejects.toThrow("Survey not found");
});

it("rejects blank survey IDs before requesting data", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  await expect(loadSurveyExport(" ")).rejects.toThrow("Enter a survey ID");
  expect(fetch).not.toHaveBeenCalled();
});
