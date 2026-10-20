import { useEffect, useId, useState } from "react";
import { Plus, X } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { me } from "../person";
import { backendRequest } from "../progress/backend";
import type { PageType } from "./PageTypesScreen";
import { cleanRules, parseTemplate, type Rules, type Template } from "./rules";

type Version = { id: number; body: string; rules: Rules };
type Row = { name: string; key?: string }; // key: a saved field's, until its name is edited
export type Labels = Record<string, string>; // page number -> page type

const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
const start = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);
// A field as typed, as a template's key ("Index No." -> index_no), and a key as it is shown (index_no -> Index no).
const keyOf = (name: string) => {
  const key = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return /^[0-9]/.test(key) ? `field_${key}` : key;
};
const nameOf = (key: string) => start(key.replaceAll("_", " "));

// Beside a sample's page on screen, setting its series up from it: what kind of page it is (one of the series' page types, or a
// new one named here), and that kind's fields to read, its template, as a list.
export default function SamplePanel({ collectionId, item, page, types, labels, onLabels, onChanged }: {
  collectionId: number; item: string; page: number; types: PageType[]; labels: Labels; onLabels: (labels: Labels) => void; onChanged: () => void;
}) {
  const id = useId();
  const [addingTo, setAddingTo] = useState<number | null>(null); // the page a new page type is being named for
  const adding = addingTo === page;
  const [label, setLabel] = useState("");
  const [drafts, setDrafts] = useState<Record<string, Row[]>>({}); // each page type's fields as edited, until saved
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const own = types.filter((t) => !t.unknown);
  const type = own.find((t) => t.name === labels[String(page)]);

  async function act(work: () => Promise<void>, fallback: string) {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError(message(e, fallback));
    }
    setBusy(false);
  }
  const say = async (pageType: string | null) =>
    onLabels(await backendRequest<Labels>(`/collections/${collectionId}/items/${item}/labels/${page}`, json("PUT", { pageType })));
  function choose(value: string) {
    if (busy) return;
    setAddingTo(value === "new" ? page : null);
    if (value !== "new") void act(() => say(value || null), "Could not save what the page is.");
  }
  const add = () => act(async () => {
    const created = await backendRequest<PageType>("/page-types", json("POST", { label, reviewerId: me().id, collectionId }));
    setAddingTo(null);
    setLabel("");
    onChanged(); // listed even if saying what the page is fails
    await say(created.name);
  }, "Could not add the page type.");

  return (
    <section aria-label="This page" className="space-y-4 rounded-lg border bg-card p-5">
      <Field>
        <FieldLabel htmlFor={`${id}-type`}>Page {page} is a</FieldLabel>
        <NativeSelect id={`${id}-type`} className="w-full" value={adding ? "new" : type?.name ?? ""} aria-busy={busy}
          onChange={(e) => choose(e.target.value)}>
          <option value="">Not said yet</option>
          {own.map((t) => <option key={t.name} value={t.name}>{t.label}</option>)}
          <option value="new">New page type…</option>
        </NativeSelect>
      </Field>
      {adding && (
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void add(); }}>
          <Input aria-label="New page type" placeholder="Casualty card" value={label} onChange={(e) => setLabel(e.target.value)} autoFocus />
          <Button type="submit" disabled={busy || !label.trim()}>Add</Button>
        </form>
      )}
      {error && <Alert variant="destructive"><AlertDescription className="whitespace-pre-line">{error}</AlertDescription></Alert>}
      {type && !adding && <Fields key={`${type.name}-${type.templateVersion}`} collectionId={collectionId} type={type}
        draft={drafts[`${type.name}-${type.templateVersion}`]}
        onDraft={(rows) => setDrafts((d) => ({ ...d, [`${type.name}-${type.templateVersion}`]: rows }))} onSaved={onChanged} />}
    </section>
  );
}

// A page type's fields to read, its template, as a list of names (as edited: draft, kept by the panel across pages): saved as a
// new version of it, each field kept with its description and rules; one whose fields are grouped is edited in Page types.
function Fields({ collectionId, type, draft, onDraft, onSaved }: {
  collectionId: number; type: PageType; draft?: Row[]; onDraft: (rows: Row[]) => void; onSaved: () => void;
}) {
  const [newest, setNewest] = useState<Version | null | undefined>(type.templateVersion ? undefined : null); // undefined: loading
  const [saved, setSaved] = useState<Row[]>([{ name: "" }]);
  const rows = draft ?? saved;
  const setRows = onDraft;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!type.templateVersion) return;
    let current = true;
    backendRequest<Version[]>(`/instructions/${type.name}`)
      .then(([found]) => {
        if (!current) return;
        setNewest(found);
        setSaved(Object.keys(parseTemplate(found.body) ?? {}).map((key) => ({ name: nameOf(key), key })));
      })
      .catch((e) => { if (current) setError(message(e, "Could not load its fields.")); });
    return () => { current = false; };
  }, [type]);

  const full = `/?series=${collectionId}&view=setup&section=page-types`;
  if (newest === undefined) return error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>
    : <p className="text-sm text-muted-foreground">Loading its fields…</p>;
  const old: Template = parseTemplate(newest?.body ?? null) ?? {};
  if (Object.values(old).some((v) => v !== null && typeof v !== "string")) {
    return <p className="text-sm text-muted-foreground">Its fields are grouped: edit them in <a className="text-primary underline-offset-4 hover:underline" href={full}>Page types</a>.</p>;
  }
  const keys = rows.map((r) => r.key ?? keyOf(r.name)).filter(Boolean);
  const twice = new Set(keys).size < keys.length;
  const changed = keys.join() !== Object.keys(old).join();
  const save = async () => {
    setBusy(true);
    setError("");
    const template = Object.fromEntries(keys.map((k) => [k, k in old ? old[k] : null]));
    try {
      await backendRequest(`/instructions/${type.name}`, json("POST", {
        body: JSON.stringify(template, null, 2), rules: cleanRules(newest?.rules ?? {}, template), basedOn: newest?.id ?? null,
        reviewerId: me().id }));
      onSaved();
    } catch (e) {
      setError(message(e, "Could not save its fields."));
    }
    setBusy(false);
  };

  return (
    <fieldset className="space-y-2">
      <legend className="mb-2 text-sm font-medium">Fields to read from each {type.label}</legend>
      {!type.templateVersion && <p className="text-xs text-muted-foreground">Its pages aren't read until these are saved.</p>}
      <ol className="space-y-1.5">
        {rows.map((row, i) => (
          <li key={i} className="flex gap-2">
            <Input aria-label={`Field ${i + 1}`} placeholder="Surname" value={row.name}
              onChange={(e) => setRows(rows.map((r, j) => (j === i ? { name: e.target.value } : r)))} />
            <Button variant="ghost" size="icon" aria-label={`Remove field ${i + 1}`} disabled={rows.length === 1}
              onClick={() => setRows(rows.filter((_, j) => j !== i))}><X /></Button>
          </li>
        ))}
      </ol>
      {twice && <p className="text-sm text-destructive">Two fields have the same name.</p>}
      {error && <Alert variant="destructive"><AlertDescription className="whitespace-pre-line">{error}</AlertDescription></Alert>}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setRows([...rows, { name: "" }])}><Plus /> Add field</Button>
        <Button size="sm" disabled={busy || !keys.length || twice || !changed} onClick={save}>Save template</Button>
      </div>
      <a className="block text-xs text-muted-foreground underline-offset-4 hover:underline" href={full}>Edit as JSON, or set rules for its fields</a>
    </fieldset>
  );
}
