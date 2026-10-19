import ExportDialog from "../export/ExportDialog";
import PageActions from "./PageActions";
// Main review screen: field table on the left, scan viewer on the right.

import { useState } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Search,
  TriangleAlert,
  CircleCheck,
  Pencil,
} from "lucide-react";
import { cn } from "cn";
import ImageViewer from "./ImageViewer";
import { itemTitle, recordWords } from "../progress/backend";
import type { useReviewSession } from "./useReviewSession";
import { getPageName, isTextPage } from "./model";
import type { Flag } from "./model";
import { flagCategories, flagLabels } from "./flags";
import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

// Flag kind and the reason the extractor gave for it.
function FlagReason({ flag }: { flag: Flag }) {
  return (
    <div className="mt-2 text-xs leading-relaxed text-muted-foreground">
      <strong className="font-medium text-foreground">
        {flagLabels[flag.kind]}
      </strong>
      <p className="my-1">{flag.reason}</p>
    </div>
  );
}

const cell = "align-top whitespace-normal break-words";

// Render extracted fields and the scan, wiring reviewer controls and dialogs to session actions.
export default function ReviewScreen({
  session,
}: {
  session: ReturnType<typeof useReviewSession>;
}) {
  const [transcribeToolbar, setTranscribeToolbar] = useState<HTMLDivElement | null>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<
    Record<string, boolean>
  >({});
  const [creatingReviewer, setCreatingReviewer] = useState(false);
  const [statusFilter, setStatusFilter] = useState("all");
  const [selection, setSelection] = useState<{
    pageId: string;
    fieldId: string;
    token: number;
  } | null>(null);
  const {
    survey,
    error,
    setAttempt,
    index,
    query,
    setQuery,
    filter,
    setFilter,
    page,
    pageReviews,
    flagsLeft,
    reviewer,
    setReviewer,
    reviewers,
    newName,
    setNewName,
    adding,
    setAdding,
    editing,
    setEditing,
    draft,
    setDraft,
    message,
    saving,
    beginEdit,
    applyEdit,
    addReviewer,
    reviewAll,
    savePage,
    navigate,
    leaving,
    stayOnPage,
    saveAndContinue,
    discardAndContinue,
    visible: matchingFields,
  } = session;
  // Filter by the same saved/draft status shown in each row.
  const visible = matchingFields.filter((field) => {
    const review = pageReviews[field.id];
    const status = review
      ? review.savedAt
        ? "Reviewed"
        : "Unsaved"
      : field.value === null || field.value === ""
        ? "Blank"
        : "Transcribed";
    return statusFilter === "all" || statusFilter === status;
  });
  const groups = [...new Set(visible.map((field) => field.group))];
  const textPage = !!page && isTextPage(page);
  // The dashboard names an item by its name; the bundle id is accepted too when the survey doesn't say.
  const bundleLabel = survey?.item?.name || survey?.bundleId || "";
  const words = recordWords(survey?.recordName);
  return (
    <>
      <AppHeader
        crumbs={[
          { label: "Series", href: "/" },
          ...(survey?.collectionId ? [{ label: survey.title, href: `/?collection=${survey.collectionId}` }] : []),
          ...(survey?.bundleId
            ? [{ label: itemTitle(bundleLabel, survey.item?.archive), href: `/?collection=${survey.collectionId ?? 1}&bundle=${encodeURIComponent(bundleLabel)}` }]
            : []),
          { label: survey ? `${words.One} ${session.surveyId}` : session.surveyId || words.One },
        ]}
      />
      <main>
        <h1 className="sr-only">Review {words.one}</h1>
        {!session.surveyId ? (
          <div className="p-8 text-center text-muted-foreground" role="status">
            Select {words.a} to review.
          </div>
        ) : error ? (
          <Alert variant="destructive" className="m-6 w-auto">
            <AlertDescription className="flex items-center gap-4">
              {error}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAttempt((a) => a + 1)}
              >
                Try again
              </Button>
            </AlertDescription>
          </Alert>
        ) : !page || !survey ? (
          <div
            className="flex items-center justify-center gap-2 p-8 text-muted-foreground"
            role="status"
          >
            <Spinner aria-hidden="true" />
            Loading pages and source images…
          </div>
        ) : (
          <div className="grid grid-cols-1 md:h-[calc(100dvh-5.6rem)] md:grid-cols-[46%_54%]">
            <section className="flex h-[560px] min-w-0 flex-col overflow-hidden border-b px-4 pt-4 md:h-auto md:border-r md:border-b-0 md:px-6">
              <div
                className="flex flex-wrap items-center gap-2"
                data-page-id={page.id}
              >
                <h2 className="min-w-0 flex-1 basis-full text-base font-semibold min-[1150px]:basis-auto">
                  {page.id} · {getPageName(page)}{" "}
                </h2>
                <Badge variant="outline">
                  {`${
                    page.fields.length
                      ? Math.round(
                          (Object.keys(pageReviews).length /
                            page.fields.length) *
                            100,
                        )
                      : 0
                  }% reviewed`}
                </Badge>
                <PageActions key={page.id} session={session} toolbar={transcribeToolbar} />
                <Badge variant="outline">
                  {flagsLeft ? `${flagsLeft} need checking` : "No flags"}
                </Badge>
                {/* TODO:support page-category changes
                <button disabled title="Change page category not implemented yet">
                  Change page category
                </button>
                */}
              </div>
              <div className="mt-4 flex items-center">
                <div className="relative ml-auto flex w-full max-w-48 items-center">
                  <Search
                    className="pointer-events-none absolute left-2.5 size-4 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <Input
                    className="pl-8"
                    aria-label="Search fields"
                    placeholder="Search fields…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
              </div>
              <div className="mt-3 min-h-0 flex-1 overflow-auto" key={page.id}>
                {!visible.length ? (
                  <div className="p-8 text-center text-muted-foreground">
                    No fields match your filters.
                    <Button
                      variant="outline"
                      className="m-4"
                      onClick={() => {
                        setQuery("");
                        setFilter("all");
                        setStatusFilter("all");
                      }}
                    >
                      Clear filters
                    </Button>
                  </div>
                ) : (
                  <table className="w-full table-fixed text-xs">
                    <TableHeader className="sticky top-0 z-30 bg-background">
                      <TableRow className="hover:bg-transparent">
                        <TableHead
                          className={cn(
                            "h-9 px-2 text-xs font-normal text-muted-foreground",
                            textPage ? "w-[13%]" : "w-[32%]",
                          )}
                        >
                          Sub-field
                        </TableHead>
                        <TableHead
                          className={cn(
                            "h-9 px-2 text-xs font-normal text-muted-foreground",
                            textPage ? "w-[56%]" : "w-[23%]",
                          )}
                        >
                          Value
                        </TableHead>
                        <TableHead
                          className={cn(
                            "h-9 px-2 text-xs font-normal",
                            textPage ? "w-[12%]" : "w-[21%]",
                          )}
                        >
                          <NativeSelect
                            size="sm"
                            className="w-full"
                            aria-label="Filter fields"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                          >
                            <NativeSelectOption value="all">
                              Flag
                            </NativeSelectOption>
                            <NativeSelectOption value="flagged">
                              All flagged fields
                            </NativeSelectOption>
                            {Object.entries(flagCategories).map(
                              ([value, label]) => (
                                <NativeSelectOption key={value} value={value}>
                                  {label}
                                </NativeSelectOption>
                              ),
                            )}
                          </NativeSelect>
                        </TableHead>
                        <TableHead
                          className={cn(
                            "h-9 px-2 text-xs font-normal",
                            textPage ? "w-[19%]" : "w-[24%]",
                          )}
                        >
                          <NativeSelect
                            size="sm"
                            className="w-full"
                            aria-label="Filter by review status"
                            value={statusFilter}
                            onChange={(event) =>
                              setStatusFilter(event.target.value)
                            }
                          >
                            <NativeSelectOption value="all">
                              Status
                            </NativeSelectOption>
                            {[
                              "Reviewed",
                              "Unsaved",
                              "Blank",
                              "Transcribed",
                            ].map((status) => (
                              <NativeSelectOption key={status} value={status}>
                                {status}
                              </NativeSelectOption>
                            ))}
                          </NativeSelect>
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    {groups.map((group) => {
                      const groupKey = JSON.stringify([
                        survey.id,
                        page.id,
                        group,
                      ]);
                      const collapsed = collapsedGroups[groupKey];
                      return (
                        <TableBody key={group}>
                          <TableRow className="hover:bg-transparent">
                            <TableHead
                              colSpan={4}
                              className="sticky top-9 z-20 h-auto bg-muted p-0"
                            >
                              <Button
                                variant="ghost"
                                className="h-auto w-full justify-start rounded-none px-2 py-2 text-sm font-semibold"
                                aria-expanded={!collapsed}
                                onClick={() =>
                                  setCollapsedGroups((current) => ({
                                    ...current,
                                    [groupKey]: !current[groupKey],
                                  }))
                                }
                              >
                                {collapsed ? (
                                  <ChevronRight aria-hidden="true" />
                                ) : (
                                  <ChevronDown aria-hidden="true" />
                                )}
                                {group}
                              </Button>
                            </TableHead>
                          </TableRow>
                          {!collapsed &&
                            visible
                              .filter((f) => f.group === group)
                              .map((field) => {
                                const flags = page.flags.filter(
                                  (f) => f.fieldId === field.id,
                                );
                                const checked = !!pageReviews[field.id];
                                const locate = () =>
                                  setSelection({
                                    pageId: page.id,
                                    fieldId: field.id,
                                    token: Date.now(),
                                  });
                                return (
                                  <TableRow
                                    key={field.id}
                                    className="cursor-pointer"
                                    data-state={
                                      selection?.pageId === page.id &&
                                      selection.fieldId === field.id
                                        ? "selected"
                                        : undefined
                                    }
                                    onClick={locate}
                                  >
                                    <TableCell
                                      className={cn(
                                        cell,
                                        textPage
                                          ? "pl-2"
                                          : "pl-5 max-[1150px]:pl-2",
                                      )}
                                    >
                                      <Button
                                        variant="link"
                                        className="h-auto justify-start p-0 text-left text-xs font-normal whitespace-normal text-muted-foreground hover:underline max-md:text-[11px]"
                                        aria-label={`Locate ${field.group}: ${field.label} in image`}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          locate();
                                        }}
                                      >
                                        {field.label}
                                      </Button>
                                    </TableCell>
                                    <TableCell className={cell}>
                                      <div className="flex items-start justify-between gap-1.5">
                                        <div className="min-w-0">
                                          <span
                                            className={cn(
                                              "whitespace-pre-wrap break-words",
                                              textPage &&
                                                "min-h-[260px] text-sm leading-7",
                                            )}
                                          >
                                            {(pageReviews[field.id]
                                              ? pageReviews[field.id].value
                                              : field.value) || "–"}
                                          </span>
                                          {(field.areaLabel || field.location) && (
                                            <p className="mt-0.5 text-xs text-muted-foreground">
                                              {[field.areaLabel, field.location]
                                                .filter(Boolean)
                                                .join(" · ")}
                                            </p>
                                          )}
                                        </div>
                                        <Button
                                          variant="ghost"
                                          size="icon-xs"
                                          className="shrink-0"
                                          disabled={saving}
                                          onClick={() => beginEdit(field)}
                                          aria-label={`Edit ${field.label}`}
                                          title="Edit or review this field"
                                        >
                                          <Pencil />
                                        </Button>
                                      </div>
                                    </TableCell>
                                    <TableCell className={cell}>
                                      {flags.length ? (
                                        <Collapsible className="rounded-md data-[state=open]:bg-muted data-[state=open]:p-1.5">
                                          <CollapsibleTrigger asChild>
                                            <Button
                                              variant="ghost"
                                              size="xs"
                                              className="h-auto justify-start gap-1.5 p-0 text-left text-[11px] leading-tight font-normal whitespace-normal hover:bg-transparent"
                                            >
                                              {checked ? (
                                                <CircleCheck />
                                              ) : (
                                                <TriangleAlert className="text-destructive" />
                                              )}
                                              <span>
                                                {checked
                                                  ? "Checked"
                                                  : [
                                                      ...new Set(
                                                        flags.map(
                                                          (flag) =>
                                                            flagLabels[
                                                              flag.kind
                                                            ],
                                                        ),
                                                      ),
                                                    ].join(", ")}
                                              </span>
                                            </Button>
                                          </CollapsibleTrigger>
                                          <CollapsibleContent>
                                            {flags.map((flag) => (
                                              <FlagReason
                                                key={flag.id}
                                                flag={flag}
                                              />
                                            ))}
                                          </CollapsibleContent>
                                        </Collapsible>
                                      ) : (
                                        "—"
                                      )}
                                    </TableCell>
                                    <TableCell className={cell}>
                                      <Badge
                                        variant={
                                          pageReviews[field.id]?.savedAt
                                            ? "secondary"
                                            : "outline"
                                        }
                                        className="h-auto py-0.5 text-left whitespace-normal break-words"
                                      >
                                        {pageReviews[field.id]
                                          ? `${pageReviews[field.id].savedAt ? "Reviewed" : "Unsaved"} by: ${pageReviews[field.id].reviewer}`
                                          : field.value === null ||
                                              field.value === ""
                                            ? "Blank"
                                            : "Transcribed"}
                                      </Badge>
                                    </TableCell>
                                  </TableRow>
                                );
                              })}
                        </TableBody>
                      );
                    })}
                  </table>
                )}
              </div>
              <div className="border-t py-2.5 text-[10px] text-muted-foreground">
                {visible.length} of {page.fields.length} fields
              </div>
            </section>
            <section className="flex h-[650px] min-h-0 min-w-0 flex-col px-4 py-4 md:h-auto md:pr-5 md:pl-6">
              <div className="mb-2 flex items-start justify-between gap-4">
                <div>
                  <h2 className="mb-1 text-base font-semibold">
                    Transcript Review
                  </h2>
                  <nav
                    className="flex items-center gap-3 text-sm"
                    aria-label={`${words.One} pages`}
                  >
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Previous page"
                      disabled={saving || index === 0}
                      onClick={() => navigate(index - 1)}
                    >
                      <ChevronLeft />
                    </Button>
                    <span>
                      Page {index + 1} of {survey.pages.length}
                    </span>
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Next page"
                      disabled={saving || index === survey.pages.length - 1}
                      onClick={() => navigate(index + 1)}
                    >
                      <ChevronRight />
                    </Button>
                  </nav>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex items-center" ref={setTranscribeToolbar} />
                  <ExportDialog
                    surveyId={survey.id}
                    initialBundleId={survey.bundleId}
                    collectionId={survey.collectionId}
                    recordName={survey.recordName}
                    hasDrafts={Object.values(session.reviews).some((fields) =>
                      Object.values(fields).some((review) => !review.savedAt),
                    )}
                  />
                </div>
              </div>
              <ImageViewer
                key={page.id}
                page={page}
                selection={selection?.pageId === page.id ? selection : null}
              />
              <div className="mt-2.5 flex flex-wrap items-end justify-end gap-2">
                <Field className="w-auto flex-1 md:w-[250px] md:flex-none">
                  <FieldLabel htmlFor="reviewer-name" className="text-xs">
                    Reviewer name *
                  </FieldLabel>
                  <NativeSelect
                    id="reviewer-name"
                    aria-label="Reviewer name"
                    value={reviewer}
                    onChange={(e) => {
                      if (e.target.value === "__add__") {
                        setAdding(true);
                      } else setReviewer(e.target.value);
                    }}
                  >
                    <NativeSelectOption value="">
                      Select reviewer
                    </NativeSelectOption>
                    {reviewers.map((person) => (
                      <NativeSelectOption key={person.id} value={person.name}>
                        {person.name}
                      </NativeSelectOption>
                    ))}
                    <NativeSelectOption value="__add__">
                      + Add reviewer…
                    </NativeSelectOption>
                  </NativeSelect>
                </Field>
                <Button variant="outline" onClick={() => setAdding((a) => !a)}>
                  Add reviewer
                </Button>
                <Button
                  variant="outline"
                  disabled={saving || !reviewer || !page.fields.length}
                  onClick={reviewAll}
                >
                  Mark all fields as reviewed
                </Button>
                <Button
                  disabled={
                    saving ||
                    !reviewer ||
                    !Object.values(pageReviews).some((e) => !e.savedAt)
                  }
                  onClick={savePage}
                >
                  {saving ? "Saving…" : "Save Page Transcript"}
                </Button>
              </div>
              {adding && !editing && (
                <form
                  className="mt-2 flex justify-end gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    addReviewer();
                  }}
                >
                  <Input
                    autoFocus
                    className="max-w-56 min-w-0"
                    aria-label="New reviewer name"
                    placeholder="Enter reviewer name"
                    maxLength={80}
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                  <Button disabled={!newName.trim()} type="submit">
                    Add
                  </Button>
                  <Button
                    variant="outline"
                    type="button"
                    onClick={() => setAdding(false)}
                  >
                    Cancel
                  </Button>
                </form>
              )}
              <p
                className="mt-1.5 text-right text-xs leading-snug text-muted-foreground"
                role="status"
              >
                {message ||
                  "Save page transcript saves your reviews. Select a reviewer before applying an edit."}
              </p>
            </section>
          </div>
        )}
      </main>
      <Dialog
        open={leaving}
        onOpenChange={(open) => {
          if (!open) stayOnPage();
        }}
      >
        <DialogContent
          showCloseButton={false}
          className="sm:max-w-xl"
          onInteractOutside={(event) => event.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle>Save your reviews before leaving?</DialogTitle>
            <DialogDescription>
              This page has unsaved reviews. Save them or discard them before
              continuing.
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Discarding restores the last saved values. Previously saved reviews
            are kept.
          </p>
          <DialogFooter>
            <Button
              autoFocus
              variant="outline"
              disabled={saving}
              onClick={stayOnPage}
            >
              Stay here
            </Button>
            <Button
              variant="destructive"
              disabled={saving}
              onClick={discardAndContinue}
            >
              Discard reviews and continue
            </Button>
            <Button disabled={saving || !reviewer} onClick={saveAndContinue}>
              {saving ? "Saving…" : "Save and continue"}
            </Button>
          </DialogFooter>
          <p role="status">{message}</p>
        </DialogContent>
      </Dialog>
      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      >
        <DialogContent
          showCloseButton={false}
          className="max-h-[calc(100dvh-2rem)] overflow-y-auto data-[state=closed]:animate-none sm:max-w-lg"
          onInteractOutside={(event) => event.preventDefault()}
        >
          <form
            className="grid gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!adding && !creatingReviewer) applyEdit();
            }}
          >
            <DialogHeader>
              <DialogTitle>Edit field</DialogTitle>
            </DialogHeader>
            {/* Explain each flag on the selected field before the reviewer edits it. */}
            {page?.flags
              .filter((flag) => flag.fieldId === editing?.id)
              .map((flag) => (
                <FlagReason key={flag.id} flag={flag} />
              ))}
            <DialogDescription>
              {page && getPageName(page)} · {editing?.label}{" "}
            </DialogDescription>
            <Field>
              <FieldLabel>Extracted value</FieldLabel>
              <div className="max-h-30 overflow-auto rounded-md bg-muted p-2.5 break-words whitespace-pre-wrap">
                {editing?.value || "Blank"}
              </div>
            </Field>
            <Field>
              <FieldLabel htmlFor="field-value">Reviewed value</FieldLabel>
              <Textarea
                autoFocus
                id="field-value"
                rows={page && isTextPage(page) ? 10 : 4}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
              <FieldDescription>
                Leave empty to record a blank value. Once applied, this
                field&apos;s flags show as checked.
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-reviewer">Reviewer *</FieldLabel>
              <NativeSelect
                id="edit-reviewer"
                value={adding ? "__add__" : reviewer}
                disabled={creatingReviewer}
                onChange={(e) => {
                  if (e.target.value === "__add__") setAdding(true);
                  else {
                    setAdding(false);
                    setReviewer(e.target.value);
                  }
                }}
              >
                <NativeSelectOption value="">
                  Select reviewer
                </NativeSelectOption>
                {reviewers.map((person) => (
                  <NativeSelectOption key={person.id} value={person.name}>
                    {person.name}
                  </NativeSelectOption>
                ))}
                <NativeSelectOption value="__add__">
                  + Add reviewer…
                </NativeSelectOption>
              </NativeSelect>
            </Field>
            {adding && (
              <div className="flex gap-2">
                <Input
                  autoFocus
                  className="min-w-0"
                  aria-label="New reviewer name"
                  placeholder="Enter reviewer name"
                  maxLength={80}
                  value={newName}
                  disabled={creatingReviewer}
                  onChange={(event) => setNewName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.preventDefault();
                  }}
                />
                <Button
                  type="button"
                  disabled={creatingReviewer || !newName.trim()}
                  onClick={async () => {
                    setCreatingReviewer(true);
                    try {
                      await addReviewer();
                    } finally {
                      setCreatingReviewer(false);
                    }
                  }}
                >
                  {creatingReviewer ? "Adding…" : "Add reviewer"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={creatingReviewer}
                  onClick={() => setAdding(false)}
                >
                  Cancel adding
                </Button>
              </div>
            )}
            <p role="status">{message}</p>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditing(null)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!reviewer || adding || creatingReviewer}
              >
                Apply review
              </Button>
            </DialogFooter>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Applying a review creates an unsaved change. Save the page to
              store it permanently.
            </p>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
