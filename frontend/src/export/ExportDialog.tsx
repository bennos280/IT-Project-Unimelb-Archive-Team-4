// Displays the export dialog for downloading saved survey data as JSON,
// with validation and success or error messages.

import { useEffect, useRef, useState, type ReactNode } from "react";

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
import { Progress } from "@/components/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { recordWords } from "../progress/backend";

import {
  loadSurveyExport,
  loadBundleExport,
  loadExportBundles,
  startSeriesExport,
  pollSeriesExport,
} from "./exportService";

// Defines the available export scope options shown in the dialog.
type Scope = "series" | "bundle" | "survey" | "current";

// Saves a blob under a file name through a temporary download link.
function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();

  // Release the temporary object URL once the download has started.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

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
 * Downloads a survey, a loaded bundle or a whole series from persisted backend data.
 */

export default function ExportDialog({
  surveyId,
  hasDrafts,
  initialBundleId = "",
  defaultScope = "survey",
  collectionId,
  recordName,
  variant = "default",
}: {
  surveyId: string;
  hasDrafts: boolean;
  initialBundleId?: string;
  defaultScope?: Scope;
  collectionId?: number; // the bundles listed are this collection's
  recordName?: string; // what the collection calls a record
  variant?: "default" | "outline"; // its button: outline beside a screen's main action
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
  // How many of a series' items are done while its zip is prepared.
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const [open, setOpen] = useState(false);
  const [reviewCheck, setReviewCheck] = useState<{
    key: string;
    pending: boolean;
  } | null>(null);
  // A series has no selection, so nothing to check or pick.
  const seriesId = scope === "series" ? collectionId : undefined;
  const selectedId = scope === "series" ? "" : (scope === "survey" ? requestedId : bundleId).trim();
  const selectionKey = `${scope}:${selectedId}`;
  const ready = scope === "series" ? seriesId !== undefined : selectedId !== "";

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
    counts?: { surveys: number; pages: number; pending: number };
  } | null>(null);

  const failureTitle =
    scope === "series"
      ? "The series could not be exported."
      : scope === "survey"
        ? `${words.One} ${requestedId || "(no ID)"} could not be exported.`
        : `Item ${bundleId || "(no ID)"} could not be exported.`;

  // Closes the dialog unless an export is currently being generated.
  function close() {
    if (!busy) setOpen(false);
  }

  // Switches scope and clears any previous result or error.
  function chooseScope(next: string) {
    if (next === "series") {
      setScope("series");
    } else if (next === "current") {
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
    if (busy || !ready) return;
    setBusy(true);
    setFailure("");
    setResult(null);

    try {
      if (seriesId !== undefined) {
        const { id, total } = await startSeriesExport(seriesId);
        setProgress({ done: 0, total });
        for (;;) {
          await new Promise((resolve) => setTimeout(resolve, 1000));
          if (!mounted.current) return;
          const reply = await pollSeriesExport(seriesId, id);
          if (!mounted.current) return;
          if ("blob" in reply) {
            save(reply.blob, reply.filename);
            setResult({ filename: reply.filename });
            return;
          }
          setProgress(reply);
        }
      }
      const id = scope === "survey" ? requestedId.trim() : bundleId;
      // Always read saved values from US8; never export the session's drafts.
      const payload = await (scope === "survey"
        ? loadSurveyExport(id)
        : loadBundleExport(id));
      const pages = payload.surveys.flatMap((record) => record.pages);
      const unassigned = payload.unassignedPages ?? [];

      const filename = `${scope === "survey" ? words.one.replace(/\W+/g, "-") : "bundle"}-${id.replace(/[^a-zA-Z0-9_-]/g, "_")}-export.json`;
      save(
        new Blob([JSON.stringify(payload, null, 2)], {
          type: "application/json",
        }),
        filename,
      );

      // Store export details so the success message can be displayed.
      setResult({
        filename,
        counts: {
          surveys: payload.surveys.length,
          pages: pages.length + unassigned.length,
          pending:
            pages.filter((p) => p.status === "ToBeReviewed").length +
            unassigned.length,
        },
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
      setProgress(null);
    }
  }

  return (
    <>
      {/* Modal containing all export controls and feedback. */}
      <Dialog open={open} onOpenChange={(next) => !busy && setOpen(next)}>
        {/* Opens the export dialog and resets previous messages. The trigger gets focus back on close. */}
        <DialogTrigger asChild>
          <Button
            variant={variant}
            onClick={() => {
              setOpen(true);
              setReviewCheck(null);
              setResult(null);
              setFailure("");
              setRequestedId(surveyId);
              setScope(defaultScope);
              setBundleId(initialBundleId);
              // The item list is only fetched where it is shown; choosing items fetches it.
              if (defaultScope !== "series")
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
                {collectionId !== undefined && (
                  <ScopeOption value="series" title="Whole series">
                    A zip with one JSON file per transcribed item, laid out as
                    on the archive: series, item, then page number. Each page
                    says whether it was reviewed.
                  </ScopeOption>
                )}

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

            {/* How far the series' zip has got. */}
            {progress && (
              <div className="flex flex-col gap-1.5">
                <span role="status" className="text-sm">
                  Prepared {progress.done.toLocaleString()} of {progress.total.toLocaleString()} items
                </span>
                <Progress
                  className="h-2"
                  aria-label="Export progress"
                  value={(progress.done / progress.total) * 100}
                  max={progress.total}
                  aria-valuenow={progress.done}
                />
              </div>
            )}

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
                <AlertTitle>{failureTitle}</AlertTitle>
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
                  {result.counts && (
                    <p>
                      {result.counts.surveys} {result.counts.surveys === 1 ? words.one : words.many} · {result.counts.pages} pages ·{" "}
                      {result.counts.pending} pages awaiting review included.
                    </p>
                  )}
                </AlertDescription>
              </Alert>
            )}

            <p className="text-sm text-muted-foreground">
              Moving to another computer?{" "}
              <a className="text-primary underline-offset-4 hover:underline" href="/api/state" download>Save a PrestCribe file</a> of
              everything here, to open on another computer.
            </p>

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

              <Button type="submit" disabled={busy || !ready}>
                {busy ? "Preparing…" : scope === "series" ? "Export zip" : "Export JSON"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
