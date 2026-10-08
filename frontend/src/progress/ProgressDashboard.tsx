// Bundle overview and page list
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Search, Upload } from "lucide-react";
import ExportDialog from "../export/ExportDialog";
import {
  counts,
  bundleFromSurvey,
  type Bundle,
  type ProgressPage,
} from "./progressData";
import { getSurvey, getReviews } from "../review-screen/api";
import "./progress.css";
const pageSize = 9;

// Shows the bundle overview or the selected bundle’s pages using saved US8 data.
export default function ProgressDashboard() {
  // Null means data has not loaded yet; an empty array means no bundles were returned.
  const [bundles, setBundles] = useState<Bundle[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let latest = 0;
    async function refresh() {
      const request = ++latest;
      try {
        //todo Currently connects survey 216417_1 in bundle 216417; real bundle discovery is still to be added.
        const [survey, saved] = await Promise.all([
          getSurvey("216417_1"),
          getReviews("216417_1"),
        ]);
        if (!active || request !== latest) return;
        // A page counts as reviewed only when every field has a saved review.
        setBundles([bundleFromSurvey(survey, saved.reviews, "216417")]);
        setError("");
      } catch (cause) {
        if (!active || request !== latest) return;
        setError(
          cause instanceof Error ? cause.message : "Could not load progress.",
        );
      }
    }
    void refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    // Remove the focus listener when this effect is replaced or the dashboard closes.
    return () => {
      active = false;
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

  const dialog = useRef<HTMLDialogElement>(null);
  const [transcriptionModel, setTranscriptionModel] = useState("sonnet");
  const [customModel, setCustomModel] = useState("");
  const bundle = (bundles ?? []).find((b) => b.id === bundleId);

  // Summary cards cover the selected bundle or all loaded pages, regardless of filters.
  const totals = counts(
    bundle ? bundle.pages : (bundles ?? []).flatMap((b) => b.pages),
  );
  // Reviewed requires every page; other statuses match bundles with pending pages.
  const matchingBundles = (bundles ?? []).filter(
    (b) =>
      b.id.includes(query.trim()) &&
      (status === "All" ||
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
  // Show a placeholder until transcription is connected; this starts no backend job.
  function openTranscription() {
    dialog.current?.showModal();
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
              {bundle ? `Bundle Number · ${bundle.id}` : "All survey bundles"}
            </h2>
            <p>
              {bundle
                ? `${totals.ready} pages ready to review`
                : `Track review progress across ${(bundles ?? []).length} bundles`}
            </p>
          </div>
          {/* Reuse US12 export and open the import screen. */}
          <div className="progress-actions">
            <ExportDialog surveyId="216417_1" hasDrafts={false} />
            <button
              type="button"
              onClick={() => {
                window.location.href = "/?view=import";
              }}
            >
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
                  "Awaiting transcription",
                  "Ready to review",
                  "Reviewed",
                ].map((s) => (
                  <option key={s} value={s}>
                    Status: {s}
                  </option>
                ))}
              </select>
              {bundle && (
                <button onClick={openTranscription}>Transcribe bundle</button>
              )}
            </div>
            {/* The same table shows bundle summaries or individual page details. */}
            <div className="progress-table-wrap">
              <table className="progress-table">
                <thead>
                  <tr>
                    {(bundle
                      ? ["Page", "Page category", "Flags", "Status", "Action"]
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
                            {p.flagCount > 0
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
                          <td>
                            {p.status === "Awaiting transcription" ? (
                              <button onClick={openTranscription}>
                                Transcribe
                              </button>
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
                                title="This illustrative page is not connected to a survey"
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
                                  {b.id}
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
                                {c.ready ? (
                                  <button onClick={() => openBundle(b.id)}>
                                    Review <ArrowRight size={16} />
                                  </button>
                                ) : c.reviewed === c.total ? (
                                  <button onClick={() => openBundle(b.id)}>
                                    View <ArrowRight size={16} />
                                  </button>
                                ) : (
                                  <button onClick={openTranscription}>
                                    Transcribe
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                  {/* Offer a filter reset when no rows match. */}
                  {!totalRows && (
                    <tr>
                      <td colSpan={5}>
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
      <dialog
        className="progress-dialog"
        ref={dialog}
        aria-labelledby="progress-dialog-title"
      >
        <h2 id="progress-dialog-title">Transcribe scans</h2>
        <p>Choose the model to transcribe your scans.</p>
        <label className="transcription-model">
          Transcription model
          <select
            autoFocus
            value={transcriptionModel}
            onChange={(event) => setTranscriptionModel(event.target.value)}
          >
            <option value="sonnet">Claude Sonnet</option>
            <option value="opus">Claude Opus</option>
            <option value="haiku">Claude Haiku</option>
            <option value="custom">Custom model</option>
          </select>
        </label>
        {transcriptionModel === "custom" && (
          <label className="transcription-model">
            Model name
            <input
              value={customModel}
              placeholder="Enter the configured model name"
              onChange={(event) => setCustomModel(event.target.value)}
            />
          </label>
        )}
        {/* Pass the selected model to the job endpoint when US8 provides it. */}
        <p id="transcription-availability">
          Starting transcription is not available yet.
        </p>
        <div className="progress-dialog-actions">
          <button onClick={() => dialog.current?.close()}>Cancel</button>
          <button disabled aria-describedby="transcription-availability">
            Start transcription
          </button>
        </div>
      </dialog>
    </div>
  );
}
