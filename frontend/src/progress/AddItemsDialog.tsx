import { useEffect, useId, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { ADD_ALL_MAX, backendRequest } from "./backend";

const MAX_ADD = 25; // the most one request may add
const LISTED_MAX = 10_000; // the archive lists no further than this
type Listed = { node: number; title: string; identifier: string; scanned: boolean; added: boolean };
type Listing = { items: Listed[]; page: number; pages: number; total: number };
type Added = { added: { node: number; title: string }[]; refused: { node: number; reason: string }[] };
type Result = { added: number; skipped: number };

const itemCount = (n: number) => `${n.toLocaleString()} ${n === 1 ? "item" : "items"}`;
// The primary button's words; a null count (the series' size isn't known) only comes with adding everything.
function primaryLabel(everything: boolean, count: number | null) {
  if (count === null) return "Add all items";
  return everything && count > 1 ? `Add all ${count.toLocaleString()} items` : `Add ${itemCount(count)}`;
}

// Adds a series' items from the archive: all of them at once, or ones chosen from a list. The parent controls whether this dialog exists.
// archiveItems is how many items the series has on the archive, when known.
export default function AddItemsDialog({ collectionId, seriesTitle, archiveItems, onClose, onAdded }: {
  collectionId: number; seriesTitle: string; archiveItems: number | null; onClose: () => void; onAdded: () => void;
}) {
  const id = useId();
  const primary = useRef<HTMLButtonElement>(null);
  // Null until "Choose items instead" opens the list; then the page and search it shows. Each change, even to the same page, fetches again.
  const [request, setRequest] = useState<{ page: number; search: string } | null>(null);
  const [query, setQuery] = useState("");
  // The last list that arrived stays up, dimmed, while the next loads.
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // The chosen items across pages, node to title.
  const [selected, setSelected] = useState<Map<number, string>>(new Map());
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<{ text: string; refused: { node: number; line: string }[] } | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  useEffect(() => {
    if (!request) return;
    let active = true;
    const params = new URLSearchParams({ page: String(request.page) });
    if (request.search) params.set("search", request.search);
    backendRequest<Listing>(`/collections/${collectionId}/archive-items?${params}`)
      .then((page) => {
        if (!active) return;
        setListing(page);
        setLoading(false);
        // An item the list shows as unavailable can't stay chosen.
        setSelected((s) => {
          const next = new Map(s);
          for (const item of page.items) if (item.added || !item.scanned) next.delete(item.node);
          return next;
        });
      })
      .catch((e) => {
        if (!active) return;
        setListing(null);
        setLoading(false);
        setError(e instanceof Error ? e.message : "Could not load items.");
      });
    return () => { active = false; };
  }, [collectionId, request]);
  function openList() {
    setLoading(true);
    setRequest({ page: 1, search: "" });
  }
  function closeList() {
    setRequest(null);
    setListing(null);
    setLoading(false);
    setError("");
    setQuery("");
  }
  function load(next: Partial<{ page: number; search: string }> = {}) {
    setLoading(true);
    setError("");
    setRequest((r) => r && { ...r, ...next });
  }
  function choose(item: Listed, on: boolean) {
    setSelected((s) => {
      const next = new Map(s);
      if (on) next.set(item.node, item.title);
      else next.delete(item.node);
      return next;
    });
  }
  // Ticks the page's items that fit under the cap, or unticks them all.
  function choosePage(page: Listed[], on: boolean) {
    setSelected((s) => {
      const next = new Map(s);
      for (const item of page) {
        if (!on) next.delete(item.node);
        else if (next.size < MAX_ADD) next.set(item.node, item.title);
      }
      return next;
    });
  }
  async function add() {
    setBusy(true);
    setProblem(null);
    try {
      const outcome = await backendRequest<Added>(`/collections/${collectionId}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nodes: [...selected.keys()] }),
      });
      onAdded();
      if (!outcome.refused.length) {
        onClose();
        return;
      }
      setProblem({
        text: "Some items couldn't be added.",
        refused: outcome.refused.map((r) => ({ node: r.node, line: `${selected.get(r.node) ?? r.node}: ${r.reason}` })),
      });
      setSelected((s) => {
        const next = new Map(s);
        for (const item of outcome.added) next.delete(item.node);
        return next;
      });
      load();
    } catch (e) {
      setProblem({ text: e instanceof Error ? e.message : "Could not add the items.", refused: [] });
    } finally {
      setBusy(false);
    }
  }
  // Adds every item of the series, or of a search of it, then tells how it went.
  async function addAll(search: string) {
    setBusy(true);
    setProblem(null);
    try {
      const done = await backendRequest<Result>(`/collections/${collectionId}/items/all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ search }),
      });
      onAdded();
      setResult(done);
    } catch (e) {
      setProblem({ text: e instanceof Error ? e.message : "Could not add the items.", refused: [] });
    } finally {
      setBusy(false);
    }
  }
  const choosing = request !== null;
  const locked = busy || loading;
  const full = selected.size >= MAX_ADD;
  const enabled = listing?.items.filter((i) => i.scanned && !i.added) ?? [];
  const pageChosen = enabled.length > 0 && enabled.every((i) => selected.has(i.node));
  // Before the list is opened, or with nothing ticked in it, the button adds everything.
  const everything = !choosing || selected.size === 0;
  // The archive lists no more than 10,000 of a longer series, so then the series' own count is the list's size.
  const capped = choosing && !request.search && listing !== null && listing.total >= LISTED_MAX && archiveItems !== null && archiveItems > listing.total;
  const count = !choosing ? archiveItems : everything ? ((capped ? archiveItems : null) ?? listing?.total ?? 0) : selected.size;
  const tooMany = everything && count !== null && count > ADD_ALL_MAX;
  return <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
    <DialogContent showCloseButton={false} className="max-h-[90dvh] overflow-y-auto sm:max-w-xl"
      onInteractOutside={(event) => event.preventDefault()}
      // Focus starts on the primary button, or on the dialog itself when that is off; never the search field.
      onOpenAutoFocus={(event) => {
        event.preventDefault();
        const button = primary.current;
        (button && !button.disabled ? button : event.currentTarget as HTMLElement).focus();
      }}>
      <DialogHeader>
        <DialogTitle>Add items</DialogTitle>
        <DialogDescription>Choose items from the archive to add to {seriesTitle}.</DialogDescription>
      </DialogHeader>
      {result ? <>
        <p role="status">
          Added {itemCount(result.added)}.
          {result.skipped > 0 && ` ${result.skipped === 1 ? "1 was" : `${result.skipped.toLocaleString()} were`} skipped (no scans online, or already listed).`}
        </p>
        <DialogFooter><Button onClick={onClose}>Done</Button></DialogFooter>
      </> : <>
        {!choosing && <div className="grid gap-2">
          <p>
            {tooMany ? `${itemCount(archiveItems ?? 0)}: too many to add at once. Choose items instead, or search for the ones you want.`
              : archiveItems === null ? "Add every item this series has on the archive."
              : `${seriesTitle} has ${itemCount(archiveItems)} on the archive.`}
          </p>
          <p className="text-muted-foreground">Items with no scans online are skipped.</p>
          <Button variant="link" className="h-auto w-fit p-0" disabled={busy} onClick={openList}>Choose items instead</Button>
        </div>}
        {choosing && <>
          <Button variant="link" className="h-auto w-fit p-0" disabled={busy} onClick={closeList}>Add all instead</Button>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); load({ page: 1, search: query.trim() }); }}>
            <Input aria-label="Search archive items" placeholder="Search items…" value={query} onChange={(e) => setQuery(e.target.value)} />
            <Button type="submit" variant="outline" disabled={busy}>Search</Button>
          </form>
          {error && <Alert variant="destructive"><AlertDescription className="flex flex-wrap items-center gap-2">{error} <Button variant="outline" size="sm" onClick={() => load()}>Try again</Button></AlertDescription></Alert>}
          {loading && <p role="status" className="flex items-center gap-2 text-muted-foreground"><Spinner role="presentation" aria-hidden="true" />Loading items from the archive…</p>}
          {listing && <div aria-busy={loading} className={`grid gap-4 ${loading ? "opacity-60" : ""}`}>
            {listing.items.length > 0 && <label className="flex cursor-pointer items-center gap-3 px-3">
              <input type="checkbox" className="size-4 shrink-0 accent-primary" checked={pageChosen}
                disabled={locked || !enabled.length || (full && !pageChosen)} onChange={(e) => choosePage(enabled, e.target.checked)} />
              Select all on this page
            </label>}
            {listing.items.length ? <ul className="max-h-[40dvh] divide-y overflow-y-auto rounded-md border">
              {listing.items.map((item) => {
                const checked = selected.has(item.node);
                const note = item.added ? "Added" : !item.scanned ? "No scans online" : "";
                const detail = `${item.identifier} · ${item.node}${note && ` · ${note}`}`;
                const disabled = Boolean(note) || locked || (full && !checked);
                return <li key={item.node}>
                  <label className={`flex items-start gap-3 px-3 py-2 ${disabled ? "" : "cursor-pointer hover:bg-muted"}`}>
                    <input type="checkbox" className="mt-0.5 size-4 shrink-0 accent-primary" checked={checked} disabled={disabled}
                      aria-label={item.title} aria-describedby={`${id}-${item.node}`} onChange={(e) => choose(item, e.target.checked)} />
                    <span className={`min-w-0 ${note ? "opacity-60" : ""}`}>
                      <span className="block font-medium">{item.title}</span>
                      <span id={`${id}-${item.node}`} className="block text-muted-foreground">{detail}</span>
                    </span>
                  </label>
                </li>;
              })}
            </ul> : <p className="text-muted-foreground">No items found.</p>}
            <div className="flex flex-wrap items-center justify-between gap-2 text-muted-foreground">
              <span>{itemCount(listing.total)}</span>
              <div className="flex items-center gap-2">
                {/* Loading marks the pager aria-disabled rather than disabled, so the focused button keeps focus. */}
                <Button variant="outline" size="sm" className="aria-disabled:opacity-50" aria-disabled={loading} disabled={busy || listing.page <= 1}
                  onClick={() => { if (!loading) load({ page: listing.page - 1 }); }}>Previous</Button>
                <span>Page {listing.page} of {listing.pages}</span>
                <Button variant="outline" size="sm" className="aria-disabled:opacity-50" aria-disabled={loading} disabled={busy || listing.page >= listing.pages}
                  onClick={() => { if (!loading) load({ page: listing.page + 1 }); }}>Next <ArrowRight /></Button>
              </div>
            </div>
            {tooMany && <p className="text-muted-foreground">Over 1,000 items: search to narrow the list, or tick the ones you want.</p>}
            {listing.total >= LISTED_MAX && <p className="text-muted-foreground">Showing the first 10,000; search to find others.</p>}
          </div>}
          {full && <p className="text-muted-foreground">Add up to {MAX_ADD} at a time.</p>}
        </>}
        {busy && everything && <p role="status" className="flex items-center gap-2 text-muted-foreground"><Spinner role="presentation" aria-hidden="true" />Adding items… a long list can take a minute.</p>}
        {problem && <Alert variant="destructive"><AlertDescription>
          {problem.text}
          {problem.refused.length > 0 && <ul className="mt-1 list-disc pl-4">{problem.refused.map((r) => <li key={r.node}>{r.line}</li>)}</ul>}
        </AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
          <Button ref={primary} disabled={locked || count === 0 || tooMany}
            onClick={() => void (everything ? addAll(request?.search ?? "") : add())}>
            {busy ? "Adding…" : primaryLabel(everything, count)}
          </Button>
        </DialogFooter>
      </>}
    </DialogContent>
  </Dialog>;
}
