// Bundle overview and page list
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Search, Upload, Download } from "lucide-react";
import {
  counts,
  type Bundle,
  type ProgressPage,
  type PageStatus,
} from "./progressData";
import { backendRequest, type AvailableBundle } from "./backend";
import "./progress.css";
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
          ? b.pages.length > 0 && b.pages.every((p) => p.status === "Reviewed")
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
    return `/?survey=${encodeURIComponent(p.surveyId!)}&page=${encodeURIComponent(p.reviewPageId!)}`;
  }
  return (
    <div className="progress-app">
      <header className="progress-header">
        <div>
          <h1>Wilfred Prest Survey</h1>
          <p>Review Progress</p>
        </div>
        {bundle && (
          <button onClick={() => openBundle(null)}>
            <ArrowLeft size={17} /> Back to all bundles
          </button>
        )}
      </header>
      <main className="progress-main">
        <div className="progress-title">
          <div>
            <h2>
              {bundle
                ? `Bundle Number · ${bundle.name ?? bundle.id}`
                : "All survey bundles"}
            </h2>
            <p>
              {bundle
                ? `${totals.ready} pages ready to review`
                : `Track review progress across ${(bundles ?? []).length} bundles`}
            </p>
          </div>
          {/* Import and export will be implemented separately. */}
          <div className="progress-actions">
            <button type="button" disabled title="Export coming soon">
              <Download size={16} /> Export
            </button>
            <button type="button" disabled title="Import coming soon">
              <Upload size={16} /> Import
            </button>
          </div>
        </div>
        {/* Display loading failures and allow retry; previously loaded data stays visible. */}
        {error && (
          <div role="alert">
            Could not load current progress: {error}
            <button onClick={() => setAttempt((a) => a + 1)}>Try again</button>
          </div>
        )}
        {bundle?.source && !bundle.source.loaded && (
          <p role="status" className="progress-incomplete-warning">
            {bundleNotStarted
              ? "This bundle has not been processed yet. Press Transcribe to get started."
              : "This bundle has not finished processing. Pages shown may not be transcribed, grouped into survey or identified yet. Please complete transcription."}
          </p>
        )}

        {jobError && !transcribing && <p role="alert">{jobError}</p>}
        {!bundles && !error && <p role="status">Loading review progress…</p>}
        {bundles && (
          <>
            {/* Saved page statuses determine the totals and review progress. */}
            <div className="progress-stats">
              {[
                ["Total pages", totals.total],
                ["Reviewed", totals.reviewed],
                ["Ready to review", totals.ready],
              ].map(([label, value]) => (
                <section key={label}>
                  <span>{label}</span>
                  <strong>{value.toLocaleString()}</strong>
                </section>
              ))}
            </div>
            {/* Changing search or status returns the table to its first page. */}
            <div className="progress-filters">
              <label className="progress-search">
                <Search size={19} />
                <input
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
              </label>
              <select
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
                ].map((s) => (
                  <option key={s} value={s}>
                    Status: {s}
                  </option>
                ))}
              </select>
              {bundle?.source && !bundle.source.loaded && (
                <button
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
                </button>
              )}
            </div>
            {/* The same table shows bundle summaries or individual page details. */}
            <div className="progress-table-wrap">
              <table
                className={`progress-table${bundle ? " progress-pages-table" : ""}`}
              >
                <thead>
                  <tr>
                    {(bundle
                      ? [
                          "Page",
                          "Page category",
                          "Flags",
                          "Status",
                          "Model",
                          "Action",
                        ]
                      : [
                          "Bundle number",
                          "Total pages",
                          "Ready to review",
                          "Review progress",
                          "Action",
                        ]
                    ).map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {bundle
                    ? matchingPages.slice(start, start + pageSize).map((p) => (
                        <tr key={p.id}>
                          <td>{p.label}</td>
                          <td>{p.category}</td>
                          <td>
                            {bundle.source && !bundle.source.loaded
                              ? "Pending checks"
                              : p.flagCount > 0
                                ? `${p.flagCount} need checking`
                                : "No flags"}
                          </td>
                          <td>
                            <span
                              className={`progress-badge ${p.status === "Reviewed" ? "done" : p.status === "Ready to review" ? "ready" : "waiting"}`}
                            >
                              {p.status}
                            </span>
                          </td>
                          <td>{p.model || "—"}</td>
                          <td>
                            {bundle.source && !bundle.source.loaded ? (
                              <span>Unavailable at the moment</span>
                            ) : p.status === "Awaiting transcription" ? (
                              <span>Awaiting transcription</span>
                            ) : p.surveyId ? (
                              <a
                                className="progress-link-button"
                                href={reviewLink(p)}
                              >
                                {p.status === "Reviewed" ? "View" : "Review"}
                                <ArrowRight size={16} />
                              </a>
                            ) : (
                              <button
                                disabled
                                title="This page has no survey assignment"
                              >
                                Review
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    : matchingBundles
                        .slice(start, start + pageSize)
                        .map((b) => {
                          const c = counts(b.pages);
                          // Guard against division by zero and round for the displayed percentage.
                          const percent = c.total
                            ? Math.round((c.reviewed / c.total) * 100)
                            : 0;
                          return (
                            <tr key={b.id}>
                              <td>
                                <button
                                  className="progress-bundle"
                                  onClick={() => openBundle(b.id)}
                                >
                                  {b.name ?? b.id}
                                </button>
                              </td>
                              <td>{c.total}</td>
                              <td>{c.ready}</td>
                              <td>
                                <div className="progress-meter">
                                  <span>
                                    {c.reviewed} / {c.total} reviewed ·{" "}
                                    {percent}%
                                  </span>
                                  <progress
                                    aria-label={`Bundle ${b.id} review progress`}
                                    value={c.reviewed}
                                    max={c.total || 1}
                                  />
                                </div>
                              </td>
                              <td>
                                {b.source && !b.source.loaded ? (
                                  <div>
                                    {b.source.job?.status === "waiting" ||
                                    b.source.job?.status === "running" ? (
                                      <div role="status">
                                        <strong>
                                          {b.source.job.status === "waiting"
                                            ? "Waiting — queued"
                                            : "Running"}
                                        </strong>
                                        <div>
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
                                            <small>
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
                                            <span>Not transcribed</span>{" "}
                                          </>
                                        )}
                                        <button
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
                                        </button>
                                      </>
                                    )}
                                    {b.source.job?.status === "failed" && (
                                      <p className="transcription-failure">
                                        Transcription failed
                                        {b.source.job.error && (
                                          <>
                                            :{" "}
                                            <button
                                              className="transcription-error-link"
                                              onClick={() =>
                                                setErrorDetails({
                                                  bundle: b.name ?? b.id,
                                                  message:
                                                    b.source!.job!.error!,
                                                })
                                              }
                                            >
                                              more details here
                                            </button>
                                          </>
                                        )}
                                      </p>
                                    )}
                                  </div>
                                ) : c.ready ? (
                                  <button onClick={() => openBundle(b.id)}>
                                    Review <ArrowRight size={16} />
                                  </button>
                                ) : c.reviewed === c.total ? (
                                  <button onClick={() => openBundle(b.id)}>
                                    View <ArrowRight size={16} />
                                  </button>
                                ) : (
                                  <button onClick={() => openBundle(b.id)}>
                                    View
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                  {/* Offer a filter reset when no rows match. */}
                  {!totalRows && (
                    <tr>
                      <td colSpan={bundle ? 6 : 5}>
                        <div className="progress-empty">
                          No {bundle ? "pages" : "bundles"} match your filters.
                          <button
                            onClick={() => {
                              setQuery("");
                              setStatus("All");
                              setPageNumber(0);
                            }}
                          >
                            Clear filters
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {/* Show the visible row range and disable navigation at either end. */}
            <footer className="progress-pagination">
              <span>
                Showing {totalRows ? start + 1 : 0}–
                {Math.min(start + pageSize, totalRows)} of {totalRows}{" "}
                {bundle ? "pages" : "bundles"}
              </span>
              <div>
                <button
                  disabled={current === 0}
                  onClick={() => setPageNumber(current - 1)}
                >
                  Previous
                </button>
                <span>
                  Page {current + 1} of {lastPage + 1}
                </span>
                <button
                  disabled={current === lastPage}
                  onClick={() => setPageNumber(current + 1)}
                >
                  Next <ArrowRight size={15} />
                </button>
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
