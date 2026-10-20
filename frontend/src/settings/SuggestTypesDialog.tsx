import { useEffect, useId, useRef, useState } from "react";
import { CircleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { me } from "../person";
import { backendRequest, itemTitle, providerNames, type ArchiveItem } from "../progress/backend";
import type { ModelChoice, ModelData } from "../progress/ModelControls";

type Suggestion = { label: string; description: string; pages: number[] };
type Answer = { pages: number[]; types: Suggestion[] };
type Listed = { items: { name: string; archive: ArchiveItem | null }[] };
type Pick = "spread" | "random" | "range";

const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
// A typed number as a whole one from 1 to most (fallback when nothing, or not a number, is typed).
const whole = (text: string, fallback: number, most = Infinity) => {
  const n = Math.floor(Number(text));
  return text.trim() === "" || Number.isNaN(n) ? fallback : Math.min(most, Math.max(1, n));
};
const PICKS: [Pick, string][] = [["spread", "Spread across the item"], ["random", "At random"], ["range", "A range of pages"]];

// Page types suggested by the transcription model (Settings) from some of one item's pages, which it sees side by side
// (POST /collections/<id>/page-types/suggest; the item's PDF is fetched from the archive first if it isn't here). The ones
// kept, under the names given them here, are added as the series' page types; one the series has already isn't offered.
// onChanged: some were added though not all (the list behind reloads); onAdded: all were.
export default function SuggestTypesDialog({ collectionId, existing, onClose, onChanged, onAdded }: {
  collectionId: number; existing: string[]; onClose: () => void; onChanged: () => void; onAdded: () => void;
}) {
  const id = useId();
  const [items, setItems] = useState<Listed["items"] | null>(null);
  const [model, setModel] = useState<ModelChoice | null | undefined>(undefined); // null: none chosen in Settings
  const [item, setItem] = useState("");
  const [count, setCount] = useState("16"); // as typed; made a whole number when asked
  const [pick, setPick] = useState<Pick>("spread");
  const [first, setFirst] = useState("1");
  const [last, setLast] = useState("20");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState<"" | "asking" | "adding">("");
  const [error, setError] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [labels, setLabels] = useState<(string | null)[]>([]); // per suggestion: the name to add it under, null: left out
  const asking = useRef<AbortController | null>(null);

  useEffect(() => {
    backendRequest<Listed>(`/collections/${collectionId}/items?page=0&size=100`)
      .then((listed) => {
        const archived = listed.items.filter((i) => i.archive); // only the archive's items have scans to fetch
        setItems(archived);
        setItem((chosen) => chosen || archived[0]?.name || "");
      })
      .catch((e) => setError(message(e, "Could not load the series' items.")));
    backendRequest<ModelData>("/transcription-models").then((d) => setModel(d.configured)).catch(() => setModel(null));
  }, [collectionId]);

  const known = new Set(existing.map((label) => label.toLowerCase()));
  const pages = whole(count, 16, 30);
  async function ask() {
    const controller = new AbortController();
    asking.current = controller;
    setBusy("asking");
    setError("");
    try {
      const found = await backendRequest<Answer>(`/collections/${collectionId}/page-types/suggest`, {
        ...json("POST", { item, count: pages, pick, hint, ...(pick === "range" ? { first: whole(first, 1), ...(last.trim() ? { last: whole(last, 1) } : {}) } : {}) }), // no "to": the item's end
        signal: controller.signal });
      setAnswer(found);
      setLabels(found.types.map((t) => (known.has(t.label.toLowerCase()) ? null : t.label)));
    } catch (e) {
      if (controller.signal.aborted) return; // closed while asking
      setError(message(e, "Could not get suggestions."));
    }
    setBusy("");
  }

  // Closing while asking stops waiting for the answer (the model may still finish on the server).
  function close() {
    asking.current?.abort();
    onClose();
  }

  // Each kept one is added in turn and then no longer offered, so a failure part-way can be fixed and Add pressed again.
  async function add() {
    const names = labels.map((label) => label?.trim() || null);
    const kept = names.filter((name): name is string => !!name).map((name) => name.toLowerCase());
    const clash = kept.find((name, i) => known.has(name) || kept.indexOf(name) !== i);
    if (clash) return setError(`"${names.find((n) => n?.toLowerCase() === clash)}" is a page type already, or kept twice: rename it or untick it.`);
    setBusy("adding");
    setError("");
    let added = 0;
    try {
      for (const [i, name] of names.entries()) {
        if (!name) continue;
        await backendRequest("/page-types", json("POST", { label: name, reviewerId: me().id, collectionId }));
        added++;
        setLabels((all) => all.map((label, j) => (j === i ? null : label)));
      }
      onAdded();
    } catch (e) {
      setError(message(e, "Could not add the page types."));
      if (added) onChanged();
      setBusy("");
    }
  }

  const chosen = labels.filter((label) => label?.trim()).length;
  const scan = (n: number) => `/api/collections/${collectionId}/items/${encodeURIComponent(item)}/scans/${n}`;
  return (
    <Dialog open onOpenChange={(open) => { if (!open && busy !== "adding") close(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Suggest page types</DialogTitle>
          <DialogDescription>
            {model ? `${model.model} · ${model.effort} on ${providerNames[model.provider] ?? model.provider}` : "Your transcription model"} looks at
            some of an item's pages and suggests the kinds of page in it.
          </DialogDescription>
        </DialogHeader>
        {model === null && (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertTitle>No transcription model chosen</AlertTitle>
            <AlertDescription>
              <p>Choose a transcription model in <a href="/?view=settings&tab=transcription">Settings</a> first: it's the one asked.</p>
            </AlertDescription>
          </Alert>
        )}
        {!answer ? (
          <FieldGroup className="gap-4">
            <Field>
              <FieldLabel htmlFor={`${id}-item`}>Item to look at</FieldLabel>
              {items?.length === 0 && <p className="text-sm text-muted-foreground">This series has no items from the archive to look at yet.</p>}
              <NativeSelect id={`${id}-item`} className="w-full" value={item} disabled={!items?.length} onChange={(e) => setItem(e.target.value)}>
                {items?.map((i) => <NativeSelectOption key={i.name} value={i.name}>{itemTitle(i.name, i.archive)}</NativeSelectOption>)}
              </NativeSelect>
            </Field>
            <Field>
              <FieldLabel htmlFor={`${id}-count`}>Pages to look at</FieldLabel>
              <Input id={`${id}-count`} type="number" min={1} max={30} className="w-24" value={count}
                onChange={(e) => setCount(e.target.value)} onBlur={() => setCount(String(pages))} />
            </Field>
            <Field>
              <FieldLabel id={`${id}-pick`}>Which pages</FieldLabel>
              <RadioGroup aria-labelledby={`${id}-pick`} value={pick} onValueChange={(v) => setPick(v as Pick)} className="gap-2">
                {PICKS.map(([value, text]) => (
                  <div key={value} className="flex items-center gap-2">
                    <RadioGroupItem value={value} id={`${id}-${value}`} />
                    <label htmlFor={`${id}-${value}`} className="text-sm">{text}</label>
                  </div>
                ))}
              </RadioGroup>
              {pick === "range" && (
                <div className="flex items-center gap-2 pl-6 text-sm">
                  <label htmlFor={`${id}-first`}>From page</label>
                  <Input id={`${id}-first`} type="number" min={1} className="w-20" value={first} onChange={(e) => setFirst(e.target.value)} onBlur={() => setFirst(String(whole(first, 1)))} />
                  <label htmlFor={`${id}-last`}>to</label>
                  <Input id={`${id}-last`} type="number" min={1} className="w-20" value={last} onChange={(e) => setLast(e.target.value)} onBlur={() => setLast(last.trim() ? String(whole(last, 1)) : "")} />
                </div>
              )}
            </Field>
            <Field>
              <FieldLabel htmlFor={`${id}-hint`}>Anything the model should know (optional)</FieldLabel>
              <Textarea id={`${id}-hint`} value={hint} maxLength={1000} placeholder="e.g. Covers and adverts count as their own page types."
                onChange={(e) => setHint(e.target.value)} />
            </Field>
            <p role="status" className={busy ? "text-sm text-muted-foreground" : "sr-only"}>
              {busy === "asking" ? `Asking about ${pages} pages… this can take a minute.` : ""}
            </p>
          </FieldGroup>
        ) : (
          <ol aria-label="Suggested page types" className="space-y-3">
            {answer.types.length === 0 && <li className="text-sm text-muted-foreground">No page types were suggested. Try other pages, or a note.</li>}
            {answer.types.map((t, i) => {
              const already = known.has(t.label.toLowerCase());
              const kept = labels[i] !== null;
              return (
                <li key={`${t.label}-${i}`} className="space-y-2 rounded-md border p-3">
                  <div className="flex items-center gap-3">
                    <input type="checkbox" className="size-4" aria-label={`Add ${t.label}`} checked={kept} disabled={already}
                      onChange={(e) => setLabels((all) => all.map((l, j) => (j === i ? (e.target.checked ? t.label : null) : l)))} />
                    <Input aria-label={`Name for ${t.label}`} className="h-8 max-w-xs" value={labels[i] ?? t.label} disabled={!kept}
                      onChange={(e) => setLabels((all) => all.map((l, j) => (j === i ? e.target.value : l)))} />
                    {already && <span className="text-sm text-muted-foreground">Already a page type</span>}
                  </div>
                  {t.description && <p className="text-sm text-muted-foreground">{t.description}</p>}
                  {t.pages.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {t.pages.slice(0, 6).map((n) => <img key={n} src={scan(n)} alt={`Page ${n}`} className="h-24 rounded border" />)}
                      {t.pages.length > 6 && <span className="self-end text-xs text-muted-foreground">and {t.pages.length - 6} more</span>}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        <DialogFooter>
          {answer && <Button variant="outline" disabled={!!busy} onClick={() => { setAnswer(null); setError(""); }}>Ask again</Button>}
          <Button variant="outline" disabled={busy === "adding"} onClick={close}>Cancel</Button>
          {!answer
            ? <Button disabled={!!busy || !item || !model} onClick={ask}>{busy === "asking" ? "Asking…" : "Suggest"}</Button>
            : <Button disabled={!!busy || !chosen} onClick={add}>{busy === "adding" ? "Adding…" : `Add ${chosen} page type${chosen === 1 ? "" : "s"}`}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
