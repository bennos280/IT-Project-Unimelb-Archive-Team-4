// Displays the export dialog for downloading saved survey data as JSON,
// with validation and success or error messages.

import { useEffect, useState, type ReactNode } from "react";

import { CheckCircle2, Download, X, AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
  FieldLegend,
  FieldSet,
  FieldTitle,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { recordWords } from "../progress/backend";

import {
  loadSurveyExport,
  loadBundleExport,
  loadExportBundles,
} from "./exportService";

// Defines the available export scope options shown in the dialog.
type Scope = "bundle" | "survey" | "current";

// One selectable export scope: a radio whose label holds its title and help text.
function ScopeOption({
  value,
  title,
  children,
}: {
  value: Scope;
  title: string;
  children: ReactNode;
}) {
  return (
    <FieldLabel htmlFor={`export-scope-${value}`}>
      <Field orientation="horizontal">
        <RadioGroupItem value={value} id={`export-scope-${value}`} />
        <FieldContent>
          <FieldTitle>{title}</FieldTitle>
          <FieldDescription>{children}</FieldDescription>
        </FieldContent>
      </Field>
    </FieldLabel>
  );
}

/**
 * Displays the export button and modal dialog.
 *
 * Downloads a survey or loaded bundle from persisted backend data.
 */

export default function ExportDialog({
  surveyId,
  hasDrafts,
  initialBundleId = "",
  defaultScope = "survey",
  collectionId,
  recordName,
}: {
  surveyId: string;
  hasDrafts: boolean;
  initialBundleId?: string;
  defaultScope?: Scope;
  collectionId?: number; // the bundles listed are this collection's
  recordName?: string; // what the collection calls a record
}) {
  const words = recordWords(recordName);
  // Stores the selected export scope.
  const [scope, setScope] = useState<Scope>(defaultScope);

  // Stores the survey ID entered by the user.
  const [requestedId, setRequestedId] = useState(surveyId);

  // Prevents repeated actions while an export is being prepared.
  const [bundleId, setBundleId] = useState(initialBundleId);
  const [bundles, setBundles] = useState<Array<{ id: string; name: string }>>(
    [],
  );
  const [busy, setBusy] = useState(false);

  const [open, setOpen] = useState(false);
  const [reviewCheck, setReviewCheck] = useState<{
    key: string;
    pending: boolean;
  } | null>(null);
  const selectedId = (scope === "survey" ? requestedId : bundleId).trim();
  const selectionKey = `${scope}:${selectedId}`;

  // Check persisted data for this selection; ignore responses from older selections.
  useEffect(() => {
    if (!open || !selectedId) return;
    let active = true;
    const timer = setTimeout(() => {
      void (
        scope === "survey"
          ? loadSurveyExport(selectedId)
          : loadBundleExport(selectedId)
      )
        .then((payload) => {
          const pending =
            payload.surveys.some(
              (survey) =>
                survey.status !== "Reviewed" ||
                survey.pages.some(
                  (page) =>
                    page.status !== "Reviewed" ||
                    page.fields.some((field) => field.status !== "Reviewed"),
                ),
            ) ||
            (payload.unassignedPages ?? []).some(
              (page) => page.status !== "Reviewed",
            );
          if (active) setReviewCheck({ key: selectionKey, pending });
        })
        .catch(() => {
          if (active) setReviewCheck(null);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [open, scope, selectedId, selectionKey]);

  // Stores any error message produced during the export.
  const [failure, setFailure] = useState("");

  // Stores information about a successfully generated export.
  const [result, setResult] = useState<{
    filename: string;
    surveys: number;
    pages: number;
    pending: number;
  } | null>(null);

  // Closes the dialog unless an export is currently being generated.
  function close() {
    if (!busy) setOpen(false);
  }

  // Switches scope and clears any previous result or error.
  function chooseScope(next: string) {
    if (next === "current") {
      setScope("current");
      setBundleId(initialBundleId);
    } else if (next === "bundle") {
      setScope("bundle");
      void loadExportBundles(collectionId)
        .then(setBundles)
        .catch((e) => setFailure(e.message));
    } else {
      setScope("survey");
    }
    setResult(null);
    setFailure("");
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

      const filename = `${scope === "survey" ? words.one.replace(/\W+/g, "-") : "bundle"}-${id.replace(/[^a-zA-Z0-9_-]/g, "_")}-export.json`;
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
        surveys: payload.surveys.length,
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
          : `Could not read saved ${words.one} data. Try again.`,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* Modal containing all export controls and feedback. */}
      <Dialog open={open} onOpenChange={(next) => !busy && setOpen(next)}>
        {/* Opens the export dialog and resets previous messages. The trigger gets focus back on close. */}
        <DialogTrigger asChild>
          <Button
            onClick={() => {
              setOpen(true);
              setReviewCheck(null);
              setResult(null);
              setFailure("");
              setRequestedId(surveyId);
              setScope(defaultScope);
              setBundleId(initialBundleId);
              void loadExportBundles(collectionId)
                .then(setBundles)
                .catch((error) => setFailure(error.message));
            }}
          >
            <Download /> Export
          </Button>
        </DialogTrigger>
        <DialogContent
          showCloseButton={false}
          className="max-h-[calc(100dvh-2rem)] overflow-y-auto data-[state=open]:animate-none data-[state=closed]:animate-none sm:max-w-lg"
          // Escape is blocked while exporting; clicking the backdrop never closes.
          onEscapeKeyDown={(event) => busy && event.preventDefault()}
          onInteractOutside={(event) => event.preventDefault()}
        >
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="absolute top-2 right-2"
            aria-label="Close export"
            onClick={close}
            disabled={busy}
          >
            <X />
          </Button>
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void exportFile();
            }}
          >
            <DialogHeader>
              <DialogTitle className="text-lg">Export</DialogTitle>
              <DialogDescription>
                Choose what you want to export.
              </DialogDescription>
            </DialogHeader>

            {/* Export scope selection. */}
            <FieldSet disabled={busy}>
              <FieldLegend className="sr-only">Export scope</FieldLegend>
              <RadioGroup
                value={scope}
                onValueChange={chooseScope}
                disabled={busy}
              >
                {initialBundleId && (
                  <ScopeOption value="current" title="Current item">
                    Export all {words.many} and unassigned pages in item{" "}
                    {initialBundleId}.
                  </ScopeOption>
                )}

                <ScopeOption value="bundle" title="Export item JSON">
                  JSON file containing all {words.many} in one item.
                </ScopeOption>

                {/* Choose a loaded bundle from the database. */}
                {scope === "bundle" && (
                  <Field className="pl-9">
                    <FieldLabel htmlFor="export-bundle">
                      Item number
                    </FieldLabel>
                    <NativeSelect
                      id="export-bundle"
                      className="w-full"
                      value={bundleId}
                      required
                      onChange={(e) => {
                        setBundleId(e.target.value);
                        setResult(null);
                        setFailure("");
                      }}
                    >
                      <option value="">Choose a loaded item</option>
                      {bundles.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name} · {b.id}
                        </option>
                      ))}
                    </NativeSelect>
                  </Field>
                )}

                <ScopeOption value="survey" title={`${words.One} ID JSON`}>
                  JSON file containing one {words.one} and its source page labels.
                </ScopeOption>

                {/* Survey ID input used for the currently supported export mode. */}
                {scope === "survey" && (
                  <Field className="pl-9">
                    <FieldLabel htmlFor="export-survey-id">
                      {words.One} ID *
                    </FieldLabel>
                    <Input
                      id="export-survey-id"
                      required
                      value={requestedId}
                      onChange={(event) => {
                        setRequestedId(event.target.value);
                        setResult(null);
                        setFailure("");
                      }}
                      placeholder={`Enter ${words.one} ID`}
                    />
                  </Field>
                )}
              </RadioGroup>
            </FieldSet>

            {/* Only warn when the selected saved data contains unreviewed records. */}
            {reviewCheck?.key === selectionKey && reviewCheck.pending && (
              <Alert role="status">
                <AlertTitle>Contains unreviewed data</AlertTitle>
                <AlertDescription>
                  This contains fields that are still awaiting review. Be aware
                  that unreviewed values may contain transcription errors and
                  have not been verified by a reviewer.
                </AlertDescription>
              </Alert>
            )}
            {hasDrafts && (
              <p className="flex items-start gap-2 text-sm text-muted-foreground">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                Unsaved edits are excluded. Save your pages first to include
                them.
              </p>
            )}

            {/* Display an export failure to the user. */}
            {failure && (
              <Alert variant="destructive" className="wrap-anywhere">
                <AlertTitle>
                  {words.One} {requestedId || "(no ID)"} could not be exported.
                </AlertTitle>
                <AlertDescription>
                  <p>{failure}</p>
                  <p>No export file was created.</p>
                </AlertDescription>
              </Alert>
            )}

            {/* Display details about a successful export. */}
            {result && (
              <Alert role="status" className="wrap-anywhere">
                <CheckCircle2 />
                <AlertTitle>Export file prepared</AlertTitle>
                <AlertDescription>
                  <p>{result.filename}</p>
                  <p>
                    {result.surveys} {result.surveys === 1 ? words.one : words.many} · {result.pages} pages ·{" "}
                    {result.pending} pages awaiting review included.
                  </p>
                </AlertDescription>
              </Alert>
            )}

            {/* Dialog actions. */}
            <DialogFooter className="sm:justify-between">
              <Button
                type="button"
                variant="outline"
                onClick={close}
                disabled={busy}
              >
                {result ? "Close" : "Cancel"}
              </Button>

              <Button
                type="submit"
                disabled={
                  busy || !(scope === "survey" ? requestedId.trim() : bundleId)
                }
              >
                {busy ? "Preparing…" : "Export JSON"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
