// Displays the export dialog for downloading saved survey data as JSON,
// with validation and success or error messages.

import { useRef, useState } from "react";

import { CheckCircle2, Download, X, AlertTriangle } from "lucide-react";

import {
  loadSurveyExport,
  loadBundleExport,
  loadExportBundles,
} from "./exportService";

import "./export.css";

// Defines the available export scope options shown in the dialog.
type Scope = "bundle" | "survey";

/**
 * Displays the export button and modal dialog.
 *
 * Downloads a survey or loaded bundle from persisted backend data.
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
  const [bundleId, setBundleId] = useState("");
  const [bundles, setBundles] = useState<Array<{ id: string; name: string }>>(
    [],
  );
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
   * Requests the export JSON prepared by the backend,
   * and downloads the result as a JSON file.
   */
  async function exportFile() {
    if (busy || !(scope === "survey" ? requestedId.trim() : bundleId)) return;
    setBusy(true);
    setFailure("");
    setResult(null);

    try {
      const id = scope === "survey" ? requestedId.trim() : bundleId;
      // Always read saved values from US8; never export the session's drafts.
      const payload = await (scope === "survey"
        ? loadSurveyExport(id)
        : loadBundleExport(id));
      const pages = payload.surveys.flatMap((record) => record.pages);
      const unassigned = payload.unassignedPages ?? [];

      const filename = `${scope}-${id.replace(/[^a-zA-Z0-9_-]/g, "_")}-export.json`;
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
        pages: pages.length + unassigned.length,
        pending:
          pages.filter((p) => p.status === "ToBeReviewed").length +
          unassigned.length,
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

              {/* Bundle export option. */}
              <label className="export-option">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === "bundle"}
                  onChange={() => {
                    setScope("bundle");
                    void loadExportBundles()
                      .then(setBundles)
                      .catch((e) => setFailure(e.message));
                    setResult(null);
                    setFailure("");
                  }}
                />

                <span>
                  <strong>Export bundle JSON</strong>
                  <small>JSON file containing all surveys in one bundle.</small>
                </span>
              </label>

              {/* Choose a loaded bundle from the database. */}
              {scope === "bundle" && (
                <label className="export-input">
                  Bundle number
                  <select
                    value={bundleId}
                    required
                    onChange={(e) => {
                      setBundleId(e.target.value);
                      setResult(null);
                      setFailure("");
                    }}
                  >
                    <option value="">Choose a loaded bundle</option>
                    {bundles.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} · {b.id}
                      </option>
                    ))}
                  </select>
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
                </label>
              )}
            </fieldset>

            {/* Explain which saved values are exported. */}
            {
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
            }

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
          </div>

          {/* Dialog actions. */}
          <footer className="export-footer">
            <button type="button" onClick={close} disabled={busy}>
              {result ? "Close" : "Cancel"}
            </button>

            <button
              className="export-submit"
              type="submit"
              disabled={
                busy || !(scope === "survey" ? requestedId.trim() : bundleId)
              }
            >
              {busy ? "Preparing…" : "Export JSON"}
            </button>
          </footer>
        </form>
      </dialog>
    </>
  );
}
