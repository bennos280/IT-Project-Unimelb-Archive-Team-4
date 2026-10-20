import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Download, ExternalLink, FolderOpen, Lock, Plus } from "lucide-react";

import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Progress as ProgressBar } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableOpenArrow, TableRow, TableRowLink } from "@/components/ui/table";
import { ARCHIVE, backendRequest } from "../progress/backend";
import { isSetUp } from "../progress/setup";
import type { Reviewer } from "../review-screen/api";
import SaveFileDialog from "./SaveFileDialog";
import Welcome from "./Welcome";

type Collection = {
  id: number; name: string; archiveSeries: number | null; archiveIdentifier: string | null; archiveTitle: string | null;
  archiveItems: number | null; bundles: number; running: number; failed: number; pages: number; reviewable: number; reviewed: number;
  unknownPages: number; flagged: number; pageTypes: number; templates: number;
};
type Series = { id: number; title: string; identifier: string; date: string; access: string; items: number | null; url: string };
type Lookup = { node: number; series?: Series; error?: string };

const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
// A series' node id from its address on the archive (.../nodes/view/499420) or the number itself; null: neither.
const nodeOf = (text: string) => {
  const found = text.trim().match(/^(?:https?:\/\/archives\.library\.unimelb\.edu\.au\/nodes\/view\/)?([1-9]\d{0,8})\/?$/);
  return found ? Number(found[1]) : null;
};

// Home: every collection, each a series on the University of Melbourne Archives with its own page types and bundles; or, until
// this browser knows who is working (onChosen), a welcome that asks.
export default function CollectionsScreen({ onChosen }: { onChosen?: (person: Reviewer) => void }) {
  const [collections, setCollections] = useState<Collection[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    backendRequest<Collection[]>("/collections")
      .then((result) => { setCollections(result); setLoadError(""); })
      .catch((e) => setLoadError(message(e, "Could not load the series.")));
  }, []);
  useEffect(load, [load]);

  if (onChosen) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <AppHeader />
        <main className="p-6"><Welcome onChosen={onChosen} /></main>
      </div>
    );
  }
  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader />
      <main className="space-y-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Series</h1>
            <p className="text-sm text-muted-foreground">
              Series from the University of Melbourne Archives, each with its own page types and items.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" asChild><a href="/?view=import"><FolderOpen /> Open a PrestCribe file</a></Button>
            <Button variant="outline" onClick={() => setSaving(true)}><Download /> Save a PrestCribe file</Button>
            <Button onClick={() => setCreating(true)}><Plus /> New series</Button>
          </div>
        </div>
        {loadError && (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-2">
              {loadError} <Button variant="outline" size="sm" onClick={load}>Try again</Button>
            </AlertDescription>
          </Alert>
        )}
        {collections && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Series</TableHead>
                <TableHead>On the archive</TableHead>
                <TableHead>Items</TableHead>
                <TableHead>Reviewed</TableHead>
                <TableHead>Needs attention</TableHead>
                <TableHead className="w-10"><span className="sr-only">Open</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {collections.map((c) => (
                <TableRow key={c.id} clickable>
                  <TableCell>
                    <TableRowLink href={`/?series=${c.id}`}>{c.name}</TableRowLink>
                  </TableCell>
                  <TableCell className="max-w-72 whitespace-normal">
                    {c.archiveSeries ? (
                      <div className="flex flex-col">
                        <a href={`${ARCHIVE}/nodes/view/${c.archiveSeries}`} target="_blank" rel="noopener noreferrer"
                          className="inline-flex w-fit items-center gap-1 hover:underline">
                          {c.archiveIdentifier ?? `Series ${c.archiveSeries}`} <ExternalLink aria-hidden="true" className="size-3.5" />
                        </a>
                        {c.archiveTitle && <span className="text-muted-foreground">{c.archiveTitle}</span>}
                      </div>
                    ) : "Not linked"}
                  </TableCell>
                  <TableCell><Items collection={c} /></TableCell>
                  <TableCell><Progress collection={c} /></TableCell>
                  <TableCell><Attention collection={c} /></TableCell>
                  <TableCell><TableOpenArrow /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </main>
      {saving && <SaveFileDialog onClose={() => setSaving(false)} />}
      {creating && (
        <NewCollectionDialog onClose={() => setCreating(false)}
          onCreated={(created) => { window.location.href = `/?series=${created.id}`; }} />
      )}
    </div>
  );
}

// The series' items processed so far (sorted, transcribed and grouped), and any being processed or failed.
function Items({ collection: c }: { collection: Collection }) {
  const n = (count: number) => count.toLocaleString();
  return (
    <div className="flex flex-col">
      <span>{c.archiveItems ? `${n(c.bundles)} of ${n(c.archiveItems)}` : n(c.bundles)} processed</span>
      {c.running > 0 && <span className="text-muted-foreground">{n(c.running)} processing now</span>}
      {c.failed > 0 && <span className="text-destructive">{n(c.failed)} failed</span>}
    </div>
  );
}

// What waits for a person: pages sorting couldn't place, and flags not yet checked.
function Attention({ collection: c }: { collection: Collection }) {
  const n = (count: number) => count.toLocaleString();
  if (!c.unknownPages && !c.flagged) return <span className="text-muted-foreground">Nothing</span>;
  return (
    <div className="flex flex-col">
      {c.unknownPages > 0 && <span>{n(c.unknownPages)} {c.unknownPages === 1 ? "page needs" : "pages need"} a type</span>}
      {c.flagged > 0 && <span>{n(c.flagged)} {c.flagged === 1 ? "flag" : "flags"} to check</span>}
    </div>
  );
}

// How far a collection's review has got; until it's set up, a link to setting it up on its Items page.
function Progress({ collection: c }: { collection: Collection }) {
  const note = (text: string) => <span className="text-muted-foreground">{text}</span>;
  if (!isSetUp(c)) return <a href={`/?series=${c.id}`} className="underline">Next: set up series</a>;
  if (!c.reviewable) return note("No pages to review yet");
  const percent = Math.round((c.reviewed / c.reviewable) * 100);
  return (
    <div className="flex max-w-sm flex-col gap-1.5">
      <span>{c.reviewed.toLocaleString()} / {c.reviewable.toLocaleString()} pages · {percent}%</span>
      <ProgressBar className="h-2" aria-label={`${c.name} review progress`} value={percent} aria-valuenow={c.reviewed} max={c.reviewable} />
    </div>
  );
}

// A new collection: its series on the archive (looked up and shown before it is created) and its name.
function NewCollectionDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (created: Collection) => void }) {
  const id = useId();
  const [address, setAddress] = useState("");
  const [name, setName] = useState("");
  const named = useRef(false); // the name was typed, so a lookup doesn't replace it
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [addItems, setAddItems] = useState(true);
  // The series exists but its items didn't come with it; Continue goes on to the series.
  const [stranded, setStranded] = useState<{ created: Collection; detail: string } | null>(null);
  const node = nodeOf(address);

  // Looks the series up once typing stops; a lookup for an earlier number is ignored.
  useEffect(() => {
    if (node === null) return;
    let current = true;
    const timer = window.setTimeout(() => {
      backendRequest<Series>(`/archive-series/${node}`)
        .then((series) => {
          if (!current) return;
          setLookup({ node, series });
          if (!named.current) setName(series.title);
        })
        .catch((e) => { if (current) setLookup({ node, error: message(e, "Could not look the series up.") }); });
    }, 400);
    return () => { current = false; window.clearTimeout(timer); };
  }, [node]);
  const shown = lookup && lookup.node === node ? lookup : null;

  async function create() {
    setBusy(true);
    setError("");
    let created: Collection;
    try {
      created = await backendRequest<Collection>("/collections", json("POST", {
        name, archiveSeries: address, archiveIdentifier: shown?.series?.identifier, archiveTitle: shown?.series?.title,
        archiveItems: shown?.series?.items ?? undefined,
      }));
    } catch (e) {
      setError(message(e, "Could not create the series."));
      setBusy(false);
      return;
    }
    if (addItems) {
      try {
        await backendRequest<unknown>(`/collections/${created.id}/items/all`, json("POST", { search: "" }));
      } catch (e) {
        setStranded({ created, detail: message(e, "Could not add the items.") });
        return;
      }
    }
    onCreated(created);
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>New series</DialogTitle>
          <DialogDescription>A series on the University of Melbourne Archives, with its own page types and items.</DialogDescription>
        </DialogHeader>
        <FieldGroup className="gap-4">
          <Field>
            <FieldLabel htmlFor={`${id}-series`}>Archive series</FieldLabel>
            <Input id={`${id}-series`} value={address} placeholder={`${ARCHIVE}/nodes/view/123456`} onChange={(e) => setAddress(e.target.value)} />
            <FieldDescription>The series' address on the University of Melbourne Archives, or just the number at its end.</FieldDescription>
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Where do I find it?</summary>
              <div className="mt-2 space-y-2 rounded-lg border p-3">
                <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
                  <li>
                    On <a href={ARCHIVE} target="_blank" rel="noopener noreferrer" className="underline">archives.library.unimelb.edu.au</a>,
                    find the series and open it. A series' identifier starts with UMA-SR.
                  </li>
                  <li>Copy the address from your browser's address bar. The number at its end is the series:</li>
                </ol>
                <div aria-hidden="true" className="flex items-center gap-2 rounded-full border bg-muted px-3 py-1.5 font-mono text-xs">
                  <Lock className="size-3 shrink-0 text-muted-foreground" />
                  <span className="truncate text-muted-foreground">archives.library.unimelb.edu.au/nodes/view/</span>
                  <mark className="rounded bg-yellow-200 px-1 text-foreground dark:bg-yellow-500/40">123456</mark>
                </div>
              </div>
            </details>
            {address.trim() && node === null && <FieldDescription className="text-destructive">That isn't a series address or number.</FieldDescription>}
          </Field>
          {node !== null && !shown && (
            <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner role={undefined} aria-hidden="true" />Looking it up on the archive…</p>
          )}
          {shown?.error && <Alert variant="destructive"><AlertDescription>{shown.error}</AlertDescription></Alert>}
          {shown?.series && (
            <Card size="sm" role="region" aria-label="Archive series">
              <CardContent className="space-y-1 text-sm">
                <p className="font-medium">{shown.series.title || `Page ${shown.series.id}`}</p>
                <p className="text-muted-foreground">
                  {[shown.series.identifier, shown.series.date, shown.series.access].filter(Boolean).join(" · ")}
                </p>
                {shown.series.items !== null && <p>{shown.series.items.toLocaleString()} items in this series</p>}
                {!/^UMA-SRE?-/.test(shown.series.identifier) && (
                  <p className="text-destructive">This isn't a series. Open the series it belongs to and paste that address instead.</p>
                )}
                <a href={shown.series.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline">
                  Open on the archive <ExternalLink aria-hidden="true" className="size-3.5" />
                </a>
              </CardContent>
            </Card>
          )}
          <Field>
            <FieldLabel htmlFor={`${id}-name`}>Name</FieldLabel>
            <Input id={`${id}-name`} value={name} onChange={(e) => { setName(e.target.value); named.current = true; }} />
          </Field>
          <Field>
            <label className="flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" className="size-4 accent-primary" checked={addItems} disabled={busy}
                onChange={(e) => setAddItems(e.target.checked)} />
              Add all its items
            </label>
          </Field>
        </FieldGroup>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        {stranded && (
          <Alert variant="destructive">
            <AlertDescription>The series was created, but its items weren't added: {stranded.detail.replace(/\.$/, "")}. Add them from the series' page.</AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          {stranded ? <Button onClick={() => onCreated(stranded.created)}>Continue</Button> : <>
            <Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
            <Button disabled={busy || node === null || !name.trim()} onClick={create}>Create series</Button>
          </>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
