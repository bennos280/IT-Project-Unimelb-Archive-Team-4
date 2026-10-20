import type { Request } from "@playwright/test";

// A stand-in for the server's item endpoints, so the specs that show the dashboard serve its items without a backend.
// GET /api/collections/<id>/items searches, filters and pages the series' items; GET .../items/<name or bundle> gives one with its pages.
export type MockPage = {
  id: string; label: string; category: string; status: string; flagCount: number;
  surveyId?: string | null; reviewPageId?: string; model?: string | null;
};
export type MockItem = {
  bundle: string; name: string; pdf?: string;
  loaded?: boolean; job?: unknown; pages?: MockPage[];
};
type Reply = { status?: number; json: unknown };

// The page counts the server gives for a set of pages.
export function tally(pages: MockPage[]) {
  const reviewable = pages.filter((page) => page.surveyId != null);
  return {
    total: pages.length,
    reviewable: reviewable.length,
    unassigned: pages.filter((page) => page.status === "Not in a survey").length,
    reviewed: reviewable.filter((page) => page.status === "Reviewed").length,
    ready: reviewable.filter((page) => page.status === "Ready to review").length,
    records: new Set(reviewable.map((page) => page.surveyId)).size,
  };
}

const row = (item: MockItem) => ({
  bundle: item.bundle, name: item.name, pdf: item.pdf ?? `${item.name}.pdf`,
  loaded: item.loaded ?? true, job: item.job ?? null,
});

// Whether an item matches a status as the server decides it.
function hasStatus(item: MockItem, status: string) {
  const counts = tally(item.pages ?? []);
  const job = item.job as { status?: string } | null | undefined;
  const loaded = item.loaded ?? true;
  if (status === "All") return true;
  if (status === "Awaiting transcription") return !loaded || (item.pages ?? []).some((page) => page.status === status);
  if (status === "Transcription in progress") return !loaded && job?.status === "running";
  if (status === "Reviewed") return counts.reviewable > 0 && counts.reviewed === counts.reviewable;
  return (item.pages ?? []).some((page) => page.status === status);
}

// The reply to a request for the series' items, or null when it is for something else.
// The items may be a function, called afresh for every request.
export function serveItems(items: MockItem[] | (() => MockItem[]), request: Request): Reply | null {
  const url = new URL(request.url());
  const found = url.pathname.match(/^\/api\/collections\/\d+\/items(?:\/([^/]+))?$/);
  if (!found || request.method() !== "GET") return null;
  const all = [...(typeof items === "function" ? items() : items)].sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { numeric: true }));
  if (found[1]) {
    const name = decodeURIComponent(found[1]);
    const one = all.find((item) => item.name === name || item.bundle === name);
    return one ? { json: { ...row(one), pages: one.pages ?? [] } } : { status: 404, json: { detail: "No such item." } };
  }
  const search = (url.searchParams.get("search") ?? "").trim().toLowerCase();
  const status = url.searchParams.get("status") ?? "All";
  const size = Number(url.searchParams.get("size")) || 9;
  const matching = all.filter((item) =>
    [item.name, item.bundle].join(" ").toLowerCase().includes(search) &&
    hasStatus(item, status));
  const page = Math.min(Math.max(0, Number(url.searchParams.get("page")) || 0), Math.max(0, Math.ceil(matching.length / size) - 1));
  return {
    json: {
      items: matching.slice(page * size, (page + 1) * size).map((item) => ({ ...row(item), counts: tally(item.pages ?? []) })),
      page, total: matching.length, all: all.length, totals: tally(all.flatMap((item) => item.pages ?? [])),
      most: { pages: Math.max(0, ...all.map((item) => (item.pages ?? []).length)),
        records: Math.max(0, ...all.map((item) => tally(item.pages ?? []).records)) },
    },
  };
}
