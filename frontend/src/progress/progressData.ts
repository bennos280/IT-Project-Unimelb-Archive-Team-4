import type { Survey } from "../review-screen/model";
type SavedReviews = Record<
  string,
  Record<string, { value: string | null; savedAt?: string }>
>;
// Covers both processing stages and review states shown in the page list.
export type PageStatus =
  | "Awaiting transcription"
  | "Ready to review"
  | "Reviewed"
  | "Not in a survey"
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
  surveyId?: string | null;
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
  const categories: Record<string, string> = {
    main: "Main page",
    notes: "Notes",
    coded: "Coded",
    other: "Other",
  };
  return {
    id: bundleId,
    pages: survey.pages.map((page, index) => ({
      id: page.id,
      label: `Pg ${index + 1}`,
      category: Object.hasOwn(categories, page.type)
        ? categories[page.type]
        : page.type,
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
// Ready excludes pages without extracted fields and fully reviewed pages. Records: how many the pages make up.
export function counts(pages: ProgressPage[]) {
  const reviewable = pages.filter((page) => page.surveyId != null);

  return {
    total: pages.length,
    reviewable: reviewable.length,
    unassigned: pages.filter((page) => page.status === "Not in a survey")
      .length,
    reviewed: reviewable.filter((page) => page.status === "Reviewed").length,
    ready: reviewable.filter((page) => page.status === "Ready to review")
      .length,
    records: new Set(reviewable.map((page) => page.surveyId)).size,
  };
}
// A record's statuses, least far along first; a record is as far along as its least far page.
export const recordStatuses: PageStatus[] = ["Awaiting transcription", "Ready to review", "Reviewed"];
// An item's records in scan order, each with its pages, its flags, how far along it is, and the page to open: its first that
// far along.
export function records(pages: ProgressPage[]) {
  const found = new Map<string, ProgressPage[]>();
  for (const page of pages) if (page.surveyId) found.set(page.surveyId, [...(found.get(page.surveyId) ?? []), page]);
  return [...found].map(([id, pages]) => {
    const status = recordStatuses.find((s) => pages.some((page) => page.status === s)) ?? "Reviewed";
    return { id, pages, status, page: pages.find((page) => page.status === status) ?? pages[0],
      flagCount: pages.reduce((n, page) => n + page.flagCount, 0) };
  });
}
// The page counts of one item, or of a whole series.
export type Counts = ReturnType<typeof counts>;
