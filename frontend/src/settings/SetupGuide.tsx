import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import SetupChecklist from "../progress/SetupChecklist";
import { backendRequest, itemTitle, type ArchiveItem } from "../progress/backend";

type Listed = { items: { name: string; archive: ArchiveItem | null }[]; page: number; total: number };
const MOVES: Record<string, number> = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1, Home: -Infinity, End: Infinity };

const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

// A series' Setup tab until it is set up: one of its items as a sample, every page of it on screen (its PDF fetched from the
// archive first, if it isn't here), beside the steps of setting the series up. The sample is the first item listed, or the one
// chosen with the arrows (?sample=, counting from 1; past the last, the last). Its pages are one tab stop, moved through by the
// arrow keys, Home and End.
export default function SetupGuide({ collectionId }: { collectionId: number }) {
  const [index, setIndex] = useState(() => Math.max(Number(new URLSearchParams(location.search).get("sample")) || 1, 1) - 1);
  const [listed, setListed] = useState<Listed | null>(null);
  const [scans, setScans] = useState<{ of: string; pages: number } | null>(null);
  const [shown, setShown] = useState({ of: "", page: 1 }); // the page looked at, of which item
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const item = listed?.items[0];
  const name = item?.name;
  const pages = scans && scans.of === name ? scans.pages : null;
  const page = shown.of === name ? shown.page : 1;
  const setPage = (n: number) => setShown({ of: name!, page: n });
  const strip = useRef<HTMLOListElement>(null);

  useEffect(() => {
    let current = true;
    backendRequest<Listed>(`/collections/${collectionId}/items?page=${index}&size=1`)
      .then((found) => { if (current) setListed(found); })
      .catch((e) => { if (current) setError(message(e, "Could not load the series' items.")); });
    return () => { current = false; };
  }, [collectionId, index, attempt]);
  useEffect(() => {
    if (!name) return;
    let current = true;
    backendRequest<{ pages: number }>(`/collections/${collectionId}/items/${name}/scans`)
      .then((found) => { if (current) setScans({ of: name, pages: found.pages }); })
      .catch((e) => { if (current) setError(message(e, "Could not get its scans.")); });
    return () => { current = false; };
  }, [collectionId, name, attempt]);

  function again() {
    setError("");
    setAttempt((n) => n + 1);
  }
  function choose(next: number) {
    setError("");
    const url = new URL(location.href);
    if (next) url.searchParams.set("sample", String(next + 1));
    else url.searchParams.delete("sample");
    history.replaceState(null, "", url);
    setIndex(next);
  }
  function move(e: KeyboardEvent) {
    if (!(e.key in MOVES)) return;
    e.preventDefault();
    const next = Math.min(Math.max(page + MOVES[e.key], 1), pages!);
    setPage(next);
    strip.current?.querySelectorAll("button")[next - 1]?.focus();
  }
  const at = listed?.page ?? index; // the item shown: one asked for past the last is the last
  const scan = (n: number, width: number) => `/api/collections/${collectionId}/items/${name}/scans/${n}?width=${width}`;
  const total = listed?.total ?? 0;
  const numbers = Array.from({ length: pages ?? 0 }, (_, i) => i + 1);

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_26rem]">
      <section aria-labelledby="setup-sample" className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 id="setup-sample" className="text-lg font-semibold tracking-tight [overflow-wrap:anywhere]">
              {item ? `Sample: ${itemTitle(item.name, item.archive)}` : "Sample"}
            </h2>
            <p className="text-sm text-muted-foreground">
              {total ? `Item ${(at + 1).toLocaleString()} of ${total.toLocaleString()}${pages ? ` · ${pages} ${pages === 1 ? "page" : "pages"}` : ""}` : "\u00a0"}
            </p>
          </div>
          {total > 1 && (
            <div className="flex gap-1">
              <Button variant="outline" size="icon-sm" aria-label="Previous item" disabled={at === 0} onClick={() => choose(at - 1)}>
                <ChevronLeft />
              </Button>
              <Button variant="outline" size="icon-sm" aria-label="Next item" disabled={at >= total - 1} onClick={() => choose(at + 1)}>
                <ChevronRight />
              </Button>
            </div>
          )}
        </div>
        {error ? (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-2">
              {error} <Button variant="outline" size="sm" onClick={again}>Try again</Button>
            </AlertDescription>
          </Alert>
        ) : listed && !item ? (
          <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            Add items to the series first, on its <a className="text-primary underline-offset-4 hover:underline" href={`/?collection=${collectionId}`}>Items</a> page,
            then set it up on one of them.
          </p>
        ) : pages === null ? (
          <p role="status" className="flex items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-sm text-muted-foreground">
            <Spinner /> {item ? "Getting its scans from the archive…" : "Loading…"}
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-[5.5rem_minmax(0,1fr)]">
            <ol ref={strip} aria-label="Pages" className="flex gap-2 overflow-x-auto pb-1 sm:max-h-[80vh] sm:flex-col sm:overflow-x-visible sm:overflow-y-auto sm:pb-0 sm:pr-1">
              {numbers.map((n) => (
                <li key={n} className="shrink-0">
                  <button type="button" aria-label={`Page ${n}`} aria-current={n === page ? "true" : undefined} tabIndex={n === page ? 0 : -1}
                    onClick={() => setPage(n)} onKeyDown={move}
                    className={`block w-20 overflow-hidden rounded-md border bg-muted outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ${
                      n === page ? "ring-2 ring-primary" : "hover:border-foreground/40"}`}>
                    <img src={scan(n, 240)} alt="" loading="lazy" className="h-28 w-20 object-cover object-top" />
                    <span className="block border-t bg-background py-0.5 text-center text-xs text-muted-foreground">{n}</span>
                  </button>
                </li>
              ))}
            </ol>
            <figure className="min-w-0 space-y-2 rounded-lg bg-muted/50 p-3">
              <img src={scan(page, 1200)} alt={`Page ${page} of ${pages}`}
                className="mx-auto max-h-[80vh] w-auto max-w-full rounded-sm border bg-background object-contain" />
              <figcaption aria-live="polite" className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                <Button variant="ghost" size="icon-sm" aria-label="Previous page" disabled={page === 1} onClick={() => setPage(page - 1)}>
                  <ChevronLeft />
                </Button>
                Page {page} of {pages}
                <Button variant="ghost" size="icon-sm" aria-label="Next page" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                  <ChevronRight />
                </Button>
              </figcaption>
            </figure>
          </div>
        )}
      </section>
      <SetupChecklist collectionId={collectionId} inSetup sample={name} />
    </div>
  );
}
