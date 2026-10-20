import { useCallback, useEffect, useId, useState } from "react";
import { Plus } from "lucide-react";

import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Progress as ProgressBar } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableOpenArrow, TableRow, TableRowLink } from "@/components/ui/table";
import { backendRequest } from "../progress/backend";
import type { Reviewer } from "../review-screen/api";
import Welcome from "./Welcome";

type Collection = {
  id: number; name: string; bundles: number; running: number; failed: number; pages: number; reviewable: number; reviewed: number;
  unknownPages: number; flagged: number;
};

const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

// Home: every collection, each a series with its own page types and bundles; or, until
// this browser knows who is working (onChosen), a welcome that asks.
export default function CollectionsScreen({ onChosen }: { onChosen?: (person: Reviewer) => void }) {
  const [collections, setCollections] = useState<Collection[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [creating, setCreating] = useState(false);

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
              Series, each with its own page types and items.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
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
      <span>{n(c.bundles)} processed</span>
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

// How far a collection's review has got.
function Progress({ collection: c }: { collection: Collection }) {
  const note = (text: string) => <span className="text-muted-foreground">{text}</span>;
  if (!c.reviewable) return note("No pages to review yet");
  const percent = Math.round((c.reviewed / c.reviewable) * 100);
  return (
    <div className="flex max-w-sm flex-col gap-1.5">
      <span>{c.reviewed.toLocaleString()} / {c.reviewable.toLocaleString()} pages · {percent}%</span>
      <ProgressBar className="h-2" aria-label={`${c.name} review progress`} value={percent} aria-valuenow={c.reviewed} max={c.reviewable} />
    </div>
  );
}

// A new collection: its name.
function NewCollectionDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (created: Collection) => void }) {
  const id = useId();
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    setError("");
    let created: Collection;
    try {
      created = await backendRequest<Collection>("/collections", json("POST", { name }));
    } catch (e) {
      setError(message(e, "Could not create the series."));
      setBusy(false);
      return;
    }
    onCreated(created);
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>New series</DialogTitle>
          <DialogDescription>A series, with its own page types and items.</DialogDescription>
        </DialogHeader>
        <FieldGroup className="gap-4">
          <Field>
            <FieldLabel htmlFor={`${id}-name`}>Name</FieldLabel>
            <Input id={`${id}-name`} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
        </FieldGroup>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !name.trim()} onClick={create}>Create series</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
