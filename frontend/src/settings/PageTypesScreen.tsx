import { useCallback, useEffect, useId, useState, type ReactNode } from "react";

import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldContent, FieldDescription, FieldGroup, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { backendRequest } from "../progress/backend";

type PageType = { name: string; label: string; builtIn: boolean; unknown: boolean; startsRecord: boolean; matchedByKey: boolean; templateVersion: number | null };
type Collection = { id: number; name: string; recordKey: string | null };
type Reviewer = { id: number; name: string };
type Version = { id: number; body: string };
type Grouping = "starts" | "matched" | "follows";

const COLLECTION = 1; // ponytail: the only collection until there is a way to choose one
const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
const groupingOf = (t: PageType): Grouping => (t.startsRecord ? "starts" : t.matchedByKey ? "matched" : "follows");
const GROUPINGS: Record<Grouping, string> = {
  starts: "Starts a survey",
  matched: "Joins the survey with the same number",
  follows: "Follows the page before it",
};

// The collection's page types: what each is called, the template its pages are read with, and how they group into surveys.
export default function PageTypesScreen() {
  const [types, setTypes] = useState<PageType[] | null>(null);
  const [collection, setCollection] = useState<Collection | null>(null);
  const [reviewers, setReviewers] = useState<Reviewer[]>([]);
  const [loadError, setLoadError] = useState("");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<PageType | null>(null);

  const load = useCallback(() => {
    Promise.all([
      backendRequest<PageType[]>("/page-types"),
      backendRequest<Collection>(`/collections/${COLLECTION}`),
      backendRequest<Reviewer[]>("/reviewers"),
    ]).then(([t, c, r]) => {
      setTypes(t);
      setCollection(c);
      setReviewers(r);
      setLoadError("");
    }).catch((e) => setLoadError(message(e, "Could not load the page types.")));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader crumbs={[{ label: "All bundles", href: "/" }, { label: "Settings", href: "/?view=settings" }, { label: "Page types" }]} />
      <main className="mx-auto max-w-6xl space-y-8 p-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Page types</h1>
          <p className="text-sm text-muted-foreground">
            The kinds of page in {collection?.name ?? "this collection"}: what each is called, how it is read, and how pages group into surveys.
          </p>
        </div>
        {loadError && (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-2">
              {loadError} <Button variant="outline" size="sm" onClick={load}>Try again</Button>
            </AlertDescription>
          </Alert>
        )}
        {collection && <SurveyNumber key={collection.recordKey ?? ""} collection={collection} onSaved={load} />}
        {types && (
          <section className="space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold tracking-tight">Page types</h2>
                <p className="text-sm text-muted-foreground">A page is read with its type's template; a type with no template isn't read.</p>
              </div>
              <Button onClick={() => setAdding(true)}>Add page type</Button>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Page type</TableHead>
                  <TableHead>Grouping</TableHead>
                  <TableHead>Template</TableHead>
                  <TableHead className="w-0"><span className="sr-only">Actions</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {types.map((t) => (
                  <TableRow key={t.name}>
                    <TableCell className="font-medium">{t.label}</TableCell>
                    <TableCell>{t.unknown ? "Pages sorting couldn't place wait here" : GROUPINGS[groupingOf(t)]}</TableCell>
                    <TableCell>{t.unknown ? "Not read" : t.templateVersion ? "Saved" : "None yet"}</TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" aria-label={`Edit ${t.label}`} onClick={() => setEditing(t)}>Edit</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>
        )}
      </main>
      {adding && (
        <AddDialog reviewers={reviewers} onClose={() => setAdding(false)}
          onAdded={(created) => { setAdding(false); setEditing(created); load(); }} />
      )}
      {editing && collection && (
        <EditDialog type={editing} collection={collection} reviewers={reviewers} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

// The field holding each survey's number; empty: pages group by their order only.
function SurveyNumber({ collection, onSaved }: { collection: Collection; onSaved: () => void }) {
  const id = useId();
  const [key, setKey] = useState(collection.recordKey ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError("");
    try {
      await backendRequest<Collection>(`/collections/${collection.id}`, json("PATCH", { recordKey: key }));
      onSaved();
    } catch (e) {
      setError(message(e, "Could not save the survey number field."));
    }
    setBusy(false);
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Survey number</h2>
        <p className="text-sm text-muted-foreground">
          The field holding each survey's number. A page that joins by number is filed with the survey showing the same number.
          Leave it empty to group pages by their order only.
        </p>
      </div>
      <div className="flex max-w-md items-end gap-2">
        <Field className="flex-1">
          <FieldLabel htmlFor={id}>Survey number field</FieldLabel>
          <Input id={id} value={key} placeholder="e.g. number_of_dwelling" onChange={(e) => setKey(e.target.value)} />
        </Field>
        <Button disabled={busy || key.trim() === (collection.recordKey ?? "")} onClick={save}>Save</Button>
      </div>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    </section>
  );
}

// Who saves: a new page type and each template version record their reviewer.
function ReviewerField({ reviewers, value, onChange }: { reviewers: Reviewer[]; value: string; onChange: (value: string) => void }) {
  const id = useId();
  return (
    <Field>
      <FieldLabel htmlFor={id}>Saved as</FieldLabel>
      <NativeSelect id={id} className="w-full" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select reviewer</option>
        {reviewers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
      </NativeSelect>
      {!reviewers.length && <FieldDescription>Add yourself as a reviewer on a review screen first.</FieldDescription>}
    </Field>
  );
}

function AddDialog({ reviewers, onClose, onAdded }: { reviewers: Reviewer[]; onClose: () => void; onAdded: (created: PageType) => void }) {
  const id = useId();
  const [label, setLabel] = useState("");
  const [reviewerId, setReviewerId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    setError("");
    try {
      onAdded(await backendRequest<PageType>("/page-types", json("POST", { label, reviewerId: Number(reviewerId) })));
    } catch (e) {
      setError(message(e, "Could not add the page type."));
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add page type</DialogTitle>
          <DialogDescription>Then give it a template, so its pages can be read.</DialogDescription>
        </DialogHeader>
        <FieldGroup className="gap-4">
          <Field>
            <FieldLabel htmlFor={id}>Label</FieldLabel>
            <Input id={id} value={label} placeholder="e.g. Follow-up visit" onChange={(e) => setLabel(e.target.value)} />
          </Field>
          <ReviewerField reviewers={reviewers} value={reviewerId} onChange={setReviewerId} />
        </FieldGroup>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !label.trim() || !reviewerId} onClick={add}>Add</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function GroupingOption({ value, title, disabled, children }: { value: Grouping; title: string; disabled?: boolean; children: ReactNode }) {
  return (
    <FieldLabel htmlFor={`grouping-${value}`}>
      <Field orientation="horizontal" data-disabled={disabled || undefined}>
        <RadioGroupItem value={value} id={`grouping-${value}`} disabled={disabled} />
        <FieldContent>
          <FieldTitle>{title}</FieldTitle>
          <FieldDescription>{children}</FieldDescription>
        </FieldContent>
      </Field>
    </FieldLabel>
  );
}

// A page type's label, how its pages group, and its template (each save of the template is a new version).
function EditDialog({ type, collection, reviewers, onClose, onSaved }: {
  type: PageType; collection: Collection; reviewers: Reviewer[]; onClose: () => void; onSaved: () => void;
}) {
  const id = useId();
  const [label, setLabel] = useState(type.label);
  const [grouping, setGrouping] = useState<Grouping>(groupingOf(type));
  const [newest, setNewest] = useState<Version | null>(null);
  const [template, setTemplate] = useState<string | null>(type.templateVersion ? null : ""); // null: loading
  const [reviewerId, setReviewerId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!type.templateVersion) return;
    backendRequest<Version[]>(`/instructions/${type.name}`)
      .then((versions) => { setNewest(versions[0]); setTemplate(versions[0].body); })
      .catch((e) => setError(message(e, "Could not load the template.")));
  }, [type]);

  const templateChanged = template !== null && template !== (newest?.body ?? "");
  const settingsChanged = label.trim() !== type.label || grouping !== groupingOf(type);

  async function save() {
    setBusy(true);
    setError("");
    const settings = () => backendRequest(`/page-types/${type.name}`,
      json("PATCH", { label, startsRecord: grouping === "starts", matchedByKey: grouping === "matched" }));
    const saveTemplate = () => backendRequest(`/instructions/${type.name}`,
      json("POST", { body: template, basedOn: newest?.id ?? null, reviewerId: Number(reviewerId) }));
    try {
      // A type that groups by number needs the number field in its template before its setting; one that stops, after.
      if (grouping === "follows") {
        if (settingsChanged) await settings();
        if (templateChanged) await saveTemplate();
      } else {
        if (templateChanged) await saveTemplate();
        if (settingsChanged) await settings();
      }
      onSaved();
    } catch (e) {
      setError(message(e, "Could not save."));
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle>Edit {type.label}</DialogTitle>
          <DialogDescription>Changes apply to pages read from now on.</DialogDescription>
        </DialogHeader>
        <FieldGroup className="gap-4">
          <Field>
            <FieldLabel htmlFor={id}>Label</FieldLabel>
            <Input id={id} value={label} onChange={(e) => setLabel(e.target.value)} />
          </Field>
          {type.unknown ? (
            <p className="text-sm text-muted-foreground">
              Pages sorting couldn't place wait here, unread, until a reviewer picks their type. They have no template and don't start or join a survey.
            </p>
          ) : (
            <>
              <Field>
                <FieldTitle>Grouping</FieldTitle>
                <RadioGroup aria-label="Grouping" value={grouping} onValueChange={(value) => setGrouping(value as Grouping)}>
                  <GroupingOption value="starts" title={GROUPINGS.starts}>A page of this type begins a new survey; the pages after it join it.</GroupingOption>
                  <GroupingOption value="matched" title={GROUPINGS.matched} disabled={!collection.recordKey}>
                    {collection.recordKey
                      ? `Filed with the survey showing the same ${collection.recordKey}, wherever it is in the bundle.`
                      : "Set a survey number field first."}
                  </GroupingOption>
                  <GroupingOption value="follows" title={GROUPINGS.follows}>Joins the survey of the page before it.</GroupingOption>
                </RadioGroup>
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-template`}>Template</FieldLabel>
                <Textarea id={`${id}-template`} rows={12} className="font-mono text-xs" value={template ?? ""} disabled={template === null}
                  placeholder={'{"field_name": null}'} onChange={(e) => setTemplate(e.target.value)} />
                <FieldDescription>
                  The fields to read off each page, as JSON: every field is null, or an object of fields.
                  {!type.templateVersion && " Until it has one, pages of this type aren't read."}
                </FieldDescription>
              </Field>
              {templateChanged && <ReviewerField reviewers={reviewers} value={reviewerId} onChange={setReviewerId} />}
            </>
          )}
        </FieldGroup>
        {error && <Alert variant="destructive"><AlertDescription className="whitespace-pre-line">{error}</AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !label.trim() || (!settingsChanged && !templateChanged) || (templateChanged && !reviewerId)} onClick={save}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
