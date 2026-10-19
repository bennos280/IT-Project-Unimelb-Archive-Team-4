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
import { backendRequest, recordWords } from "../progress/backend";
import { createReviewer } from "../review-screen/api";
import FieldRules from "./FieldRules";
import { cleanRules, parseTemplate, type Rules } from "./rules";

type PageType = { name: string; label: string; builtIn: boolean; unknown: boolean; startsRecord: boolean; matchedByKey: boolean; templateVersion: number | null };
type Collection = { id: number; name: string; recordKey: string | null; recordName: string; grouped: boolean };
type Reviewer = { id: number; name: string };
type Version = { id: number; body: string; rules: Rules; reviewer: string | null; note: string | null; createdAt: string };
type Grouping = "starts" | "matched" | "follows";

const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
const groupingOf = (t: PageType): Grouping => (t.startsRecord ? "starts" : t.matchedByKey ? "matched" : "follows");
// How a type groups, in the series' words.
const groupings = ({ recordName }: Collection): Record<Grouping, string> => ({
  starts: `Starts ${recordWords(recordName).a}`,
  matched: `Joins the ${recordName} with the same number`,
  follows: "Follows the page before it",
});

// The collection's page types: what each is called, the template its pages are read with, and how they group into records.
export default function PageTypesScreen() {
  const collectionId = Number(new URLSearchParams(location.search).get("collection")) || 1;
  const [types, setTypes] = useState<PageType[] | null>(null);
  const [collection, setCollection] = useState<Collection | null>(null);
  const [reviewers, setReviewers] = useState<Reviewer[]>([]);
  const [loadError, setLoadError] = useState("");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<PageType | null>(null);

  const load = useCallback(() => {
    Promise.all([
      backendRequest<PageType[]>(`/page-types?collection=${collectionId}`),
      backendRequest<Collection>(`/collections/${collectionId}`),
      backendRequest<Reviewer[]>("/reviewers"),
    ]).then(([t, c, r]) => {
      setTypes(t);
      setCollection(c);
      setReviewers(r);
      setLoadError("");
    }).catch((e) => setLoadError(message(e, "Could not load the page types.")));
  }, [collectionId]);
  useEffect(load, [load]);
  const addReviewer = (person: Reviewer) => setReviewers((r) => [...r.filter((p) => p.id !== person.id), person]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader crumbs={[{ label: "Series", href: "/" }, { label: collection?.name ?? "Series", href: `/?collection=${collectionId}` },
        { label: "Page types" }]} />
      <main className="mx-auto max-w-6xl space-y-8 p-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Page types</h1>
          <p className="text-sm text-muted-foreground">
            The kinds of page in {collection?.name ?? "this series"}: what each is called, how it is read, and how pages group into {recordWords(collection?.recordName).many}.
          </p>
        </div>
        {loadError && (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-2">
              {loadError} <Button variant="outline" size="sm" onClick={load}>Try again</Button>
            </AlertDescription>
          </Alert>
        )}
        {collection && <Records key={`${collection.recordName} ${collection.recordKey}`} collection={collection} onSaved={load} />}
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
                    <TableCell>
                      {t.unknown ? "Pages sorting couldn't place wait here"
                        : collection && (collection.grouped ? groupings(collection)[groupingOf(t)] : `${recordWords(collection.recordName).A} of its own`)}
                    </TableCell>
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
        <AddDialog collectionId={collectionId} reviewers={reviewers} onAddReviewer={addReviewer} onClose={() => setAdding(false)}
          onAdded={(created) => { setAdding(false); setEditing(created); load(); }} />
      )}
      {editing && collection && (
        <EditDialog type={editing} collection={collection} reviewers={reviewers} onAddReviewer={addReviewer}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

// What one record is called, and the field holding each record's number; empty: pages group by their order only.
function Records({ collection, onSaved }: { collection: Collection; onSaved: () => void }) {
  const id = useId();
  const [name, setName] = useState(collection.recordName);
  const [key, setKey] = useState(collection.recordKey ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const words = recordWords(collection.recordName);
  const stored = name.toLowerCase().split(/\s+/).filter(Boolean).join(" ") || "record"; // as the backend stores it
  const unchanged = stored === collection.recordName && key.trim() === (collection.recordKey ?? "");

  async function save() {
    setBusy(true);
    setError("");
    try {
      await backendRequest<Collection>(`/collections/${collection.id}`, json("PATCH", { recordName: name, recordKey: key }));
      onSaved();
    } catch (e) {
      setError(message(e, "Could not save the records' settings."));
    }
    setBusy(false);
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Records</h2>
        <p className="text-sm text-muted-foreground">
          {collection.grouped
            ? `The pages of one ${words.one} are reviewed together. A page that joins by number is filed with the ${words.one} showing the same number; leave the number field empty to group pages by their order only.`
            : `No page type starts ${words.a}, so each page is ${words.a} of its own. Edit a page type to make it start one.`}
        </p>
      </div>
      <div className="flex max-w-2xl flex-wrap items-end gap-2">
        <Field className="min-w-48 flex-1">
          <FieldLabel htmlFor={`${id}-name`}>Record name</FieldLabel>
          <Input id={`${id}-name`} value={name} placeholder="record" onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field className="min-w-48 flex-1">
          <FieldLabel htmlFor={`${id}-key`}>{words.One} number field</FieldLabel>
          <Input id={`${id}-key`} value={key} placeholder="e.g. number_of_dwelling" onChange={(e) => setKey(e.target.value)} />
        </Field>
        <Button disabled={busy || unchanged} onClick={save}>Save</Button>
      </div>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    </section>
  );
}

// Who saves: a new page type and each template version record their reviewer; someone not listed adds their name here.
function ReviewerField({ reviewers, value, onChange, onAddReviewer }: {
  reviewers: Reviewer[]; value: string; onChange: (value: string) => void; onAddReviewer: (person: Reviewer) => void;
}) {
  const id = useId();
  const [adding, setAdding] = useState(!reviewers.length);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    setError("");
    try {
      const person = await createReviewer(name);
      onAddReviewer(person);
      onChange(String(person.id));
      setAdding(false);
      setName("");
    } catch (e) {
      setError(message(e, "Could not add the reviewer."));
    }
    setBusy(false);
  }

  return (
    <Field>
      <FieldLabel htmlFor={id}>Saved as</FieldLabel>
      <NativeSelect id={id} className="w-full" value={adding ? "add" : value} onChange={(e) => {
        setAdding(e.target.value === "add");
        onChange(e.target.value === "add" ? "" : e.target.value);
      }}>
        <option value="">Select reviewer</option>
        {reviewers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        <option value="add">+ Add reviewer…</option>
      </NativeSelect>
      {adding && (
        <div className="flex gap-2">
          <Input aria-label="New reviewer name" placeholder="Enter reviewer name" value={name} onChange={(e) => setName(e.target.value)} />
          <Button variant="outline" disabled={busy || !name.trim()} onClick={add}>Add reviewer</Button>
        </div>
      )}
      {error && <FieldDescription className="text-destructive">{error}</FieldDescription>}
    </Field>
  );
}

function AddDialog({ collectionId, reviewers, onAddReviewer, onClose, onAdded }: {
  collectionId: number; reviewers: Reviewer[]; onAddReviewer: (person: Reviewer) => void; onClose: () => void;
  onAdded: (created: PageType) => void;
}) {
  const id = useId();
  const [label, setLabel] = useState("");
  const [reviewerId, setReviewerId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    setError("");
    try {
      onAdded(await backendRequest<PageType>("/page-types", json("POST", { label, reviewerId: Number(reviewerId), collectionId })));
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
          <ReviewerField reviewers={reviewers} value={reviewerId} onChange={setReviewerId} onAddReviewer={onAddReviewer} />
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

// A page type's label, how its pages group, its template and its fields' rules (each save of those is a new version; an
// older one can be brought back).
function EditDialog({ type, collection, reviewers, onAddReviewer, onClose, onSaved }: {
  type: PageType; collection: Collection; reviewers: Reviewer[]; onAddReviewer: (person: Reviewer) => void; onClose: () => void;
  onSaved: () => void;
}) {
  const id = useId();
  const [label, setLabel] = useState(type.label);
  const [grouping, setGrouping] = useState<Grouping>(groupingOf(type));
  const [versions, setVersions] = useState<Version[]>([]); // newest first
  const [template, setTemplate] = useState<string | null>(type.templateVersion ? null : ""); // null: loading
  const [rules, setRules] = useState<Rules>({});
  const [reviewerId, setReviewerId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const newest = versions[0] ?? null;

  useEffect(() => {
    if (!type.templateVersion) return;
    backendRequest<Version[]>(`/instructions/${type.name}`)
      .then((loaded) => { setVersions(loaded); setTemplate(loaded[0].body); setRules(loaded[0].rules); })
      .catch((e) => setError(message(e, "Could not load the template.")));
  }, [type]);

  const parsed = parseTemplate(template);
  const cleaned = cleanRules(rules, parsed);
  const rulesChanged = JSON.stringify(cleaned) !== JSON.stringify(cleanRules(newest?.rules ?? {}, parseTemplate(newest?.body ?? null)));
  const templateChanged = template !== null && (template !== (newest?.body ?? "") || rulesChanged);
  const settingsChanged = label.trim() !== type.label || grouping !== groupingOf(type);

  async function save() {
    setBusy(true);
    setError("");
    const settings = () => backendRequest(`/page-types/${type.name}`,
      json("PATCH", { label, startsRecord: grouping === "starts", matchedByKey: grouping === "matched" }));
    const saveTemplate = () => backendRequest(`/instructions/${type.name}`,
      json("POST", { body: template, rules: cleaned, basedOn: newest?.id ?? null, reviewerId: Number(reviewerId) }));
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
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl">
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
              Pages sorting couldn't place wait here, unread, until a reviewer picks their type. They have no template and don't start or join {recordWords(collection.recordName).a}.
            </p>
          ) : (
            <>
              <Field>
                <FieldTitle>Grouping</FieldTitle>
                <RadioGroup aria-label="Grouping" value={grouping} onValueChange={(value) => setGrouping(value as Grouping)}>
                  <GroupingOption value="starts" title={groupings(collection).starts}>A page of this type begins a new {collection.recordName}; the pages after it join it.</GroupingOption>
                  <GroupingOption value="matched" title={groupings(collection).matched} disabled={!collection.recordKey}>
                    {collection.recordKey
                      ? `Filed with the ${collection.recordName} showing the same ${collection.recordKey}, wherever it is in the item.`
                      : `Set ${recordWords(collection.recordName).a} number field first.`}
                  </GroupingOption>
                  <GroupingOption value="follows" title={groupings(collection).follows}>
                    {collection.grouped ? `Joins the ${collection.recordName} of the page before it.` : `Each page of this type is ${recordWords(collection.recordName).a} of its own.`}
                  </GroupingOption>
                </RadioGroup>
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-template`}>Template</FieldLabel>
                <Textarea id={`${id}-template`} rows={12} className="font-mono text-xs" value={template ?? ""} disabled={template === null}
                  placeholder={'{"field_name": null}'} onChange={(e) => setTemplate(e.target.value)} />
                <FieldDescription>
                  The fields to read off each page, as JSON: every field is null (or its description), or an object of fields.
                  {!type.templateVersion && " Until it has one, pages of this type aren't read."}
                </FieldDescription>
              </Field>
              <Field>
                <FieldTitle>Fields</FieldTitle>
                <FieldDescription>
                  What each field should hold. A transcription that breaks a field's rule is flagged for review; the description
                  helps the model read it.
                </FieldDescription>
                {parsed ? <FieldRules template={parsed} rules={rules} onRules={setRules} onTemplate={setTemplate} />
                  : <p className="text-sm text-muted-foreground">{template ? "Fix the template's JSON to set its fields' rules." : "Add fields to the template first."}</p>}
              </Field>
              {versions.length > 1 && (
                <Field>
                  <FieldTitle>History</FieldTitle>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Version</TableHead>
                        <TableHead>Saved</TableHead>
                        <TableHead>By</TableHead>
                        <TableHead>Note</TableHead>
                        <TableHead className="w-0"><span className="sr-only">Use</span></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {versions.map((v, n) => (
                        <TableRow key={v.id}>
                          <TableCell className="font-medium">{versions.length - n}</TableCell>
                          <TableCell className="text-muted-foreground">{v.createdAt ? new Date(v.createdAt).toLocaleString() : ""}</TableCell>
                          <TableCell>{v.reviewer ?? "From the files"}</TableCell>
                          <TableCell className="whitespace-normal">{v.note}</TableCell>
                          <TableCell>
                            {n === 0 ? <span className="text-muted-foreground">Current</span> : (
                              <Button variant="outline" size="sm" aria-label={`Use version ${versions.length - n}`}
                                onClick={() => { setTemplate(v.body); setRules(v.rules); }}>Use this version</Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <FieldDescription>Using an older version fills it in above; saving makes it the newest.</FieldDescription>
                </Field>
              )}
              {templateChanged && <ReviewerField reviewers={reviewers} value={reviewerId} onChange={setReviewerId} onAddReviewer={onAddReviewer} />}
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
