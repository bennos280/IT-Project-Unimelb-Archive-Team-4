// Displays the export dialog for downloading saved survey data as JSON,
// with validation and success or error messages.

import { useRef, useState } from "react";

import { CheckCircle2, Download, X, AlertTriangle } from "lucide-react";

import { loadSurveyExport } from "./exportService";

import "./export.css";

// Defines the available export scope options shown in the dialog.
type Scope = "all" | "bundle" | "survey";

/**
 * Displays the export button and modal dialog.
 *
 * Currently only single-survey JSON exports are supported because the
 * backend currently provides individual survey endpoints.
 */

export default function ExportDialog({
  surveyId,
  hasDrafts,
}: {
  surveyId: string;
  hasDrafts: boolean;
}) {
  // Reference to the native HTML dialog so it can be opened and closed.
  const dialog = useRef<HTMLDialogElement>(null);

  // Stores the selected export scope.
  const [scope, setScope] = useState<Scope>("survey");

  // Stores the survey ID entered by the user.
  const [requestedId, setRequestedId] = useState(surveyId);

  // Prevents repeated actions while an export is being prepared.
  const [busy, setBusy] = useState(false);

  // Stores any error message produced during the export.
  const [failure, setFailure] = useState("");

  // Stores information about a successfully generated export.
  const [result, setResult] = useState<{
    filename: string;
    pages: number;
    pending: number;
  } | null>(null);

  // Closes the dialog unless an export is currently being generated.
  function close() {
    if (!busy) dialog.current?.close();
  }

  /**
   * Loads the survey and its saved reviews, builds the export object,
   * and downloads the result as a JSON file.
   */
  async function exportFile() {
    if (busy || scope !== "survey" || !requestedId.trim()) return;
    setBusy(true);
    setFailure("");
    setResult(null);

    try {
      const id = requestedId.trim();
      // Always read saved values from US8; never export the session's drafts.
      const payload = await loadSurveyExport(id);
      const record = payload.surveys[0];

      const filename = `survey-${id.replace(/[^a-zA-Z0-9_-]/g, "_")}-export.json`;
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(payload, null, 2)], {
          type: "application/json",
        }),
      );

      // Create and trigger a temporary download link.
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();

      // Release the temporary object URL once the download has started.
      setTimeout(() => URL.revokeObjectURL(url), 1000);

      // Store export details so the success message can be displayed.
      setResult({
        filename,
        pages: record.pages.length,
        pending: record.pages.filter((p) => p.status === "ToBeReviewed").length,
      });
    } catch (error) {
      // Display a useful error message if loading or exporting fails.
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
      {/* Opens the export dialog and resets previous messages. */}
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

      {/* Native modal containing all export controls and feedback. */}
      <dialog
        ref={dialog}
        className="export-dialog"
        aria-labelledby="export-title"
        aria-describedby="export-description"
        onCancel={(event) => {
          // Prevent the Escape key from closing the dialog while exporting.
          if (busy) {
            event.preventDefault();
          }
        }}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void exportFile();
          }}
        >
          <div className="export-body">
            {/* Dialog heading and close control. */}
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

            {/* Export scope selection. */}
            <fieldset disabled={busy} className="export-choices">
              <legend className="export-sr">Export scope</legend>

              {/* Full archive export option. Not yet implemented. */}
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

              {/* Bundle export option. Not yet implemented. */}
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

              {/* Bundle number will become available after database integration. */}
              {scope === "bundle" && (
                <label className="export-input">
                  Bundle number
                  <input
                    disabled
                    placeholder="Requires bundle export support"
                  />
                </label>
              )}

              {/* Single-survey export option. */}
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

              {/* Survey ID input used for the currently supported export mode. */}
              {scope === "survey" && (
                <label className="export-input">
                  Survey ID *
                  <input
                    required
                    value={requestedId}
                    onChange={(event) => {
                      setRequestedId(event.target.value);
                      setResult(null);
                      setFailure("");
                    }}
                    placeholder="Enter survey ID"
                  />
                  <small>
                    Enter the ID of a survey stored in US8. Bundle export is not
                    available yet.
                  </small>
                </label>
              )}
            </fieldset>

            {/* Explain why unsupported export scopes cannot yet be used. */}
            {scope !== "survey" ? (
              <p className="export-notice" role="status">
                US8 needs an export endpoint for{" "}
                {scope === "all" ? "the full archive" : "a bundle"}. Individual
                survey export is available.
              </p>
            ) : (
              /* Explain how single-survey export values are chosen. */
              <div className="export-policy">
                <span>JSON · Latest saved values</span>

                <p>
                  Includes fields still awaiting review, with a status. Blank
                  values, “/” and “[?]” are preserved.
                </p>

                {/* Warn that unsaved review edits are excluded. */}
                {hasDrafts && (
                  <p className="export-draft">
                    <AlertTriangle size={15} />
                    Unsaved edits are excluded. Save your pages first to include
                    them.
                  </p>
                )}
              </div>
            )}

            {/* Display an export failure to the user. */}
            {failure && (
              <div className="export-error" role="alert">
                <strong>
                  Survey {requestedId || "(no ID)"} could not be exported.
                </strong>

                <p>{failure}</p>
                <p>No export file was created.</p>
              </div>
            )}

            {/* Display details about a successful export. */}
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

            {/* Notes that the current export behaviour is still subject to stakeholder confirmation. */}
            <p className="export-footnote">
              JSON and final values only are working defaults, pending Archives’
              confirmation.
            </p>
          </div>

          {/* Dialog actions. */}
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
