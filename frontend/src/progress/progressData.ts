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
// A record of an item, or the item itself at the root (depth 0, its own pages those in no record): its own pages, the records
// inside it, every page under it, how far along those are, the page to open (its first that far along) and their flags.
export type RecordNode = {
  id: string; parent: string | null; depth: number; pages: ProgressPage[]; children: RecordNode[]; all: ProgressPage[];
  status: PageStatus; page: ProgressPage | undefined; flagCount: number;
};
// An item's records as a tree, from its pages and the records the server gives (each with the one it sits in; without them,
// every record its pages name is at the top), each list in scan order; a record with no pages under it (one a move emptied)
// has nothing to show, so it's left out.
export function recordTree(pages: ProgressPage[], records: { id: string; parent: string | null }[] = []): RecordNode {
  const node = (id: string, parent: string | null): RecordNode =>
    ({ id, parent, depth: 0, pages: [], children: [], all: [], status: "Reviewed", page: undefined, flagCount: 0 });
  const root = node("", null);
  const nodes = new Map(records.map((r) => [r.id, node(r.id, r.parent)]));
  for (const page of pages) if (page.surveyId && !nodes.has(page.surveyId)) nodes.set(page.surveyId, node(page.surveyId, null));
  for (const page of pages) (page.surveyId ? nodes.get(page.surveyId)! : root).pages.push(page);
  for (const n of nodes.values()) ((n.parent && nodes.get(n.parent)) || root).children.push(n);
  const order = new Map(pages.map((page, i) => [page, i]));
  const first = (n: RecordNode) => (n.all.length ? order.get(n.all[0])! : Infinity);
  const fill = (n: RecordNode, depth: number) => {
    n.depth = depth;
    n.children.forEach((child) => fill(child, depth + 1));
    n.children = n.children.filter((child) => child.all.length).sort((a, b) => first(a) - first(b));
    n.all = [...n.pages, ...n.children.flatMap((child) => child.all)].sort((a, b) => order.get(a)! - order.get(b)!);
    n.status = recordStatuses.find((s) => n.all.some((page) => page.status === s)) ?? "Reviewed";
    n.page = n.all.find((page) => page.status === n.status && page.surveyId) ?? n.all.find((page) => page.surveyId);
    n.flagCount = n.all.reduce((sum, page) => sum + page.flagCount, 0);
  };
  fill(root, 0);
  return root;
}
// Where opening a record leads: down through any record holding just one other and no pages of its own, so a level with only
// one thing in it is skipped.
export function descend(n: RecordNode): RecordNode {
  while (n.children.length === 1 && !n.pages.length) n = n.children[0];
  return n;
}
// The page counts of one item, or of a whole series.
export type Counts = ReturnType<typeof counts>;
