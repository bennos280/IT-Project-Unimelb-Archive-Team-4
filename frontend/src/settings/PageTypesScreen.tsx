import { useCallback, useEffect, useId, useState, type ReactNode } from "react";
import { Box, File, Layers, Plus } from "lucide-react";

import AppHeader from "@/components/AppHeader";
import SeriesHeader from "@/components/SeriesHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { backendRequest, itemTitle, recordNumber, recordWords } from "../progress/backend";
import ChecksSection from "./ChecksSection";
import FieldRules from "./FieldRules";
import ReviewerField, { type Reviewer } from "./ReviewerField";
import { cleanRules, parseTemplate, sameRules, type Rules } from "./rules";

type PageType = { name: string; label: string; builtIn: boolean; unknown: boolean; templateVersion: number | null };
// A level of record between an item and its pages: what one is called, the page types whose pages start one and those whose
// pages join the one showing the same number, and the field holding that number (null: page order only).
type Level = { name: string; starts: string[]; matched: string[]; key: string | null };
type Collection = {
  id: number; name: string; levels: Level[]; recordName: string; grouped: boolean; archiveIdentifier?: string | null;
  archiveSeries?: number | null;
};
type Version = { id: number; body: string; rules: Rules; reviewer: string | null; note: string | null; createdAt: string };
// How an item already read would group by some levels: the records grouping would make, parents first, each with the one it
// sits in and its pages; the pages in none; and what grouping would flag.
type Preview = { records: { id: string; parent: string | null; pages: string[] }[]; loose: string[]; problems: string[] };
type Role = "starts" | "matched" | "follows";

const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
const start = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);
const SECTIONS = ["levels", "page-types", "checks"];

// A series' Setup tab, in three: its levels of record, its page types (what each is called, the template its pages are read
// with and its fields' rules), and its checks across fields. The one shown is in the URL (?section=; the old ?view=page-types
// opens the page types).
export default function PageTypesScreen() {
  const params = new URLSearchParams(location.search);
  const collectionId = Number(params.get("collection")) || 1;
  const [section, setSection] = useState(() => SECTIONS.find((s) => s === params.get("section"))
    ?? (params.get("view") === "page-types" ? "page-types" : "levels"));
  function show(next: string) {
    const url = new URL(location.href);
    if (next === "levels") url.searchParams.delete("section");
    else url.searchParams.set("section", next);
    history.replaceState(null, "", url);
    setSection(next);
  }
  const [types, setTypes] = useState<PageType[] | null>(null);
  const [collection, setCollection] = useState<Collection | null>(null);
  const [reviewers, setReviewers] = useState<Reviewer[]>([]);
  const [loadError, setLoadError] = useState("");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<PageType | null>(null);

  const load = useCallback(() =>
    Promise.all([
      backendRequest<PageType[]>(`/page-types?collection=${collectionId}`),
      backendRequest<Collection>(`/collections/${collectionId}`),
      backendRequest<Reviewer[]>("/reviewers"),
    ]).then(([t, c, r]) => {
      setTypes(t);
      setCollection(c);
      setReviewers(r);
      setLoadError("");
    }).catch((e) => setLoadError(message(e, "Could not load the page types."))), [collectionId]);
  useEffect(() => { void load(); }, [load]);
  const addReviewer = (person: Reviewer) => setReviewers((r) => [...r.filter((p) => p.id !== person.id), person]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader series={{ id: collectionId, name: collection?.name ?? "" }} />
      <main className="space-y-8 p-6">
        <SeriesHeader series={{ id: collectionId, name: collection?.name ?? "", archiveIdentifier: collection?.archiveIdentifier,
          archiveSeries: collection?.archiveSeries }} tab="setup" />
        {loadError && (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-2">
              {loadError} <Button variant="outline" size="sm" onClick={load}>Try again</Button>
            </AlertDescription>
          </Alert>
        )}
        <Tabs value={section} onValueChange={show} className="gap-6">
          <TabsList aria-label="Setup">
            <TabsTrigger value="levels">Levels</TabsTrigger>
            <TabsTrigger value="page-types">Page types</TabsTrigger>
            <TabsTrigger value="checks">Checks</TabsTrigger>
          </TabsList>
          <TabsContent value="levels">
            {collection && types && <Levels collection={collection} types={types} onSaved={load} />}
          </TabsContent>
          <TabsContent value="page-types">
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
                      <TableHead>Template</TableHead>
                      <TableHead className="w-0"><span className="sr-only">Actions</span></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {types.map((t) => (
                      <TableRow key={t.name}>
                        <TableCell className="font-medium">{t.label}</TableCell>
                        <TableCell>{t.unknown ? "Not read: pages sorting couldn't place wait here" : t.templateVersion ? "Saved" : "None yet"}</TableCell>
                        <TableCell>
                          <Button variant="outline" size="sm" aria-label={`Edit ${t.label}`} onClick={() => setEditing(t)}>Edit</Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </section>
            )}
          </TabsContent>
          <TabsContent value="checks">
            {types && <ChecksSection collectionId={collectionId} types={types} reviewers={reviewers} onAddReviewer={addReviewer} />}
          </TabsContent>
        </Tabs>
      </main>
      {adding && (
        <AddDialog collectionId={collectionId} reviewers={reviewers} onAddReviewer={addReviewer} onClose={() => setAdding(false)}
          onAdded={(created) => { setAdding(false); setEditing(created); load(); }} />
      )}
      {editing && (
        <EditDialog type={editing} reviewers={reviewers} onAddReviewer={addReviewer}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

// One rung of the levels' ladder, indented under the one above.
function Rung({ depth, icon, name, how, fixed, children }: {
  depth: number; icon: ReactNode; name: string; how: string; fixed?: boolean; children?: ReactNode;
}) {
  return (
    <li className={`flex items-center gap-3 rounded-md border px-3 py-2 text-sm ${fixed ? "bg-muted/50 text-muted-foreground" : ""}`}
      style={{ marginLeft: `${depth * 1.5}rem` }}>
      <span aria-hidden="true" className="[&_svg]:size-4">{icon}</span>
      <span className={`min-w-20 font-medium ${fixed ? "" : "text-foreground"}`}>{name}</span>
      <span className="flex-1 text-muted-foreground">{how}</span>
      {children}
    </li>
  );
}

// The series' levels of record between an item and its pages, top first, as a ladder from Item to Page; with none, each item
// is one record. A level added goes inside the bottom one.
function Levels({ collection, types, onSaved }: { collection: Collection; types: PageType[]; onSaved: () => Promise<void> }) {
  const [editing, setEditing] = useState<number | null>(null); // the level's index; levels.length: a new one
  const levels = collection.levels;
  const label = (name: string) => types.find((t) => t.name === name)?.label ?? name;
  const how = (level: Level) => [
    level.starts.length ? `starts at ${level.starts.map(label).join(", ")}` : "each page is one",
    level.matched.length ? `${level.matched.map(label).join(", ")} ${level.matched.length === 1 ? "joins" : "join"} by ${level.key}` : "",
  ].filter(Boolean).join(" · ");
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Levels</h2>
        <p className="text-sm text-muted-foreground">
          How an item's pages group into records for review, each level inside the one above. Changes apply to items read from now on.
        </p>
      </div>
      <ol aria-label="Levels" className="max-w-2xl space-y-1.5">
        <Rung depth={0} icon={<Box />} name="Item" how="From the archive" fixed />
        {levels.map((level, i) => (
          <Rung key={level.name} depth={i + 1} icon={<Layers />} name={start(level.name)} how={how(level)}>
            <Button variant="outline" size="sm" aria-label={`Edit ${level.name}`} onClick={() => setEditing(i)}>Edit</Button>
          </Rung>
        ))}
        <Rung depth={levels.length + 1} icon={<File />} name="Page" how="From the scan" fixed />
      </ol>
      {!levels.length && <p className="text-sm text-muted-foreground">No levels: each item is one record.</p>}
      <Button variant="outline" onClick={() => setEditing(levels.length)}><Plus /> Add level</Button>
      {editing !== null && (
        <LevelDialog collection={collection} types={types} index={editing} onClose={() => setEditing(null)}
          onSaved={async () => { await onSaved(); setEditing(null); }} />
      )}
    </section>
  );
}

// A level's name, what each read page type does in it (starts one, joins the one with the same number, or follows the page
// before it) and its number field; saved with the series' other levels, or removed from them.
function LevelDialog({ collection, types, index, onClose, onSaved }: {
  collection: Collection; types: PageType[]; index: number; onClose: () => void; onSaved: () => Promise<void>;
}) {
  const id = useId();
  const existing = collection.levels[index] as Level | undefined;
  const read = types.filter((t) => !t.unknown);
  const [name, setName] = useState(existing?.name ?? "");
  const [roles, setRoles] = useState<Record<string, Role>>(() => Object.fromEntries(read.map((t) =>
    [t.name, existing?.starts.includes(t.name) ? "starts" : existing?.matched.includes(t.name) ? "matched" : "follows"])));
  const [key, setKey] = useState(existing?.key ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Each page type's template's fields that can hold a number (not lists or groups of fields), and the series' items read.
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [items, setItems] = useState<{ id: string; name: string }[] | null>(null);
  const [item, setItem] = useState("");
  const [preview, setPreview] = useState<{ for: string; result?: Preview; error?: string } | null>(null); // for: what was tried
  const [previewing, setPreviewing] = useState(false);
  const [loadError, setLoadError] = useState("");
  useEffect(() => {
    backendRequest<Record<string, { body: string }>>("/instructions").then((found) => setFields(Object.fromEntries(
      Object.entries(found).map(([kind, v]) => {
        const template = parseTemplate(v.body) ?? {};
        return [kind, Object.keys(template).filter((f) => template[f] === null || typeof template[f] === "string")];
      })))).catch(() => setLoadError("Could not load the templates' fields."));
    backendRequest<{ id: string; name: string }[]>(`/export/bundles?collection=${collection.id}`)
      .then((found) => { setItems(found); setItem(found[0]?.id ?? ""); }).catch(() => setLoadError("Could not load the series' items."));
  }, [collection.id]);
  const words = recordWords(name.trim().toLowerCase() || "record");
  const level: Level = { name, key, starts: read.filter((t) => roles[t.name] === "starts").map((t) => t.name),
    matched: read.filter((t) => roles[t.name] === "matched").map((t) => t.name) };
  // The series' levels as saving would leave them.
  const next = existing ? collection.levels.map((l, i) => (i === index ? level : l)) : [...collection.levels, level];
  // The number field can be one every page type that starts or joins one has (one with no template isn't read: it has none);
  // with none chosen yet, any type's.
  const grouped = [...level.starts, ...level.matched].filter((t) => fields[t]);
  const choices = (grouped.length
    ? (fields[grouped[0]] ?? []).filter((f) => grouped.every((t) => (fields[t] ?? []).includes(f)))
    : [...new Set(read.flatMap((t) => fields[t.name] ?? []))].sort());
  if (key && !choices.includes(key)) choices.unshift(key);

  // What a try was of: once the settings or the item change, its result or error no longer says anything.
  const trying = JSON.stringify([next, item]);
  async function tryIt() {
    setPreviewing(true);
    try {
      setPreview({ for: trying, result: await backendRequest<Preview>(`/collections/${collection.id}/levels/preview`, json("POST", { levels: next, item })) });
    } catch (e) {
      setPreview({ for: trying, error: message(e, "Could not try it.") });
    }
    setPreviewing(false);
  }

  async function save(levels: Level[]) {
    setBusy(true);
    setError("");
    try {
      await backendRequest<Collection>(`/collections/${collection.id}/levels`, json("PUT", { levels }));
      await onSaved(); // the ladder shows the saved levels before the dialog closes
    } catch (e) {
      setError(message(e, "Could not save the levels."));
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{existing ? `Edit level: ${existing.name}` : "Add level"}</DialogTitle>
          <DialogDescription>
            {!existing && collection.levels.length ? `It goes inside each ${collection.levels.at(-1)!.name}. ` : ""}Items read from now on group by it.
          </DialogDescription>
        </DialogHeader>
        <FieldGroup className="gap-4">
          <Field>
            <FieldLabel htmlFor={`${id}-name`}>Name</FieldLabel>
            <Input id={`${id}-name`} value={name} placeholder="e.g. survey" onChange={(e) => setName(e.target.value)} />
            <FieldDescription>What one is called on screen, like survey or letter.</FieldDescription>
          </Field>
          <Field>
            <FieldTitle>Page types</FieldTitle>
            <FieldDescription>Which pages start {words.a}, and which join the one showing the same number wherever they are.</FieldDescription>
            <ul className="space-y-1.5">
              {read.map((t) => (
                <li key={t.name} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="font-medium">{t.label}</span>
                  <NativeSelect aria-label={`What ${t.label} does`} className="w-full sm:w-96" value={roles[t.name]}
                    onChange={(e) => setRoles((r) => ({ ...r, [t.name]: e.target.value as Role }))}>
                    <option value="follows">Follows the page before it</option>
                    <option value="starts">Starts {words.a}</option>
                    <option value="matched">Joins the {words.one} with the same number</option>
                  </NativeSelect>
                </li>
              ))}
            </ul>
            {!read.length && <p className="text-sm text-muted-foreground">Add a page type first.</p>}
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-key`}>Number field</FieldLabel>
            <NativeSelect id={`${id}-key`} className="w-full" value={key} onChange={(e) => setKey(e.target.value)}>
              <option value="">None: by page order only</option>
              {choices.map((f) => <option key={f} value={f}>{start(f.replaceAll("_", " "))}</option>)}
            </NativeSelect>
            <FieldDescription>
              The field each {words.one}'s number is read from, which joining by number needs: one the templates of every page type
              that starts or joins {words.a} have.
            </FieldDescription>
          </Field>
          <Field>
            <FieldTitle>Try it on an item</FieldTitle>
            <FieldDescription>How an item already read would group by these settings, before you save. Nothing changes.</FieldDescription>
            {items?.length ? (
              <div className="flex flex-wrap items-center gap-2">
                <NativeSelect aria-label="Item to try it on" className="w-full sm:w-72" value={item} onChange={(e) => setItem(e.target.value)}>
                  {items.map((i) => <option key={i.id} value={i.id}>{itemTitle(i.name)}</option>)}
                </NativeSelect>
                <Button variant="outline" disabled={previewing || !name.trim()} onClick={tryIt}>{previewing ? "Trying…" : "Try it"}</Button>
              </div>
            ) : items && <p className="text-sm text-muted-foreground">No items read yet to try it on.</p>}
            {loadError && <Alert variant="destructive"><AlertDescription>{loadError}</AlertDescription></Alert>}
            {preview?.for === trying && preview.error && <Alert variant="destructive"><AlertDescription>{preview.error}</AlertDescription></Alert>}
            {preview?.for === trying && preview.result && <PreviewResult preview={preview.result} levels={next} bundle={item} />}
          </Field>
        </FieldGroup>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        <DialogFooter className="sm:justify-between">
          {existing ? (
            <Button variant="ghost" className="text-destructive" disabled={busy}
              onClick={() => save(collection.levels.filter((_, i) => i !== index))}>Remove level</Button>
          ) : <span />}
          <div className="flex gap-2">
            <Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
            <Button disabled={busy || !name.trim()} onClick={() => save(next)}>Save</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// A preview of an item's records: each under the one it sits in, named by its level and number, with its pages by their place
// in the item ("Pg 1–3, 5"); how many there are at the top and in none; and what grouping would flag.
function PreviewResult({ preview, levels, bundle }: { preview: Preview; levels: Level[]; bundle: string }) {
  const place = new Map([...preview.records.flatMap((r) => r.pages), ...preview.loose].sort().map((page, i) => [page, i + 1]));
  const depth = new Map<string, number>();
  for (const r of preview.records) depth.set(r.id, r.parent ? (depth.get(r.parent) ?? 0) + 1 : 1);
  const pages = (ids: string[]) => {
    const runs: [number, number][] = [];
    for (const n of ids.map((page) => place.get(page)!).sort((a, b) => a - b)) {
      if (runs.length && runs.at(-1)![1] === n - 1) runs.at(-1)![1] = n;
      else runs.push([n, n]);
    }
    return runs.length ? `Pg ${runs.map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`)).join(", ")}` : "no pages of its own";
  };
  const top = preview.records.filter((r) => !r.parent).length;
  const topWords = recordWords(levels[0]?.name.trim().toLowerCase() || "record");
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  return (
    <section className="space-y-2 text-sm" aria-label="Preview" aria-live="polite">
      <p className="text-muted-foreground">
        {plural(top, topWords.one, topWords.many)} · {plural(preview.loose.length, "page", "pages")} in none · {plural(preview.problems.length, "problem", "problems")}
      </p>
      <ol aria-label="Records" className="max-h-64 space-y-0.5 overflow-auto rounded-md border p-2">
        {preview.records.map((r) => (
          <li key={r.id} style={{ paddingLeft: `${(depth.get(r.id)! - 1) * 1.25}rem` }}>
            <span className="font-medium">{start(levels[depth.get(r.id)! - 1]?.name.trim().toLowerCase() || "record")} {recordNumber(r.id, r.parent ?? bundle)}</span>
            <span className="text-muted-foreground"> · {pages(r.pages)}</span>
          </li>
        ))}
        {preview.loose.length > 0 && <li className="text-muted-foreground">In none: {pages(preview.loose).replace("no pages of its own", "")}</li>}
      </ol>
      {preview.problems.length > 0 && (
        <ul aria-label="Problems" className="list-disc space-y-0.5 pl-5 text-muted-foreground">
          {preview.problems.slice(0, 5).map((problem) => <li key={problem}>{problem}</li>)}
          {preview.problems.length > 5 && <li>and {preview.problems.length - 5} more</li>}
        </ul>
      )}
    </section>
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

// A page type's label, its template and its fields' rules (each save of those is a new version; an older one can be brought
// back).
function EditDialog({ type, reviewers, onAddReviewer, onClose, onSaved }: {
  type: PageType; reviewers: Reviewer[]; onAddReviewer: (person: Reviewer) => void; onClose: () => void; onSaved: () => void;
}) {
  const id = useId();
  const [label, setLabel] = useState(type.label);
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
  const rulesChanged = !sameRules(cleaned, cleanRules(newest?.rules ?? {}, parseTemplate(newest?.body ?? null)));
  const templateChanged = template !== null && (template !== (newest?.body ?? "") || rulesChanged);
  const settingsChanged = label.trim() !== type.label;

  async function save() {
    setBusy(true);
    setError("");
    try {
      if (settingsChanged) await backendRequest(`/page-types/${type.name}`, json("PATCH", { label }));
      if (templateChanged) {
        await backendRequest(`/instructions/${type.name}`,
          json("POST", { body: template, rules: cleaned, basedOn: newest?.id ?? null, reviewerId: Number(reviewerId) }));
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
              Pages sorting couldn't place wait here, unread, until a reviewer picks their type. They have no template.
            </p>
          ) : (
            <>
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
                          <TableCell className="font-medium">{v.id}</TableCell>
                          <TableCell className="text-muted-foreground">{v.createdAt ? new Date(v.createdAt).toLocaleString() : ""}</TableCell>
                          <TableCell>{v.reviewer ?? "From the files"}</TableCell>
                          <TableCell className="whitespace-normal">{v.note}</TableCell>
                          <TableCell>
                            {n === 0 ? <span className="text-muted-foreground">Current</span> : (
                              <Button variant="outline" size="sm" aria-label={`Use version ${v.id}`}
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
