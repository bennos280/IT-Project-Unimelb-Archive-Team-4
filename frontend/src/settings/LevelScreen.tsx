import { useEffect, useId, useState } from "react";
import { ArrowDown, ArrowUp, X } from "lucide-react";

import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { backendRequest, itemTitle, recordNumber, recordWords } from "../progress/backend";
import type { Collection, Level, PageType, Part } from "./PageTypesScreen";
import { parseTemplate } from "./rules";

// How an item already read would group by some levels: the records grouping would make, parents first, each with the one it
// sits in and its pages; the pages in none; each page's type; and what grouping would flag, each on a page and about a record
// (null: the pages in none).
type Preview = {
  records: { id: string; parent: string | null; pages: string[] }[]; loose: string[]; pageTypes: Record<string, string>;
  problems: { page: string; record: string | null; reason: string }[];
};

const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
const start = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);
// How many of a part a record has, in words.
const counts: Record<Part["count"], string> = { one: "Exactly one", one_or_more: "One or more", any: "Any number", at_most_one: "At most one" };

// One of a series' levels of record on its own page (?view=setup&level=<its place, top first>, or level=new for one inside the
// bottom one): its settings beside how an item already read would group by them, tried before saving. Saving or removing it
// goes back to Setup.
export default function LevelScreen() {
  const params = new URLSearchParams(location.search);
  const collectionId = Number(params.get("collection")) || 1;
  const asked = params.get("level");
  const setup = `/?collection=${collectionId}&view=setup`;
  const [collection, setCollection] = useState<Collection | null>(null);
  const [types, setTypes] = useState<PageType[] | null>(null);
  const [loadError, setLoadError] = useState("");
  useEffect(() => {
    Promise.all([backendRequest<Collection>(`/collections/${collectionId}`), backendRequest<PageType[]>(`/page-types?collection=${collectionId}`)])
      .then(([c, t]) => { setCollection(c); setTypes(t); })
      .catch((e) => setLoadError(message(e, "Could not load the series.")));
  }, [collectionId]);
  const index = asked === "new" ? collection?.levels.length : Number(asked) - 1;
  const existing = index === undefined ? undefined : collection?.levels[index];
  const found = collection && types && index !== undefined && (asked === "new" || existing);
  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader series={{ id: collectionId, name: collection?.name ?? "" }}
        crumbs={[{ label: "Setup", href: setup }, { label: existing ? start(existing.name) : asked === "new" ? "New level" : "Level" }]} />
      <main className="space-y-6 p-6">
        {loadError && <Alert variant="destructive"><AlertDescription>{loadError}</AlertDescription></Alert>}
        {collection && !found && (
          <p className="text-sm text-muted-foreground">This series has no such level. <a className="underline" href={setup}>Back to Setup</a></p>
        )}
        {found && <LevelForm key={asked} collection={collection} types={types} index={index} setup={setup} />}
      </main>
    </div>
  );
}

// A level's name, what one is made of in order (each part a read page type, how many of it, and whether it may be filed
// elsewhere and matched by number; the first starts one) and its number field, saved with the series' other levels or removed
// from them; beside them, an item already read tried by them.
function LevelForm({ collection, types, index, setup }: { collection: Collection; types: PageType[]; index: number; setup: string }) {
  const id = useId();
  const existing = collection.levels[index] as Level | undefined;
  const read = types.filter((t) => !t.unknown);
  const [name, setName] = useState(existing?.name ?? "");
  const [parts, setParts] = useState<Part[]>(existing?.parts ?? []);
  // The parts as changed, the first starting one and none of the others.
  const change = (next: Part[]) => setParts(next.map((p, i) => ({ ...p, how: i === 0 ? "starts" : p.how === "starts" ? "follows" : p.how })));
  // A part moved up or down a place, keeping the focus on its button (or, at an end, on the other one).
  const move = (i: number, by: number) => {
    const next = [...parts];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    change(next);
    const end = by < 0 ? i + by === 0 : i + by === parts.length - 1;
    requestAnimationFrame(() => document.getElementById(`${id}-${parts[i].type}-${(by < 0) !== end ? "up" : "down"}`)?.focus());
  };
  const label = (type: string) => types.find((t) => t.name === type)?.label ?? type;
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
  const level: Level = { name, key, parts };
  // The series' levels as saving would leave them.
  const next = existing ? collection.levels.map((l, i) => (i === index ? level : l)) : [...collection.levels, level];
  // The number field can be one every page type that starts one or is matched to it has (one with no template isn't read: it has none).
  const grouped = parts.filter((p) => p.how !== "follows" && fields[p.type]).map((p) => p.type);
  const choices = grouped.length ? fields[grouped[0]].filter((f) => grouped.every((t) => fields[t].includes(f))) : [];
  if (key && !choices.includes(key)) choices.unshift(key);

  // What a try was of: once the settings or the item change, its result or error no longer says anything.
  const trying = JSON.stringify([next, item]);
  async function tryIt() {
    setPreviewing(true);
    setPreview(null); // a new try starts afresh, showing every record
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
      location.replace(setup); // Back doesn't bring back this page as it was before saving
    } catch (e) {
      setError(message(e, "Could not save the levels."));
      setBusy(false);
    }
  }

  return (
    <>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{existing ? `Level: ${start(existing.name)}` : "Add level"}</h1>
        <p className="text-sm text-muted-foreground">
          {!existing && collection.levels.length ? `It goes inside each ${collection.levels.at(-1)!.name}. ` : ""}Items read from now on group by it.
        </p>
      </div>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <div className="space-y-4 lg:sticky lg:top-6 lg:-m-1 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto lg:p-1">
          <FieldGroup className="gap-4">
            <Field>
              <FieldLabel htmlFor={`${id}-name`}>Name</FieldLabel>
              <Input id={`${id}-name`} value={name} placeholder="e.g. survey" onChange={(e) => setName(e.target.value)} />
              <FieldDescription>What one is called on screen, like survey or letter.</FieldDescription>
            </Field>
            <Field>
              <FieldTitle>{words.A} is made of, in order</FieldTitle>
              <FieldDescription>
                The first page starts {words.a}. Each page after it joins it, unless it may be filed elsewhere. {words.A} with too many
                or too few of a part, or another page type, is flagged.
              </FieldDescription>
              <ol aria-label="Parts" className="space-y-2">
                {parts.map((p, i) => (
                  <li key={p.type} className="space-y-2 rounded-md border p-3 text-sm">
                    <div className="flex items-start gap-2">
                      <span aria-hidden="true" className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">{i + 1}</span>
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">{label(p.type)}</p>
                        {i === 0 ? <p className="text-muted-foreground">Starts {words.a}</p> : (
                          <label className="flex items-center gap-2 text-muted-foreground">
                            <input type="checkbox" className="size-4 accent-primary" checked={p.how === "matched"}
                              aria-label={`${label(p.type)} may be filed elsewhere: match by number`}
                              onChange={(e) => change(parts.map((q) => (q === p ? { ...q, how: e.target.checked ? "matched" : "follows" } : q)))} />
                            May be filed elsewhere: match by number
                          </label>
                        )}
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <Button id={`${id}-${p.type}-up`} variant="ghost" size="icon-sm" aria-label={`Move ${label(p.type)} up`} disabled={i === 0}
                          onClick={() => move(i, -1)}><ArrowUp /></Button>
                        <Button id={`${id}-${p.type}-down`} variant="ghost" size="icon-sm" aria-label={`Move ${label(p.type)} down`}
                          disabled={i === parts.length - 1} onClick={() => move(i, 1)}><ArrowDown /></Button>
                        <Button variant="ghost" size="icon-sm" aria-label={`Remove ${label(p.type)}`} onClick={() => change(parts.filter((q) => q !== p))}><X /></Button>
                      </div>
                    </div>
                    <NativeSelect aria-label={`How many ${label(p.type)}`} className="w-full" value={p.count}
                      onChange={(e) => change(parts.map((q) => (q === p ? { ...q, count: e.target.value as Part["count"] } : q)))}>
                      {Object.entries(counts).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                    </NativeSelect>
                  </li>
                ))}
              </ol>
              {!parts.length && <p className="text-sm text-muted-foreground">With no page types, each page is {words.a} of its own.</p>}
              {read.some((t) => !parts.some((p) => p.type === t.name)) ? (
                <NativeSelect aria-label="Add a page type" className="w-full" value=""
                  onChange={(e) => e.target.value && change([...parts, { type: e.target.value, count: "one", how: "follows" }])}>
                  <option value="">+ Add a page type</option>
                  {read.filter((t) => !parts.some((p) => p.type === t.name)).map((t) => <option key={t.name} value={t.name}>{t.label}</option>)}
                </NativeSelect>
              ) : !read.length && <p className="text-sm text-muted-foreground">Add a page type first.</p>}
            </Field>
            <Field>
              <FieldLabel htmlFor={`${id}-key`}>Number field</FieldLabel>
              <NativeSelect id={`${id}-key`} className="w-full" value={key} onChange={(e) => setKey(e.target.value)}>
                <option value="">None: by page order only</option>
                {choices.map((f) => <option key={f} value={f}>{start(f.replaceAll("_", " "))}</option>)}
              </NativeSelect>
              <FieldDescription>
                The field each {words.one}'s number is read from, which matching by number needs: one the templates of every page type
                that starts {words.a} or is matched to it have.
              </FieldDescription>
            </Field>
          </FieldGroup>
          {error && <Alert variant="destructive"><AlertDescription className="whitespace-pre-line">{error}</AlertDescription></Alert>}
          <div className="flex flex-wrap items-center justify-between gap-2">
            {existing ? (
              <Button variant="ghost" className="text-destructive" disabled={busy}
                onClick={() => save(collection.levels.filter((_, i) => i !== index))}>Remove level</Button>
            ) : <span />}
            <div className="flex gap-2">
              <Button variant="outline" asChild><a href={setup}>Cancel</a></Button>
              <Button disabled={busy || !name.trim()} onClick={() => save(next)}>Save</Button>
            </div>
          </div>
        </div>
        <section aria-labelledby={`${id}-try`} className="min-w-0 space-y-3">
          <div>
            <h2 id={`${id}-try`} className="text-lg font-semibold tracking-tight">Try it on an item</h2>
            <p className="text-sm text-muted-foreground">How an item already read would group by these settings, before you save. Nothing changes.</p>
          </div>
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
        </section>
      </div>
    </>
  );
}

// A page's scan, small, or a stand-in when it isn't on this computer (the caption beside it names the page).
function Thumbnail({ page }: { page: string }) {
  const [missing, setMissing] = useState(false);
  return missing ? (
    <span className="flex h-48 w-36 items-center justify-center rounded border bg-muted p-2">No scan here</span>
  ) : (
    <img src={`/api/pages/${encodeURIComponent(page)}/thumbnail`} loading="lazy" alt="" onError={() => setMissing(true)}
      className="h-48 w-36 rounded border bg-muted object-cover object-top" />
  );
}

// A preview of an item's records: each under the one it sits in, named by its level and number, with its pages by their place
// in the item ("Pg 1–3, 5") and as small scans (each opening the whole scan), and what grouping would flag about it; how many
// there are at the top and in none, and, if asked, only the ones with problems.
function PreviewResult({ preview, levels, bundle }: { preview: Preview; levels: Level[]; bundle: string }) {
  const [onlyProblems, setOnlyProblems] = useState(false);
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
  const problemsOf = (record: string | null) => preview.problems.filter((p) => p.record === record);
  const top = preview.records.filter((r) => !r.parent).length;
  const topWords = recordWords(levels[0]?.name.trim().toLowerCase() || "record");
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const rows = [
    ...(preview.loose.length ? [{ id: null, label: "In no record", pages: preview.loose, depth: 1 }] : []),
    ...preview.records.map((r) => ({ id: r.id, pages: r.pages, depth: depth.get(r.id)!,
      label: `${start(levels[depth.get(r.id)! - 1]?.name.trim().toLowerCase() || "record")} ${recordNumber(r.id, r.parent ?? bundle)}` })),
  ].filter((row) => !onlyProblems || problemsOf(row.id).length);
  return (
    <section className="space-y-3 text-sm" aria-label="Preview" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground">
          {plural(top, topWords.one, topWords.many)} · {plural(preview.loose.length, "page", "pages")} in none · {plural(preview.problems.length, "problem", "problems")}
        </p>
        {preview.problems.length > 0 && (
          <label className="flex items-center gap-2">
            <input type="checkbox" className="size-4 accent-primary" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />
            Only ones with problems
          </label>
        )}
      </div>
      <ol aria-label="Records" className="space-y-3">
        {rows.map((row) => (
          <li key={row.id ?? ""} style={{ marginLeft: `${(row.depth - 1) * 1.5}rem` }} className="space-y-2 rounded-md border p-3">
            <p><span className="font-medium">{row.label}</span><span className="text-muted-foreground"> · {pages(row.pages)}</span></p>
            {problemsOf(row.id).map((p) => (
              <p key={`${p.page} ${p.reason}`} className="text-amber-700 dark:text-amber-400">{p.reason}</p>
            ))}
            {row.pages.length > 0 && (
              <div className="flex flex-wrap gap-3">
                {row.pages.map((page) => (
                  <a key={page} href={`/api/pages/${encodeURIComponent(page)}/image`} target="_blank" rel="noopener noreferrer"
                    className="w-36 space-y-1 text-center text-xs text-muted-foreground hover:text-foreground">
                    <Thumbnail page={page} />
                    <span className="block truncate">{preview.pageTypes[page] ?? "Page"} · Pg {place.get(page)}</span>
                  </a>
                ))}
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
