import ExportDialog from "../export/ExportDialog";
// Bundle overview and page list
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Search, Upload } from "lucide-react";
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
  TableRow,
} from "@/components/ui/table";
import {
  counts,
  type Bundle,
  type ProgressPage,
  type PageStatus,
} from "./progressData";
import { backendRequest, type AvailableBundle } from "./backend";
import TranscriptionDialog, { type ModelChoice } from "./TranscriptionDialog";
import JobErrorDialog from "./JobErrorDialog";
// Attach processing metadata to database progress so unfinished bundles can appear too.
type DashboardBundle = Bundle & { source?: AvailableBundle };
const pageSize = 9;
// Translate backend pipeline step names into descriptions for reviewers.
const jobStages: Record<string, string> = {
  split: "Preparing page images (downloads PDF if needed)",
  identify: "Identifying page types",
  preprocess: "Preparing images",
  transcribe: "Transcribing pages",
  group: "Grouping surveys",
  load: "Saving results to database",
};

// Shows the bundle overview or the selected bundle’s pages using saved US8 data.
export default function ProgressDashboard() {
  // Null means data has not loaded yet; an empty array means no bundles were returned.
  const [bundles, setBundles] = useState<DashboardBundle[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [starting, setStarting] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<{
    bundle: string;
    message: string;
  } | null>(null);
  const [jobError, setJobError] = useState("");
  const [transcribing, setTranscribing] = useState<AvailableBundle | null>(
    null,
  );
  useEffect(() => {
    // Ignore responses after unmounting and older requests that finish after a newer refresh.
    let active = true;
    let latest = 0;
    async function refresh() {
      const request = ++latest;
      try {
        // /progress supplies saved review totals; /bundles also includes unprocessed sources.
        const [data, available] = await Promise.all([
          backendRequest<Bundle[]>("/progress"),
          backendRequest<AvailableBundle[]>("/bundles"),
        ]);
        // Refresh queued/running job details before displaying the current processing stage.
        await Promise.all(
          available.map(async (source) => {
            if (
              source.job?.id &&
              ["waiting", "running"].includes(source.job.status)
            ) {
              source.job = await backendRequest<
                NonNullable<AvailableBundle["job"]>
              >(`/jobs/${source.job.id}`);
            }
          }),
        );
        // Incomplete jobs can expose page results before a bundle is loaded into the database.
        const partial = new Map<string, ProgressPage[]>();
        await Promise.all(
          available.map(async (source) => {
            if (source.loaded || !source.job?.id) return;
            const saved = await backendRequest<{
              pages: {
                id: string;
                category: string;
                status: PageStatus;
                data: Record<string, unknown> | null;
              }[];
            }>(`/jobs/${source.job.id}/transcripts`);
            partial.set(
              source.bundle,
              saved.pages.map((page) => ({
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
              })),
            );
          }),
        );
        if (!active || request !== latest) return;
        // Merge by bundle ID, keeping database pages in preference to partial job results.
        const merged = new Map<string, DashboardBundle>(
          data.map((b) => [b.id, b]),
        );
        for (const source of available) {
          const existing = merged.get(source.bundle);
          merged.set(source.bundle, {
            ...existing,
            id: source.bundle,
            name: source.name,
            pages: existing?.pages ?? partial.get(source.bundle) ?? [],
            source,
          });
        }
        setBundles(
          [...merged.values()].sort((a, b) =>
            (a.name ?? a.id).localeCompare(b.name ?? b.id, undefined, {
              numeric: true,
            }),
          ),
        );
        setError("");
      } catch (cause) {
        if (!active || request !== latest) return;
        setError(
          cause instanceof Error ? cause.message : "Could not load progress.",
        );
      }
    }
    void refresh();
    const timer = window.setInterval(refresh, 5000);
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    // Clean up polling and both listeners when retrying or leaving the dashboard.
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
    };
  }, [attempt]);
  // A null selection displays all bundles; a selected ID displays that bundle’s pages.
  const [bundleId, setBundleId] = useState<string | null>(null);

  // Search, status filtering, and pagination apply to the currently displayed table.
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");
  const [pageNumber, setPageNumber] = useState(0);

  const bundle = (bundles ?? []).find((b) => b.id === bundleId);
  const bundleNotStarted = Boolean(
    bundle?.source &&
    !bundle.source.loaded &&
    !bundle.source.job &&
    bundle.pages.length === 0,
  );

  // Summary cards cover the selected bundle or all loaded pages, regardless of filters.
  const totals = counts(
    bundle ? bundle.pages : (bundles ?? []).flatMap((b) => b.pages),
  );
  // Reviewed requires every page; other statuses match bundles with pending pages.
  const matchingBundles = (bundles ?? []).filter(
    (b) =>
      `${b.name ?? ""} ${b.id}`.includes(query.trim()) &&
      (status === "All" ||
        (status === "Awaiting transcription" && b.source && !b.source.loaded) ||
        (status === "Transcription in progress" &&
          b.source &&
          !b.source.loaded &&
          b.source.job?.status === "running") ||
        (status === "Reviewed"
          ? counts(b.pages).reviewable > 0 &&
            counts(b.pages).reviewed === counts(b.pages).reviewable
          : b.pages.some((p) => p.status === status))),
  );
  // Search page labels, IDs, and categories, then apply the status filter.
  const matchingPages =
    bundle?.pages.filter(
      (p) =>
        `${p.label} ${p.id} ${p.category}`
          .toLowerCase()
          .includes(query.trim().toLowerCase()) &&
        (status === "All" || p.status === status),
    ) || [];

  const totalRows = bundle ? matchingPages.length : matchingBundles.length;
  const lastPage = Math.max(0, Math.ceil(totalRows / pageSize) - 1);
  const current = Math.min(pageNumber, lastPage);
  const start = current * pageSize;

  // Switch between overview and page list, resetting filters and pagination.
  function openBundle(id: string | null) {
    setBundleId(id);
    setQuery("");
    setStatus("All");
    setPageNumber(0);
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
      setBundles(
        (current) =>
          current?.map((b) =>
            b.source?.pdf === source.pdf
              ? { ...b, source: { ...b.source, job } }
              : b,
          ) ?? null,
      );
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
  const cell = "whitespace-normal px-1.5 sm:px-2 [overflow-wrap:anywhere]";
  const head = "whitespace-normal px-1.5 text-xs [overflow-wrap:anywhere] sm:px-2 sm:text-sm";
  const rowAction = "h-auto min-h-7 w-full flex-wrap px-1 py-1 text-xs sm:px-2.5 sm:text-[0.8rem]";
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="flex items-center justify-between gap-4 border-b px-6 py-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Wilfred Prest Survey</h1>
          <p className="text-sm text-muted-foreground">Review Progress</p>
        </div>
        {bundle && (
          <Button variant="outline" onClick={() => openBundle(null)}>
            <ArrowLeft /> Back to all bundles
          </Button>
        )}
      </header>
      <main className="space-y-4 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">
              {bundle
                ? `Bundle Number · ${bundle.name ?? bundle.id}`
                : "All survey bundles"}
            </h2>
            <p className="text-sm text-muted-foreground">
              {bundle
                ? `${totals.ready} pages ready to review`
                : `Track review progress across ${(bundles ?? []).length} bundles`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <ExportDialog
              surveyId={
                bundle?.pages.find((page) => page.surveyId)?.surveyId ?? ""
              }
              initialBundleId={
                bundle && (!bundle.source || bundle.source.loaded)
                  ? bundle.id
                  : undefined
              }
              defaultScope="bundle"
              hasDrafts={false}
            />
            <Button type="button" variant="outline" onClick={() => { window.location.href = "/?view=import"; }}>
              <Upload /> Import
            </Button>
          </div>
        </div>
        {/* Display loading failures and allow retry; previously loaded data stays visible. */}
        {error && (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-3">
              Could not load current progress: {error}
              <Button variant="outline" size="sm" onClick={() => setAttempt((a) => a + 1)}>Try again</Button>
            </AlertDescription>
          </Alert>
        )}
        {bundle?.source && !bundle.source.loaded && (
          <Alert role="status">
            <AlertDescription className="text-foreground">
              {bundleNotStarted
                ? "This bundle has not been processed yet. Press Transcribe to get started."
                : "This bundle has not finished processing. Pages shown may not be transcribed, grouped into survey or identified yet. Please complete transcription."}
            </AlertDescription>
          </Alert>
        )}

        {jobError && !transcribing && (
          <Alert variant="destructive">
            <AlertDescription>{jobError}</AlertDescription>
          </Alert>
        )}
        {!bundles && !error && (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner role="presentation" aria-hidden="true" />
            Loading review progress…
          </p>
        )}
        {bundles && (
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
              <div className="relative w-full min-w-48 sm:w-auto sm:max-w-md sm:flex-1">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="pl-8"
                  aria-label={bundle ? "Search pages" : "Search bundles"}
                  placeholder={
                    bundle ? "Search page number…" : "Search bundle number…"
                  }
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setPageNumber(0);
                  }}
                />
              </div>
              <NativeSelect
                className="w-full sm:w-auto"
                aria-label="Status"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPageNumber(0);
                }}
              >
                {[
                  "All",
                  ...(!bundle
                    ? ["Transcription in progress"]
                    : [
                        "Transcribed — not grouped",
                        "Needs identification",
                        "Not required",
                      ]),
                  "Awaiting transcription",
                  "Ready to review",
                  "Reviewed",
                  "Not in a survey",
                ].map((s) => (
                  <option key={s} value={s}>
                    Status: {s}
                  </option>
                ))}
              </NativeSelect>
              {bundle?.source && !bundle.source.loaded && (
                <Button
                  disabled={
                    starting !== null ||
                    bundle.source.job?.status === "waiting" ||
                    bundle.source.job?.status === "running"
                  }
                  onClick={() => {
                    setJobError("");
                    setTranscribing(bundle.source!);
                  }}
                >
                  {starting === bundle.source.pdf
                    ? "Starting…"
                    : bundle.source.job?.status === "waiting"
                      ? "Waiting — queued"
                      : bundle.source.job?.status === "running"
                        ? "Transcription in progress"
                        : bundleNotStarted
                          ? "Transcribe"
                          : "Complete transcription"}
                </Button>
              )}
            </div>
            {/* The same table shows bundle summaries or individual page details. */}
            <div className="rounded-md border">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow>
                    {(bundle
                      ? [
                          ["Page", "w-[9%]"],
                          ["Page category", "w-[16%]"],
                          ["Flags", "w-[15%]"],
                          ["Status", "w-[24%]"],
                          ["Model", "w-[20%]"],
                          ["Action", "w-[16%]"],
                        ]
                      : [
                          ["Bundle number", "w-[13%]"],
                          ["Total pages", "w-[20%]"],
                          ["Ready to review", "w-[20%]"],
                          ["Review progress", "w-[29%]"],
                          ["Action", "w-[18%]"],
                        ]
                    ).map(([h, width]) => (
                      <TableHead key={h} className={`${head} ${width}`}>{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {bundle
                    ? matchingPages.slice(start, start + pageSize).map((p) => (
                        <TableRow key={p.id}>
                          <TableCell className={cell}>{p.label}</TableCell>
                          <TableCell className={cell}>{p.category}</TableCell>
                          <TableCell className={cell}>
                            {bundle.source && !bundle.source.loaded
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
                              {p.status}
                            </Badge>
                          </TableCell>
                          <TableCell className={cell}>{p.model || "—"}</TableCell>
                          <TableCell className={cell}>
                            {bundle.source && !bundle.source.loaded ? (
                              <span>Unavailable at the moment</span>
                            ) : p.surveyId ? (
                              <Button asChild variant="outline" size="sm" className={rowAction}>
                                <a href={reviewLink(p)}>
                                  {p.status === "Awaiting transcription" ? "Transcribe" : p.status === "Reviewed" ? "View" : "Review"}
                                  <ArrowRight />
                                </a>
                              </Button>
                            ) : (
                              <Button
                                variant="outline"
                                size="sm"
                                className={rowAction}
                                disabled
                                title="This page has no survey assignment"
                              >
                                Review
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    : matchingBundles
                        .slice(start, start + pageSize)
                        .map((b) => {
                          const c = counts(b.pages);
                          const percent =
                            c.reviewable > 0
                              ? Math.round((c.reviewed / c.reviewable) * 100)
                              : null;
                          return (
                            <TableRow key={b.id}>
                              <TableCell className={cell}>
                                <Button
                                  variant="link"
                                  className="h-auto p-0 text-foreground underline"
                                  onClick={() => openBundle(b.id)}
                                >
                                  {b.name ?? b.id}
                                </Button>
                              </TableCell>
                              <TableCell className={cell}>{c.total}</TableCell>
                              <TableCell className={cell}>{c.ready}</TableCell>
                              <TableCell className={cell}>
                                <div className="flex max-w-sm flex-col gap-1.5">
                                  <span>
                                    {percent === null
                                      ? "No reviewable pages"
                                      : `${c.reviewed} / ${c.reviewable} reviewed · ${percent}%`}
                                  </span>

                                  {c.unassigned > 0 && (
                                    <span className="text-muted-foreground">
                                      {c.unassigned} pages not in a survey
                                    </span>
                                  )}

                                  {c.reviewable > 0 && (
                                    <Progress
                                      className="h-2"
                                      aria-label={`Bundle ${b.id} review progress`}
                                      value={(c.reviewed / c.reviewable) * 100}
                                      max={c.reviewable}
                                      aria-valuenow={c.reviewed}
                                    />
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className={cell}>
                                {b.source && !b.source.loaded ? (
                                  <div className="space-y-1.5">
                                    {b.source.job?.status === "waiting" ||
                                    b.source.job?.status === "running" ? (
                                      <div role="status">
                                        <strong>
                                          {b.source.job.status === "waiting"
                                            ? "Waiting — queued"
                                            : "Running"}
                                        </strong>
                                        <div className="text-muted-foreground">
                                          {b.source.job.status === "waiting"
                                            ? "Waiting for the worker to start this job"
                                            : (jobStages[
                                                b.source.job.step ?? ""
                                              ] ??
                                              b.source.job.step ??
                                              "Starting processing")}
                                        </div>
                                        {b.source.job.status === "running" &&
                                          b.source.job.step === "transcribe" &&
                                          b.source.job.totalPages > 0 && (
                                            <small className="text-muted-foreground">
                                              {b.source.job.donePages}/
                                              {b.source.job.totalPages} pages
                                              transcribed
                                            </small>
                                          )}
                                      </div>
                                    ) : (
                                      <>
                                        {b.source.job?.status !== "failed" && (
                                          <>
                                            <Badge variant="outline" className="h-auto whitespace-normal">Not transcribed</Badge>{" "}
                                          </>
                                        )}
                                        <Button
                                          variant="outline"
                                          size="sm"
                                          className={rowAction}
                                          disabled={starting !== null}
                                          onClick={() => {
                                            setJobError("");
                                            setTranscribing(b.source!);
                                          }}
                                        >
                                          {starting === b.source.pdf
                                            ? "Starting…"
                                            : b.source.job?.status === "failed"
                                              ? "Retry transcription"
                                              : "Transcribe"}
                                        </Button>
                                      </>
                                    )}
                                    {b.source.job?.status === "failed" && (
                                      <p className="text-xs text-destructive">
                                        Transcription failed
                                        {b.source.job.error && (
                                          <>
                                            :{" "}
                                            <Button
                                              variant="link"
                                              size="sm"
                                              className="h-auto p-0 text-xs text-destructive underline"
                                              onClick={() =>
                                                setErrorDetails({
                                                  bundle: b.name ?? b.id,
                                                  message:
                                                    b.source!.job!.error!,
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
                                ) : c.ready ? (
                                  <Button variant="outline" size="sm" className={rowAction} onClick={() => openBundle(b.id)}>
                                    Review <ArrowRight />
                                  </Button>
                                ) : c.reviewable > 0 &&
                                  c.reviewed === c.reviewable ? (
                                  <Button variant="outline" size="sm" className={rowAction} onClick={() => openBundle(b.id)}>
                                    View <ArrowRight />
                                  </Button>
                                ) : (
                                  <Button variant="outline" size="sm" className={rowAction} onClick={() => openBundle(b.id)}>
                                    View
                                  </Button>
                                )}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                  {/* Offer a filter reset when no rows match. */}
                  {!totalRows && (
                    <TableRow>
                      <TableCell colSpan={bundle ? 6 : 5}>
                        <div className="flex flex-wrap items-center justify-center gap-3 p-6 text-center whitespace-normal">
                          No {bundle ? "pages" : "bundles"} match your filters.
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setQuery("");
                              setStatus("All");
                              setPageNumber(0);
                            }}
                          >
                            Clear filters
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
            {/* Show the visible row range and disable navigation at either end. */}
            <footer className="flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <span>
                Showing {totalRows ? start + 1 : 0}–
                {Math.min(start + pageSize, totalRows)} of {totalRows}{" "}
                {bundle ? "pages" : "bundles"}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={current === 0}
                  onClick={() => setPageNumber(current - 1)}
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
                  onClick={() => setPageNumber(current + 1)}
                >
                  Next <ArrowRight />
                </Button>
              </div>
            </footer>
          </>
        )}
      </main>
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
