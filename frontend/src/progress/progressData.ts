import type { Survey } from "../review-screen/model";
import type { SavedReviews } from "../export/exportData";
export type PageStatus =
  | "Awaiting transcription"
  | "Ready to review"
  | "Reviewed";
export type ProgressPage = {
  id: string;
  label: string;
  category: string;
  status: PageStatus;
  flagCount: number;
  surveyId?: string;
  reviewPageId?: string;
};
export type Bundle = { id: string; pages: ProgressPage[] };

// A page is complete only when every field has a persisted review, including blanks.
export function bundleFromSurvey(
  survey: Survey,
  reviews: SavedReviews,
  bundleId: string,
): Bundle {
  const categories = { main: "Main page", notes: "Notes", coded: "Coded" };
  return {
    id: bundleId,
    pages: survey.pages.map((page, index) => ({
      id: page.id,
      label: `Pg ${index + 1}`,
      category: categories[page.type],
      surveyId: survey.id,
      reviewPageId: page.id,
      // Count unresolved fields, not individual flags; saved reviews resolve the count.
      flagCount: new Set(
        page.flags
          .filter((flag) => !reviews[page.id]?.[flag.fieldId]?.savedAt)
          .map((flag) => flag.fieldId),
      ).size,
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
// Ready excludes pages without extracted fields and fully reviewed pages.
export function counts(pages: ProgressPage[]) {
  return {
    total: pages.length,
    reviewed: pages.filter((p) => p.status === "Reviewed").length,
    ready: pages.filter((p) => p.status === "Ready to review").length,
  };
}
