// Displays the export dialog for downloading saved survey data as JSON, with validation and success or error messages.
import { useRef, useState } from "react";
import { CheckCircle2, Download, X, AlertTriangle } from "lucide-react";
import { getReviews, getSurvey } from "../review-screen/api";
import { buildSurveyExport } from "./exportData";
import "./export.css";

type Scope = "all" | "bundle" | "survey";
export default function ExportDialog({
  surveyId,
  hasDrafts,
}: {
  surveyId: string;
  hasDrafts: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [scope, setScope] = useState<Scope>("survey");
  const [requestedId, setRequestedId] = useState(surveyId);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [result, setResult] = useState<{
    filename: string;
    pages: number;
    pending: number;
  } | null>(null);
  function close() {
    if (!busy) dialog.current?.close();
  }
  async function exportFile() {
    if (busy || scope !== "survey" || !requestedId.trim()) return;
    setBusy(true);
    setFailure("");
    setResult(null);
    try {
      const id = requestedId.trim();
      if (id !== surveyId)
        throw new Error(
          "This preview only has the currently open survey. Open the survey you want to export first.",
        );
      const [survey, saved] = await Promise.all([
        getSurvey(id),
        getReviews(id),
      ]);
      const record = buildSurveyExport(survey, saved.reviews);
      const payload = {
        schemaVersion: "1.0",
        exportedAt: new Date().toISOString(),
        scope: "survey",
        format: "JSON",
        valuePolicy: "latest-saved",
        source: "local-preview",
        completeArchiveExport: false,
        limitations: [
          "Only the open survey is available. Bundle membership, ungrouped/other pages and annotations are not supplied by the current data adapter.",
        ],
        surveys: [record],
        failures: [],
      };
      const filename = `survey-${id.replace(/[^a-zA-Z0-9_-]/g, "_")}-export.json`;
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(payload, null, 2)], {
          type: "application/json",
        }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setResult({
        filename,
        pages: record.pages.length,
        pending: record.pages.filter((p) => p.status === "ToBeReviewed").length,
      });
    } catch (error) {
      setFailure(
        error instanceof Error
          ? error.message
          : "Could not read saved survey data. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        onClick={() => {
          setResult(null);
          setFailure("");
          setRequestedId(surveyId);
          dialog.current?.showModal();
        }}
      >
        <Download size={16} /> Export
      </button>
      <dialog
        ref={dialog}
        className="export-dialog"
        aria-labelledby="export-title"
        aria-describedby="export-description"
        onCancel={(e) => {
          if (busy) e.preventDefault();
        }}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void exportFile();
          }}
        >
          <div className="export-body">
            <div className="export-heading">
              <h2 id="export-title">Export</h2>
              <button
                type="button"
                className="export-close"
                aria-label="Close export"
                onClick={close}
                disabled={busy}
              >
                <X size={22} />
              </button>
            </div>
            <p id="export-description">Choose what you want to export.</p>
            <fieldset disabled={busy} className="export-choices">
              <legend className="export-sr">Export scope</legend>
              <label className="export-option">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === "all"}
                  onChange={() => {
                    setScope("all");
                    setResult(null);
                    setFailure("");
                  }}
                />
                <span>
                  <strong>Export all</strong>
                  <small>Export every survey and incomplete record.</small>
                </span>
              </label>
              <label className="export-option">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === "bundle"}
                  onChange={() => {
                    setScope("bundle");
                    setResult(null);
                    setFailure("");
                  }}
                />
                <span>
                  <strong>Export bundle JSON</strong>
                  <small>JSON file containing all surveys in one bundle.</small>
                </span>
              </label>
              {scope === "bundle" && (
                <label className="export-input">
                  Bundle number
                  <input
                    disabled
                    placeholder="Available after database connection"
                  />
                </label>
              )}
              <label className="export-option">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === "survey"}
                  onChange={() => {
                    setScope("survey");
                    setResult(null);
                    setFailure("");
                  }}
                />
                <span>
                  <strong>Survey ID JSON</strong>
                  <small>
                    JSON file containing one survey and its source page labels.
                  </small>
                </span>
              </label>
              {scope === "survey" && (
                <label className="export-input">
                  Survey ID *
                  <input
                    required
                    value={requestedId}
                    onChange={(e) => {
                      setRequestedId(e.target.value);
                      setResult(null);
                      setFailure("");
                    }}
                    placeholder="Enter survey ID"
                  />
                  <small>
                    Currently available: {surveyId}. Bundle membership is not
                    available yet.
                  </small>
                </label>
              )}
            </fieldset>
            {scope !== "survey" ? (
              <p className="export-notice" role="status">
                Connect the database to export{" "}
                {scope === "all" ? "the full archive" : "a bundle"}. This
                preview only loads one survey.
              </p>
            ) : (
              <div className="export-policy">
                <span>JSON · Latest saved values</span>
                <p>
                  Includes fields still awaiting review, with a status. Blank
                  values, “/” and “[?]” are preserved.
                </p>
                {hasDrafts && (
                  <p className="export-draft">
                    <AlertTriangle size={15} /> Unsaved edits are excluded. Save
                    your pages first to include them.
                  </p>
                )}
              </div>
            )}
            {failure && (
              <div className="export-error" role="alert">
                <strong>
                  Survey {requestedId || "(no ID)"} could not be exported.
                </strong>
                <p>{failure}</p>
                <p>No export file was created.</p>
              </div>
            )}
            {result && (
              <div className="export-success" role="status">
                <CheckCircle2 size={19} />
                <div>
                  <strong>Export file prepared</strong>
                  <p>{result.filename}</p>
                  <p>
                    1 survey · {result.pages} pages · {result.pending} pages
                    awaiting review included.
                  </p>
                </div>
              </div>
            )}
            <p className="export-footnote">
              JSON and final values only are working defaults, pending Archives’
              confirmation.
            </p>
          </div>
          <footer className="export-footer">
            <button type="button" onClick={close} disabled={busy}>
              {result ? "Close" : "Cancel"}
            </button>
            <button
              className="export-submit"
              type="submit"
              disabled={busy || scope !== "survey" || !requestedId.trim()}
            >
              {busy ? "Preparing…" : "Export JSON"}
            </button>
          </footer>
        </form>
      </dialog>
    </>
  );
}
