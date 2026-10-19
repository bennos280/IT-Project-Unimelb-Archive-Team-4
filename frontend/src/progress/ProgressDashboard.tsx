import ExportDialog from "../export/ExportDialog";
// Bundle overview and page list
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { ArrowRight, ExternalLink, ListPlus, Search } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import SeriesHeader from "@/components/SeriesHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Progress } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableOpenArrow,
  TableRow,
  TableRowLink,
} from "@/components/ui/table";
import {
  counts,
  descend,
  recordStatuses,
  recordTree,
  type RecordNode,
  type Counts,
  type ProgressPage,
  type PageStatus,
} from "./progressData";
import { ARCHIVE, backendRequest, itemTitle, jobStages, providerNames, recordNumber, recordWords, type AvailableBundle } from "./backend";
import { useTasks } from "./tasks";
import TranscriptionDialog, { type ModelChoice } from "./TranscriptionDialog";
import type { ModelData } from "./ModelControls";
import JobErrorDialog from "./JobErrorDialog";
import AddItemsDialog from "./AddItemsDialog";
import SetupChecklist from "./SetupChecklist";
// One row of the overview: an item, its processing job, its page counts and, when it is one record, that record.
type Row = AvailableBundle & { counts: Counts; record?: string | null };
// A page of the series' items, as the server filters and pages them; totals cover every page of the series, and most is the
// most pages and records any of its items has.
type Overview = { items: Row[]; page: number; total: number; all: number; totals: Counts; most?: { pages: number; records: number } };
// One item with its pages and its records (each with the one it sits in).
type Item = AvailableBundle & { pages: ProgressPage[]; records?: { id: string; parent: string | null }[] };
const pageSize = 9;

// The overview request: a 0-based page of the items matching a search and a status.
function itemsPath(collectionId: number, page: number, search: string, status: string) {
  const params = new URLSearchParams({ page: String(page), size: String(pageSize) });
  if (search.trim()) params.set("search", search.trim());
  if (status !== "All") params.set("status", status);
  return `/collections/${collectionId}/items?${params}`;
}

// record: the record of the item shown (none: the item); pages: its pages listed instead of the records in it.
type View = { bundle: string | null; record: string | null; pages: boolean; query: string; status: string; pageNumber: number };
// Reads the dashboard view from the URL; its page number counts from 1.
function readView(): View {
  const params = new URLSearchParams(location.search);
  return {
    bundle: params.get("bundle"),
    record: params.get("record"),
    pages: params.get("show") === "pages",
    query: params.get("q") ?? "",
    status: params.get("status") ?? "All",
    pageNumber: Math.max(0, Math.floor(Number(params.get("page")) || 1) - 1),
  };
}
// Shows the bundle overview or the selected bundle’s pages using saved US8 data.
export default function ProgressDashboard() {
  // The collection whose bundles these are (/?collection=<id>).
  const collectionId = Number(new URLSearchParams(location.search).get("collection")) || 1;
  // Until the series loads it has no name, its records are "records" and they group, so nothing flickers away.
  // archiveSeries is the series' node on the archive: undefined until it loads, null when none is linked. archiveItems is how many items it had when linked.
  // levels: the names of the series' levels of record, top first (none: each item is one record).
  const [series, setSeries] = useState<{ name: string; recordName: string; levels: string[]; grouped: boolean; archiveSeries?: number | null; archiveItems: number | null; archiveIdentifier?: string | null }>({ name: "", recordName: "record", levels: ["record"], grouped: true, archiveItems: null });
  useEffect(() => {
    backendRequest<{ name: string; recordName: string; levels?: { name: string }[]; grouped: boolean; archiveSeries?: number | null; archiveItems?: number | null; archiveIdentifier?: string | null }>(`/collections/${collectionId}`)
      .then(({ name, recordName, levels, grouped, archiveSeries, archiveItems, archiveIdentifier }) => setSeries({ name, recordName, levels: levels ? levels.map((l) => l.name) : [recordName], grouped, archiveSeries: archiveSeries ?? null, archiveItems: archiveItems ?? null, archiveIdentifier }))
      .catch(() => {});
  }, [collectionId]);
  const words = recordWords(series.recordName);
  const canAdd = typeof series.archiveSeries === "number";
  // The series' items being added in the background, if any.
  const { tasks } = useTasks();
  const addingItems = tasks?.find((t) => t.kind === "items" && t.collectionId === collectionId && (t.status === "waiting" || t.status === "running"));
  // A status as shown: in the series' words, and without grouping where its pages don't group.
  const statusLabel = (s: string) =>
    s === "Not in a survey" ? `Not in ${words.a}` : s === "Transcribed — not grouped" && !series.grouped ? "Transcribed" : s;
  // The view lives in the URL (?collection, ?bundle, ?show, ?q, ?status, ?page) so refresh, Back and shared links keep it.
  // No bundle displays the series' items, which the server searches, filters and pages; a bundle displays that item's records,
  // or its pages when it has one record or ?show=pages, which this page does.
  const [view, setView] = useState(readView);
  useEffect(() => {
    const sync = () => setView(readView());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  const { query, status, pageNumber } = view;
  // Typing in search replaces the current history entry; every other change adds one.
  function show(next: Partial<View>, replace = false) {
    const v = { ...view, ...next };
    const params = new URLSearchParams({ collection: String(collectionId) });
    if (v.bundle) params.set("bundle", v.bundle);
    if (v.bundle && v.record) params.set("record", v.record);
    if (v.bundle && v.pages) params.set("show", "pages");
    if (v.query) params.set("q", v.query);
    if (v.status !== "All") params.set("status", v.status);
    if (v.pageNumber) params.set("page", String(v.pageNumber + 1));
    history[replace ? "replaceState" : "pushState"](null, "", `/?${params}`);
    setView(v);
  }
  // The server searches the items, so a typed search is sent once typing pauses.
  const [search, setSearch] = useState(query);
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query), query ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [query]);
  // Null until the first response; the last one stays up while the next loads.
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loadedItem, setLoadedItem] = useState<Item | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [starting, setStarting] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<{
    item: string;
    message: string;
  } | null>(null);
  const [jobError, setJobError] = useState("");
  const [adding, setAdding] = useState(false);
  const [transcribing, setTranscribing] = useState<AvailableBundle | null>(
    null,
  );
  // The saved transcription choice and sign-in status, for the setup banner. Null until both load; stays null if either request fails.
  const [setup, setSetup] = useState<{ configured: ModelData["configured"]; signedIn: Record<string, boolean> } | null>(null);
  const lastCheck = useRef(-Infinity); // a ref, so React's dev-mode remount doesn't repeat the load check
  useEffect(() => {
    // Not on the progress poll: /connections runs the CLIs' status checks. Focus checks at most every 30 s.
    async function check() {
      if (Date.now() - lastCheck.current < 30_000) return;
      lastCheck.current = Date.now();
      try {
        const [models, connections] = await Promise.all([
          backendRequest<ModelData>("/transcription-models"),
          backendRequest<Record<string, { signedIn: boolean }>>("/connections"),
        ]);
        setSetup({
          configured: models.configured,
          signedIn: Object.fromEntries(Object.entries(connections).map(([id, c]) => [id, Boolean(c?.signedIn)])),
        });
      } catch {
        setSetup(null);
      }
    }
    void check();
    window.addEventListener("focus", check);
    return () => window.removeEventListener("focus", check);
  }, []);
  const bundleName = view.bundle || "";
  const path = bundleName
    ? `/collections/${collectionId}/items/${encodeURIComponent(bundleName)}`
    : itemsPath(collectionId, pageNumber, search, status);
  useEffect(() => {
    // Ignore responses after unmounting and older requests that finish after a newer refresh.
    let active = true;
    let latest = 0;
    let loading = false;
    async function refresh() {
      const request = ++latest;
      loading = true;
      try {
        if (bundleName) {
          const detail = await backendRequest<Item>(path);
          // An item still being processed has no pages in the database yet, but its job may already have some results.
          let pages = detail.pages;
          if (!detail.loaded && detail.job?.id && !pages.length) {
            const saved = await backendRequest<{
              pages: {
                id: string;
                category: string;
                status: PageStatus;
                data: Record<string, unknown> | null;
              }[];
            }>(`/jobs/${detail.job.id}/transcripts`);
            pages = saved.pages.map((page) => ({
              id: page.id,
              label: `Pg ${Number(page.id.match(/_(\d+)$/)?.[1]) || page.id}`,
              category:
                (
                  {
                    main: "Main page",
                    coded: "Coded",
                    notes: "Notes",
                    blank: "Blank",
                    unidentified: "Not identified",
                    review: "Needs identification",
                    other: "Other",
                  } as Record<string, string>
                )[page.category] ?? page.category,
              status: page.status,
              flagCount: 0,
              savedData: page.data ?? undefined,
              model:
                typeof page.data?.model === "string" ? page.data.model : null,
            }));
          }
          if (!active || request !== latest) return;
          setLoadedItem({ ...detail, pages });
        } else {
          const data = await backendRequest<Overview>(path);
          if (!active || request !== latest) return;
          setOverview(data);
        }
        setError("");
      } catch (cause) {
        if (!active || request !== latest) return;
        setError(
          cause instanceof Error ? cause.message : "Could not load progress.",
        );
      } finally {
        if (request === latest) loading = false;
      }
    }
    void refresh();
    // Poll only a visible tab, and only after the previous refresh has finished.
    const timer = window.setInterval(() => {
      if (!document.hidden && !loading) void refresh();
    }, 5000);
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    // Clean up polling and both listeners when retrying, changing the view or leaving the dashboard.
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
    };
  }, [attempt, path, bundleName]);
  const item = loadedItem && bundleName && (loadedItem.name === bundleName || loadedItem.bundle === bundleName) ? loadedItem : null;
  // What the page shows: the item's pages, or the series' items.
  const loaded = bundleName ? item : overview;
  const bundleNotStarted = Boolean(item && !item.loaded && !item.job && item.pages.length === 0);

  // A loaded item's records as a tree, and the one shown (the item at the root): the one asked for, or down from it past any
  // level with only one thing in it.
  const tree = item?.loaded ? recordTree(item.pages, item.records) : null;
  const nodes = new Map<string, RecordNode>();
  const index = (n: RecordNode) => { nodes.set(n.id, n); n.children.forEach(index); };
  if (tree) index(tree);
  const opened = view.record ? nodes.get(view.record) : undefined; // none: the item, even when it leads to its one record
  const here = tree ? descend(opened ?? tree) : null;
  // A record's words by its level (how deep it is), and its name: its level and its number within the record above.
  const levelWords = (depth: number) => recordWords(series.levels[Math.min(depth, series.levels.length) - 1] ?? series.recordName);
  const recordLabel = (n: RecordNode) =>
    `${levelWords(n.depth).One} ${recordNumber(n.id, n.parent ?? item?.bundle)}`;
  const childWords = here ? levelWords(here.depth + 1) : words;
  // Summary cards cover the record or item shown, or every page of the series, regardless of filters.
  const totals = here ? counts(here.all) : item ? counts(item.pages) : (overview?.totals ?? counts([]));
  // The records in the one shown, each named, with where opening it leads; they're listed when there are several or one holds
  // more, unless its pages are asked for, by the switch or by a status only pages have (as an older link may).
  const recordRows = (here?.children ?? []).map((n) => ({ ...n, label: recordLabel(n), target: descend(n) }));
  const listed = recordRows.length > 1 || recordRows.some((r) => r.children.length > 0);
  const byRecord = listed && !view.pages && (status === "All" || recordStatuses.includes(status as PageStatus));
  // The pages of the record shown that are in none inside it: at the item, those in no record; else the record's own.
  const loose = here?.pages.length ?? 0;
  // Search page labels, IDs, and categories (or records' names), then apply the status filter.
  const matchingPages =
    (here?.all ?? item?.pages)?.filter(
      (p) =>
        `${p.label} ${p.id} ${p.category}`
          .toLowerCase()
          .includes(query.trim().toLowerCase()) &&
        (status === "All" || p.status === status),
    ) || [];
  const matchingRecords = recordRows.filter(
    (r) => `${r.label} ${r.id}`.toLowerCase().includes(query.trim().toLowerCase()) && (status === "All" || r.status === status),
  );
  // The overview leaves out a level no item has more than one of; without the counts, pages are shown and records aren't.
  const recordsColumn = (overview?.most?.records ?? 0) > 1;
  const pagesColumn = (overview?.most?.pages ?? 2) > 1;

  const totalRows = item ? (byRecord ? matchingRecords.length : matchingPages.length) : (overview?.total ?? 0);
  // A series with no items at all, as opposed to filters that match none.
  const noItems = !bundleName && overview?.all === 0 && !query.trim() && status === "All";
  const lastPage = Math.max(0, Math.ceil(totalRows / pageSize) - 1);
  // The server says which page it returned; it may be fewer than the URL asks for.
  const current = item ? Math.min(pageNumber, lastPage) : (overview?.page ?? 0);
  const start = current * pageSize;

  // Switch between overview and page list, resetting filters and pagination.
  function openBundle(name: string | null) {
    show({ bundle: name, record: null, pages: false, query: "", status: "All", pageNumber: 0 });
  }
  // A record of the item, in-app on a plain click; modified clicks keep the link's default.
  function openRecord(e: MouseEvent, id: string | null) {
    if (e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    show({ record: id, pages: false, query: "", status: "All", pageNumber: 0 });
  }
  const recordLink = (id: string) => `/?collection=${collectionId}&bundle=${encodeURIComponent(bundleName)}&record=${encodeURIComponent(id)}`;
  // The records the one shown sits inside, top first, but not one opening it leads past, as a crumb each.
  const outer: RecordNode[] = [];
  for (let n = here?.parent ? nodes.get(here.parent) : undefined; n; n = n.parent ? nodes.get(n.parent) : undefined) {
    if (descend(n) !== here) outer.unshift(n);
  }
  // A plain click on the collection's crumb returns in-app; modified clicks keep the link's default.
  function backToOverview(e: MouseEvent) {
    if (e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    openBundle(null);
  }
  // Prevent duplicate submissions, then refresh the dashboard after the API accepts a job.
  async function startTranscription(
    source: AvailableBundle,
    choice: ModelChoice,
  ) {
    if (starting) return;
    setStarting(source.pdf);
    setJobError("");
    try {
      const job = await backendRequest<NonNullable<AvailableBundle["job"]>>(
        "/jobs",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pdf: source.pdf, ...choice }),
        },
      );
      const started = <T extends AvailableBundle>(row: T): T => (row.pdf === source.pdf ? { ...row, job } : row);
      setOverview((o) => o && { ...o, items: o.items.map(started) });
      setLoadedItem((i) => i && started(i));
      setAttempt((n) => n + 1);
      setTranscribing(null);
    } catch (e) {
      setJobError(
        e instanceof Error ? e.message : "Could not start transcription.",
      );
    } finally {
      setStarting(null);
    }
  }
  // Open US7 at the exact survey and page selected through Review or View.
  function reviewLink(p: ProgressPage) {
    return `/?survey=${encodeURIComponent(p.surveyId!)}&page=${encodeURIComponent(p.reviewPageId!)}${p.status === "Awaiting transcription" ? "&action=transcribe" : ""}`;
  }
  const openable = (p: ProgressPage) => Boolean(item?.loaded) && Boolean(p.surveyId);
  const cell = "whitespace-normal px-1.5 sm:px-2 [overflow-wrap:anywhere]";
  const head = "whitespace-normal px-1.5 text-xs [overflow-wrap:anywhere] sm:px-2 sm:text-sm";
  const num = "text-right tabular-nums";
  // Stretched link: its overlay makes the whole row clickable; controls inside a row sit above it.
  const above = "relative z-10";
  const rowAction = "h-auto min-h-7 w-full flex-wrap px-1 py-1 text-xs sm:px-2.5 sm:text-[0.8rem]";
  // The table's columns: heading, width and, for a number, its alignment (sr-only: a heading only screen readers read).
  const columns: (readonly [string, string, string?])[] = byRecord
    ? [[childWords.One, "w-[24%]"], ["Pages", "w-[12%]", num], ["Flags", "w-[20%]"], ["Status", "w-[28%]"], ["Actions", "w-[16%]", "sr-only"]]
    : item
      ? [["Page", "w-[9%]"], ["Page category", "w-[16%]"], ["Flags", "w-[15%]"], ["Status", "w-[24%]"], ["Model", "w-[20%]"],
          ["Actions", "w-[16%]", "sr-only"]]
      : [
          ["Item", "w-[25%]"],
          ...(recordsColumn ? [[words.many.charAt(0).toUpperCase() + words.many.slice(1), "w-[12%]", num] as const] : []),
          ...(pagesColumn ? [["Total pages", recordsColumn ? "w-[12%]" : "w-[16%]", num] as const] : []),
          ["Ready to review", recordsColumn ? "w-[13%]" : "w-[17%]", `${num} sm:pr-6`],
          ["Review progress", recordsColumn ? "w-[20%]" : "w-[24%]"],
          ["Actions", "w-[18%]", "sr-only"],
        ];
  // What can be done here: export, add items from the archive (a linked series), import scans (the Prest survey for now).
  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      {canAdd && (
        <Button type="button" onClick={() => setAdding(true)}>
          <ListPlus /> Add items
        </Button>
      )}
      <ExportDialog
        surveyId={item?.pages.find((page) => page.surveyId)?.surveyId ?? ""}
        initialBundleId={item?.loaded ? item.bundle : undefined}
        defaultScope="bundle"
        collectionId={collectionId}
        recordName={series.recordName}
        hasDrafts={false}
        variant={canAdd ? "outline" : "default"}
      />
    </div>
  );
  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader series={{ id: collectionId, name: series.name }}
        crumbs={item ? [{ label: "Items", href: `/?collection=${collectionId}`, onClick: backToOverview },
          here && opened
            ? { label: itemTitle(item.name, item.archive), href: `/?collection=${collectionId}&bundle=${encodeURIComponent(bundleName)}`,
                onClick: (e: MouseEvent) => openRecord(e, null) }
            : { label: itemTitle(item.name, item.archive) },
          ...outer.map((n) => ({ label: recordLabel(n), href: recordLink(n.id), onClick: (e: MouseEvent) => openRecord(e, n.id) })),
          ...(here && opened ? [{ label: recordLabel(here) }] : [])] : []} />
      <main className="space-y-4 p-6">
        {item || bundleName ? (
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">
                {here && opened ? recordLabel(here) : item ? itemTitle(item.name, item.archive) : itemTitle(bundleName!)}
              </h1>
              <p className="text-sm text-muted-foreground">
                {item?.archive && !opened && (
                  <>
                    <a href={`${ARCHIVE}/nodes/view/${item.name}`} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 hover:underline">
                      {item.archive.identifier} <ExternalLink aria-hidden="true" className="size-3.5" />
                    </a>
                    {` · ${item.name} · `}
                  </>
                )}
                {item ? `${listed ? `${recordRows.length} ${recordRows.length === 1 ? childWords.one : childWords.many} · ` : ""}${totals.ready} pages ready to review` : ""}
              </p>
            </div>
            {actions}
          </div>
        ) : (
          <>
            <SeriesHeader series={{ id: collectionId, ...series }} tab="items" actions={actions} />
            <SetupChecklist collectionId={collectionId} />
            <div>
              <h2 className="text-xl font-semibold tracking-tight">All items</h2>
              <p className="text-sm text-muted-foreground">
                {overview ? `Track review progress across ${overview.all.toLocaleString()} items` : ""}
              </p>
            </div>
          </>
        )}
        {/* Display loading failures and allow retry; previously loaded data stays visible. */}
        {error && (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-3">
              Could not load current progress: {error}
              <Button variant="outline" size="sm" onClick={() => setAttempt((a) => a + 1)}>Try again</Button>
            </AlertDescription>
          </Alert>
        )}
        {setup && (!setup.configured || !setup.signedIn[setup.configured.provider]) && (
          <Alert role="status">
            <AlertDescription className="flex flex-wrap items-center gap-x-3 text-foreground">
              {setup.configured
                ? `${providerNames[setup.configured.provider] ?? setup.configured.provider} isn't signed in, so transcription won't work yet.`
                : "Transcription isn't set up yet. Choose a model in Settings to start transcribing."}
              <Button asChild variant="link" size="sm" className="h-auto p-0"><a href="/?view=settings">Open Settings</a></Button>
            </AlertDescription>
          </Alert>
        )}
        {addingItems && (
          <Alert role="status">
            <AlertDescription className="text-foreground">
              {addingItems.status === "waiting"
                ? "Waiting to add items from the archive."
                : addingItems.total > 0
                  ? `Adding items from the archive: ${addingItems.done.toLocaleString()} of ${addingItems.total.toLocaleString()}.`
                  : "Adding items from the archive…"}
            </AlertDescription>
          </Alert>
        )}
        {item && !item.loaded && (
          <Alert role="status">
            <AlertDescription className="text-foreground">
              {bundleNotStarted
                ? "This item has not been processed yet. Press Transcribe to get started."
                : `This item has not finished processing. Pages shown may not be transcribed${series.grouped ? `, grouped into ${words.many}` : ""} or identified yet. Please complete transcription.`}
            </AlertDescription>
          </Alert>
        )}

        {jobError && !transcribing && (
          <Alert variant="destructive">
            <AlertDescription>{jobError}</AlertDescription>
          </Alert>
        )}
        {!loaded && !error && (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner role="presentation" aria-hidden="true" />
            Loading review progress…
          </p>
        )}
        {loaded && (
          <>
            {/* Saved page statuses determine the totals and review progress. */}
            <div className="grid grid-cols-3 gap-2 sm:gap-4">
              {[
                ["Total pages", totals.total],
                ["Reviewed", totals.reviewed],
                ["Ready to review", totals.ready],
              ].map(([label, value]) => (
                <Card key={label}>
                  <CardHeader>
                    <CardDescription>{label}</CardDescription>
                    <CardTitle
                      className="text-2xl font-semibold tracking-tight sm:text-3xl"
                      data-testid={`stat-${String(label).toLowerCase().replace(/ /g, "-")}`}
                    >
                      {value.toLocaleString()}
                    </CardTitle>
                  </CardHeader>
                </Card>
              ))}
            </div>
            {/* Changing search or status returns the table to its first page. */}
            <div className="flex flex-wrap items-center gap-2" data-testid="progress-filters">
              {listed && (
                <div role="group" aria-label="Show" className="flex gap-1">
                  {([[true, childWords.many], [false, "pages"]] as const).map(([records, label]) => (
                    <Button key={label} variant={byRecord === records ? "secondary" : "ghost"} size="sm" aria-pressed={byRecord === records}
                      onClick={() => show({ pages: !records, query: "", status: "All", pageNumber: 0 })}>
                      {label.charAt(0).toUpperCase() + label.slice(1)}
                    </Button>
                  ))}
                </div>
              )}
              <div className="relative w-full min-w-48 sm:w-auto sm:max-w-md sm:flex-1">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="pl-8"
                  aria-label={byRecord ? `Search ${childWords.many}` : item ? "Search pages" : "Search items"}
                  placeholder={
                    byRecord ? `Search ${childWords.one} number…` : item ? "Search page number…"
                      : overview?.items.some((b) => b.archive) ? "Search title, identifier or number…" : "Search item number…"
                  }
                  value={query}
                  onChange={(e) => show({ query: e.target.value, pageNumber: 0 }, true)}
                />
              </div>
              <NativeSelect
                className="w-full sm:w-auto"
                aria-label="Status"
                value={status}
                onChange={(e) => show({ status: e.target.value, pageNumber: 0 })}
              >
                {(byRecord ? ["All", ...recordStatuses] : [
                  "All",
                  ...(!item
                    ? ["Transcription in progress"]
                    : [
                        "Transcribed — not grouped",
                        "Needs identification",
                        "Not required",
                      ]),
                  "Awaiting transcription",
                  "Ready to review",
                  "Reviewed",
                  ...(series.grouped ? ["Not in a survey"] : []),
                ]).map((s) => (
                  <option key={s} value={s}>
                    Status: {statusLabel(s)}
                  </option>
                ))}
              </NativeSelect>
              {item && !item.loaded && (
                <Button
                  disabled={
                    starting !== null ||
                    item.job?.status === "waiting" ||
                    item.job?.status === "running"
                  }
                  onClick={() => {
                    setJobError("");
                    setTranscribing(item);
                  }}
                >
                  {starting === item.pdf
                    ? "Starting…"
                    : item.job?.status === "waiting"
                      ? "Waiting — queued"
                      : item.job?.status === "running"
                        ? "Transcription in progress"
                        : bundleNotStarted
                          ? "Transcribe"
                          : "Complete transcription"}
                </Button>
              )}
            </div>
            {byRecord && loose > 0 && (
              <p className="flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
                {here === tree ? (
                  <>
                    {loose} {loose === 1 ? "page isn't" : "pages aren't"} in {childWords.a}.
                    <Button variant="link" size="sm" className="h-auto p-0" onClick={() => show({ pages: true, query: "", status: "All", pageNumber: 0 })}>
                      Show pages
                    </Button>
                  </>
                ) : (
                  <>
                    {loose} {loose === 1 ? "page is" : "pages are"} the {levelWords(here!.depth).one}'s own.
                    <a className="underline-offset-4 hover:underline text-primary" href={reviewLink(here!.pages[0])}>Review {loose === 1 ? "it" : "them"}</a>
                  </>
                )}
              </p>
            )}
            {/* The same table shows bundle summaries, an item's records or its pages. */}
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow>
                    {columns.map(([h, width, extra]) => (
                      <TableHead key={h} className={`${head} ${width} ${extra?.startsWith(num) ? extra : ""}`}>
                        {extra === "sr-only" ? <span className="sr-only">{h}</span> : h}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {byRecord
                    ? matchingRecords.slice(start, start + pageSize).map((r) => (
                        <TableRow key={r.id} clickable>
                          <TableCell className={cell}>
                            {r.target.children.length ? (
                              <TableRowLink href={recordLink(r.target.id)} onClick={(e) => openRecord(e, r.target.id)} aria-label={`Open ${r.label}`}>
                                {r.label}
                              </TableRowLink>
                            ) : (
                              <TableRowLink href={reviewLink(r.target.page!)}
                                aria-label={`${r.status === "Awaiting transcription" ? "Transcribe" : r.status === "Reviewed" ? "View" : "Review"} ${r.label}`}>
                                {r.label}
                              </TableRowLink>
                            )}
                          </TableCell>
                          <TableCell className={`${cell} ${num}`}>{r.all.length}</TableCell>
                          <TableCell className={cell}>{r.flagCount > 0 ? `${r.flagCount} need checking` : "No flags"}</TableCell>
                          <TableCell className={cell}>
                            <Badge className="h-auto whitespace-normal"
                              variant={r.status === "Reviewed" ? "default" : r.status === "Ready to review" ? "secondary" : "outline"}>
                              {r.status}
                            </Badge>
                          </TableCell>
                          <TableCell className={cell}><TableOpenArrow /></TableCell>
                        </TableRow>
                      ))
                    : item
                    ? matchingPages.slice(start, start + pageSize).map((p) => (
                        <TableRow
                          key={p.id}
                          clickable={openable(p)}
                        >
                          <TableCell className={cell}>
                            {openable(p) ? (
                              <TableRowLink
                                href={reviewLink(p)}
                                aria-label={`${p.status === "Awaiting transcription" ? "Transcribe" : p.status === "Reviewed" ? "View" : "Review"} ${p.label}`}
                              >
                                {p.label}
                              </TableRowLink>
                            ) : (
                              p.label
                            )}
                          </TableCell>
                          <TableCell className={cell}>{p.category}</TableCell>
                          <TableCell className={cell}>
                            {!item.loaded
                              ? "Pending checks"
                              : p.flagCount > 0
                                ? `${p.flagCount} need checking`
                                : "No flags"}
                          </TableCell>
                          <TableCell className={cell}>
                            <Badge
                              className="h-auto whitespace-normal"
                              variant={p.status === "Reviewed" ? "default" : p.status === "Ready to review" ? "secondary" : "outline"}
                            >
                              {statusLabel(p.status)}
                            </Badge>
                          </TableCell>
                          <TableCell className={cell}>{p.model || "—"}</TableCell>
                          <TableCell className={cell}>
                            {!item.loaded ? (
                              <span>Unavailable at the moment</span>
                            ) : p.surveyId ? (
                              <TableOpenArrow />
                            ) : (
                              <span className="block text-right text-muted-foreground" title={`This page has no ${words.one} assignment`}>
                                —
                              </span>
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    : (overview?.items ?? []).map((b) => {
                          const c = b.counts;
                          const percent =
                            c.reviewable > 0
                              ? Math.round((c.reviewed / c.reviewable) * 100)
                              : null;
                          return (
                            <TableRow key={b.bundle} clickable>
                              <TableCell className={cell}>
                                {/* An item that is one record opens it straight away; any other, its records or pages here. */}
                                <TableRowLink
                                  href={b.loaded && b.record ? `/?survey=${encodeURIComponent(b.record)}`
                                    : `/?collection=${collectionId}&bundle=${encodeURIComponent(b.name)}`}
                                  onClick={(e) => {
                                    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || (b.loaded && b.record)) return;
                                    e.preventDefault();
                                    openBundle(b.name);
                                  }}
                                >
                                  {b.archive?.title ?? b.name}
                                </TableRowLink>
                                {b.archive && (
                                  <span className="block text-muted-foreground">
                                    <span className="hidden sm:inline">{b.archive.identifier} · </span>{b.name}
                                  </span>
                                )}
                              </TableCell>
                              {recordsColumn && <TableCell className={`${cell} ${num}`}>{c.records}</TableCell>}
                              {pagesColumn && <TableCell className={`${cell} ${num}`}>{c.total}</TableCell>}
                              <TableCell className={`${cell} ${num} sm:pr-6`}>{c.ready}</TableCell>
                              <TableCell className={cell}>
                                <div className="flex max-w-sm flex-col gap-1.5">
                                  <span>
                                    {percent === null
                                      ? "No reviewable pages"
                                      : `${c.reviewed} / ${c.reviewable} reviewed · ${percent}%`}
                                  </span>

                                  {c.unassigned > 0 && (
                                    <span className="text-muted-foreground">
                                      {c.unassigned} {c.unassigned === 1 ? "page" : "pages"} not in {words.a}
                                    </span>
                                  )}

                                  {c.reviewable > 0 && (
                                    <Progress
                                      className="h-2"
                                      aria-label={`${itemTitle(b.name, b.archive)} review progress`}
                                      value={(c.reviewed / c.reviewable) * 100}
                                      max={c.reviewable}
                                      aria-valuenow={c.reviewed}
                                    />
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className={cell}>
                                {!b.loaded ? (
                                  <div className="space-y-1.5">
                                    {b.job?.status === "waiting" ||
                                    b.job?.status === "running" ? (
                                      <div role="status">
                                        <strong>
                                          {b.job.status === "waiting"
                                            ? "Waiting — queued"
                                            : "Running"}
                                        </strong>
                                        <div className="text-muted-foreground">
                                          {b.job.status === "waiting"
                                            ? "Waiting for the worker to start this job"
                                            : ((b.job.step === "group"
                                                ? !series.levels.length ? `Making the item ${words.a}`
                                                  : series.grouped ? `Grouping pages into ${words.many}` : `Making each page ${words.a}`
                                                : jobStages[b.job.step ?? ""]) ??
                                              b.job.step ??
                                              "Starting processing")}
                                        </div>
                                        {b.job.status === "running" &&
                                          b.job.step === "transcribe" &&
                                          b.job.totalPages > 0 && (
                                            <small className="text-muted-foreground">
                                              {b.job.donePages}/
                                              {b.job.totalPages} pages
                                              transcribed
                                            </small>
                                          )}
                                      </div>
                                    ) : (
                                      <>
                                        {b.job?.status !== "failed" && (
                                          <>
                                            <Badge variant="outline" className="h-auto whitespace-normal">Not transcribed</Badge>{" "}
                                          </>
                                        )}
                                        <Button
                                          variant="outline"
                                          size="sm"
                                          className={`${rowAction} ${above}`}
                                          disabled={starting !== null}
                                          onClick={() => {
                                            setJobError("");
                                            setTranscribing(b);
                                          }}
                                        >
                                          {starting === b.pdf
                                            ? "Starting…"
                                            : b.job?.status === "failed"
                                              ? "Retry transcription"
                                              : "Transcribe"}
                                        </Button>
                                      </>
                                    )}
                                    {b.job?.status === "failed" && (
                                      <p className="text-xs text-destructive">
                                        Transcription failed
                                        {b.job.error && (
                                          <>
                                            :{" "}
                                            <Button
                                              variant="link"
                                              size="sm"
                                              className={`h-auto p-0 text-xs text-destructive underline ${above}`}
                                              onClick={() =>
                                                setErrorDetails({
                                                  item: itemTitle(b.name, b.archive),
                                                  message:
                                                    b.job!.error!,
                                                })
                                              }
                                            >
                                              more details here
                                            </Button>
                                          </>
                                        )}
                                      </p>
                                    )}
                                  </div>
                                ) : (
                                  <TableOpenArrow />
                                )}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                  {/* Offer a filter reset when no rows match. */}
                  {!totalRows && (
                    <TableRow>
                      <TableCell colSpan={columns.length}>
                        {noItems ? (
                          <div className="flex flex-col items-center gap-3 p-6 text-center whitespace-normal">
                            <p className="font-medium">No items yet.</p>
                            {series.archiveSeries !== undefined && (
                              <p className="text-muted-foreground">
                                {canAdd
                                  ? "Add items from the archive to start. Set up the series' page types first, so its pages can be read."
                                  : "This series isn't linked to the archive, so it has no items to add."}
                              </p>
                            )}
                            {canAdd && (
                              <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
                                <ListPlus /> Add items
                              </Button>
                            )}
                          </div>
                        ) : (
                          <div className="flex flex-wrap items-center justify-center gap-3 p-6 text-center whitespace-normal">
                            No {byRecord ? childWords.many : item ? "pages" : "items"} match your filters.
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => show({ query: "", status: "All", pageNumber: 0 })}
                            >
                              Clear filters
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            {/* Show the visible row range and disable navigation at either end. */}
            <footer className="flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <span>
                Showing {totalRows ? start + 1 : 0}–
                {Math.min(start + pageSize, totalRows)} of {totalRows}{" "}
                {byRecord ? childWords.many : item ? "pages" : "items"}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={current === 0}
                  onClick={() => show({ pageNumber: current - 1 })}
                >
                  Previous
                </Button>
                <span>
                  Page {current + 1} of {lastPage + 1}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={current === lastPage}
                  onClick={() => show({ pageNumber: current + 1 })}
                >
                  Next <ArrowRight />
                </Button>
              </div>
            </footer>
          </>
        )}
      </main>
      {adding && (
        <AddItemsDialog
          collectionId={collectionId}
          seriesTitle={series.name || "this series"}
          archiveItems={series.archiveItems}
          onClose={() => setAdding(false)}
          onAdded={() => setAttempt((n) => n + 1)}
        />
      )}
      {errorDetails && (
        <JobErrorDialog
          {...errorDetails}
          onClose={() => setErrorDetails(null)}
        />
      )}
      {transcribing && (
        <TranscriptionDialog
          source={transcribing}
          busy={starting !== null}
          error={jobError}
          onClose={() => {
            setTranscribing(null);
            setJobError("");
          }}
          onStart={(choice) => void startTranscription(transcribing, choice)}
        />
      )}
    </div>
  );
}
