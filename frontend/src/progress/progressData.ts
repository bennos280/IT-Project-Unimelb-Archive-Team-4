import type { Survey } from "../review-screen/model";
type SavedReviews = Record<string, Record<string, { value: string | null; savedAt?: string }>>;
// Covers both processing stages and review states shown in the page list.
export type PageStatus =
  | "Awaiting transcription"
  | "Ready to review"
  | "Reviewed"
  | "Transcribed — not grouped"
  | "Needs identification"
  | "Not required";
// One dashboard row. Partial processing results may not have a survey/review target yet.
export type ProgressPage = {
  id: string;
  label: string;
  category: string;
  status: PageStatus;
  flagCount: number;
  model?: string | null;
  // Raw transcript data can be available before grouping and database loading finish.
  savedData?: Record<string, unknown>;
  surveyId?: string;
  reviewPageId?: string;
};
export type Bundle = { id: string; name?: string; pages: ProgressPage[] };

// Converts a survey and its saved reviews into dashboard rows without changing either input.
// A page is complete only when every field has a persisted review, including blanks.
export function bundleFromSurvey(
  survey: Survey,
  reviews: SavedReviews,
  bundleId: string,
): Bundle {
  const categories: Record<string, string> = { main: "Main page", notes: "Notes", coded: "Coded", other: "Other" };
  return {
    id: bundleId,
    pages: survey.pages.map((page, index) => ({
      id: page.id,
      label: `Pg ${index + 1}`,
      category: Object.hasOwn(categories, page.type) ? categories[page.type] : page.type,
      surveyId: survey.id,
      reviewPageId: page.id,
      // Count unresolved fields, not individual flags; saved reviews resolve the count.
      flagCount: new Set(
        page.flags
          .filter((flag) => !reviews[page.id]?.[flag.fieldId]?.savedAt)
          .map((flag) => flag.fieldId),
      ).size,
      // Check for no fields first: every() would otherwise treat an empty page as reviewed.
      status:
        page.fields.length === 0
          ? "Awaiting transcription"
          : page.fields.every((field) =>
                Boolean(reviews[page.id]?.[field.id]?.savedAt),
              )
            ? "Reviewed"
            : "Ready to review",
    })),
  };
}
// Total includes every status; only the two review states contribute to the other counters.
// Ready excludes pages without extracted fields and fully reviewed pages.
export function counts(pages: ProgressPage[]) {
  return {
    total: pages.length,
    reviewed: pages.filter((p) => p.status === "Reviewed").length,
    ready: pages.filter((p) => p.status === "Ready to review").length,
  };
}
