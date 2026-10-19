import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ExternalLink, Lock, Plus, Settings } from "lucide-react";

import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Progress as ProgressBar } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ARCHIVE, backendRequest } from "../progress/backend";

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

// Home: every collection, each a series on the University of Melbourne Archives with its own page types and bundles.
export default function CollectionsScreen() {
  const [collections, setCollections] = useState<Collection[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    backendRequest<Collection[]>("/collections")
      .then((result) => { setCollections(result); setLoadError(""); })
      .catch((e) => setLoadError(message(e, "Could not load the series.")));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader
        crumbs={[{ label: "Series" }]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => setCreating(true)}><Plus /> New series</Button>
            <Button variant="outline" onClick={() => { window.location.href = "/?view=settings"; }}><Settings /> Settings</Button>
          </div>
        }
      />
      <main className="mx-auto max-w-6xl space-y-6 p-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Series</h1>
          <p className="text-sm text-muted-foreground">
            Series from the University of Melbourne Archives, each with its own page types and items.
          </p>
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {collections.map((c) => (
                // The name's link covers the row; the links in the row sit above it.
                <TableRow key={c.id} className="relative cursor-pointer hover:bg-muted focus-within:bg-muted">
                  <TableCell>
                    <a href={`/?collection=${c.id}`}
                      className="rounded-sm font-medium outline-none after:absolute after:inset-0 hover:underline focus-visible:underline focus-visible:ring-3 focus-visible:ring-ring/50">
                      {c.name}
                    </a>
                  </TableCell>
                  <TableCell className="max-w-72 whitespace-normal">
                    {c.archiveSeries ? (
                      <div className="flex flex-col">
                        <a href={`${ARCHIVE}/nodes/view/${c.archiveSeries}`} target="_blank" rel="noopener noreferrer"
                          className="relative z-10 inline-flex w-fit items-center gap-1 hover:underline">
                          {c.archiveIdentifier ?? `Series ${c.archiveSeries}`} <ExternalLink aria-hidden="true" className="size-3.5" />
                        </a>
                        {c.archiveTitle && <span className="text-muted-foreground">{c.archiveTitle}</span>}
                      </div>
                    ) : "Not linked"}
                  </TableCell>
                  <TableCell><Items collection={c} /></TableCell>
                  <TableCell><Progress collection={c} /></TableCell>
                  <TableCell><Attention collection={c} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </main>
      {creating && (
        <NewCollectionDialog onClose={() => setCreating(false)}
          onCreated={(created) => { window.location.href = `/?collection=${created.id}&view=page-types`; }} />
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

// How far a collection's review has got; until it can be reviewed, the next step of its setup.
function Progress({ collection: c }: { collection: Collection }) {
  const setup = (text: string) => <a href={`/?collection=${c.id}&view=page-types`} className="relative z-10 underline">{text}</a>;
  const note = (text: string) => <span className="text-muted-foreground">{text}</span>;
  if (!c.pageTypes) return setup("Next: add its page types");
  if (!c.templates) return setup("Next: give its page types templates");
  if (!c.bundles) return note("No items processed yet");
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
    try {
      onCreated(await backendRequest<Collection>("/collections", json("POST", {
        name, archiveSeries: address, archiveIdentifier: shown?.series?.identifier, archiveTitle: shown?.series?.title,
        archiveItems: shown?.series?.items ?? undefined,
      })));
    } catch (e) {
      setError(message(e, "Could not create the series."));
      setBusy(false);
    }
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
        </FieldGroup>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
          <Button disabled={busy || node === null || !name.trim()} onClick={create}>Create series</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
