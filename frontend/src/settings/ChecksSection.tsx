import { useCallback, useEffect, useId, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { me } from "../person";
import { backendRequest } from "../progress/backend";
import { fieldsOf, parseTemplate } from "./rules";
import {
  cleanCheck, newCheck, ops, sentence, states, unfinished, type Check, type CheckVersion, type FieldChoice, type Op, type State,
} from "./seriesChecks";

type PageType = { name: string; label: string; unknown: boolean };
const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
const same = (a: Check[], b: Check[]) => JSON.stringify(a.map(cleanCheck)) === JSON.stringify(b.map(cleanCheck));

// A series' checks across fields: listed in words, added and changed with a builder, switched on and off, saved together as a new
// version (an older one can be brought back), and run over the series' pages again as a task.
export default function ChecksSection({ collectionId, types }: {
  collectionId: number; types: PageType[];
}) {
  const [versions, setVersions] = useState<CheckVersion[] | null>(null); // newest first
  const [choices, setChoices] = useState<FieldChoice[]>([]);
  const [checks, setChecks] = useState<Check[]>([]);
  const [editing, setEditing] = useState<{ check: Check; at: number } | null>(null); // at -1: a new one
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [queued, setQueued] = useState<number | null>(null);
  const newest = versions?.[0] ?? null;

  const load = useCallback(() => {  // the saved checks, over any unsaved changes
    backendRequest<CheckVersion[]>(`/collections/${collectionId}/checks`)
      .then((loaded) => { setVersions(loaded); setChecks(loaded[0]?.checks ?? []); })
      .catch((e) => setError(message(e, "Could not load the checks.")));
  }, [collectionId]);
  useEffect(load, [load]);
  useEffect(() => {  // the fields to choose from, again when a page type changes, keeping unsaved checks
    backendRequest<Record<string, { body: string }>>("/instructions")
      .then((texts) => setChoices(types.filter((t) => !t.unknown && texts[t.name]).map((t) => ({
        type: t.name, label: t.label, fields: fieldsOf(parseTemplate(texts[t.name].body) ?? {}).map(([path]) => path),
      }))))
      .catch((e) => setError(message(e, "Could not load the page types' fields.")));
  }, [types]);

  const changed = versions !== null && !same(checks, newest?.checks ?? []);

  async function save() {
    setBusy(true);
    setError("");
    try {
      await backendRequest(`/collections/${collectionId}/checks`, json("POST", {
        checks: checks.map(cleanCheck), basedOn: newest?.id ?? null, reviewerId: me().id, note: note.trim() || null }));
      setNote("");
      load();
    } catch (e) {
      setError(message(e, "Could not save the checks."));
    }
    setBusy(false);
  }

  async function checkAgain() {
    setBusy(true);
    setError("");
    try {
      setQueued((await backendRequest<{ id: number }>(`/collections/${collectionId}/check`, { method: "POST" })).id);
    } catch (e) {
      setError(message(e, "Could not start checking the series."));
    }
    setBusy(false);
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Checks</h2>
          <p className="text-sm text-muted-foreground">
            Rules across fields, on one page or across a record's pages. A value failing one is flagged for review.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" disabled={!choices.length} onClick={() => setEditing({ check: newCheck(), at: -1 })}>Add check</Button>
          <Button variant="outline" disabled={busy || queued !== null} onClick={checkAgain}>Check again</Button>
        </div>
      </div>
      {queued !== null && (
        <p role="status" className="text-sm text-muted-foreground">
          Checking the series' pages again: <a className="underline" href={`/?view=tasks&task=${queued}`}>see the task</a>.
        </p>
      )}
      {error && <Alert variant="destructive"><AlertDescription className="whitespace-pre-line">{error}</AlertDescription></Alert>}
      {versions && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Check</TableHead>
              <TableHead>Flag says</TableHead>
              <TableHead className="w-12">On</TableHead>
              <TableHead className="w-0"><span className="sr-only">Actions</span></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {checks.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  {choices.length ? "No checks yet." : "Give a page type a template first: checks compare its fields."}
                </TableCell>
              </TableRow>
            ) : checks.map((check, at) => (
              <TableRow key={check.id}>
                <TableCell className="whitespace-normal [overflow-wrap:anywhere]">{sentence(check, choices)}</TableCell>
                <TableCell className="whitespace-normal">{check.message || <span className="text-muted-foreground">Says what failed</span>}</TableCell>
                <TableCell>
                  <input type="checkbox" className="size-4 accent-primary" aria-label={`${sentence(check, choices)} on`} checked={check.on !== false}
                    onChange={(e) => setChecks(checks.map((c, n) => (n === at ? { ...c, on: e.target.checked } : c)))} />
                </TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" aria-label={`Edit ${sentence(check, choices)}`} onClick={() => setEditing({ check, at })}>Edit</Button>
                    <Button variant="outline" size="sm" aria-label={`Remove ${sentence(check, choices)}`}
                      onClick={() => setChecks(checks.filter((_, n) => n !== at))}>Remove</Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {changed && (
        <div className="flex max-w-3xl flex-wrap items-end gap-2">
          <Field className="min-w-56 flex-1">
            <FieldLabel htmlFor="checks-note">Note</FieldLabel>
            <Input id="checks-note" placeholder="What changed, e.g. added the rooms check" value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <Button variant="outline" disabled={busy} onClick={() => setChecks(newest?.checks ?? [])}>Discard</Button>
          <Button disabled={busy} onClick={save}>Save checks</Button>
        </div>
      )}
      {versions && versions.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">History ({versions.length} {versions.length === 1 ? "version" : "versions"})</summary>
          <Table className="mt-2">
            <TableHeader>
              <TableRow>
                <TableHead>Version</TableHead>
                <TableHead>Saved</TableHead>
                <TableHead>By</TableHead>
                <TableHead>Checks</TableHead>
                <TableHead>Note</TableHead>
                <TableHead className="w-0"><span className="sr-only">Use</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {versions.map((v, n) => (
                <TableRow key={v.id}>
                  <TableCell className="font-medium">{v.number}</TableCell>
                  <TableCell className="text-muted-foreground">{v.createdAt ? new Date(v.createdAt).toLocaleString() : ""}</TableCell>
                  <TableCell>{v.reviewer}</TableCell>
                  <TableCell>{v.checks.length}</TableCell>
                  <TableCell className="whitespace-normal">{v.note}</TableCell>
                  <TableCell>
                    {n === 0 ? <span className="text-muted-foreground">Current</span> : (
                      <Button variant="outline" size="sm" aria-label={`Use checks version ${v.number}`} onClick={() => setChecks(v.checks)}>
                        Use this version
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-2 text-muted-foreground">Using an older version fills it in above; saving makes it the newest.</p>
        </details>
      )}
      {editing && (
        <CheckDialog check={editing.check} choices={choices} onClose={() => setEditing(null)} onDone={(done) => {
          setChecks(editing.at === -1 ? [...checks, done] : checks.map((c, n) => (n === editing.at ? done : c)));
          setEditing(null);
        }} />
      )}
    </section>
  );
}

// A field of the series to choose, by page type.
function FieldSelect({ label, value, choices, onChange }: { label: string; value: string; choices: FieldChoice[]; onChange: (value: string) => void }) {
  return (
    <NativeSelect aria-label={label} className="w-full" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Choose a field</option>
      {choices.map((c) => (
        <optgroup key={c.type} label={c.label}>
          {c.fields.map((f) => <option key={f} value={`${c.type}.${f}`}>{f}</option>)}
        </optgroup>
      ))}
    </NativeSelect>
  );
}

// Fields added up on one side of a comparison.
function Side({ name, fields, choices, onChange }: { name: string; fields: string[]; choices: FieldChoice[]; onChange: (fields: string[]) => void }) {
  return (
    <div className="space-y-1.5">
      {fields.map((field, n) => (
        <div key={n} className="flex items-center gap-2">
          {n > 0 && <span className="text-muted-foreground">+</span>}
          <FieldSelect label={`${name} field ${n + 1}`} value={field} choices={choices}
            onChange={(value) => onChange(fields.map((f, m) => (m === n ? value : f)))} />
          {n > 0 && <Button variant="outline" size="sm" aria-label={`Remove ${name} field ${n + 1}`} onClick={() => onChange(fields.filter((_, m) => m !== n))}>×</Button>}
        </div>
      ))}
      <Button variant="ghost" size="sm" aria-label={`Add a ${name} field to sum`} onClick={() => onChange([...fields, ""])}>+ Add a field to sum</Button>
    </div>
  );
}

// Builds one check: a comparison of fields (added up) with fields or a value, or "if a field is so, another must be".
function CheckDialog({ check, choices, onClose, onDone }: {
  check: Check; choices: FieldChoice[]; onClose: () => void; onDone: (check: Check) => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState<Check>(check);
  const set = (change: Partial<Check>) => setDraft({ ...draft, ...change });
  const missing = unfinished(draft, choices);
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{check.left?.some(Boolean) || check.if ? "Edit check" : "Add check"}</DialogTitle>
          <DialogDescription>Flags the fields it names when a record's values fail it. A comparison skips a value that's empty or unreadable; an if-then check flags one that should be filled.</DialogDescription>
        </DialogHeader>
        <FieldGroup className="gap-4">
          <Field>
            <FieldLabel htmlFor={`${id}-kind`}>Kind</FieldLabel>
            <NativeSelect id={`${id}-kind`} className="w-full" value={draft.kind} onChange={(e) => set(e.target.value === "if"
              ? { kind: "if", if: "", is: "filled", then: "", must: "filled" } : { kind: "compare", left: [""], op: "=", right: [""], value: undefined })}>
              <option value="compare">Compare fields</option>
              <option value="if">If a field is so, another must be</option>
            </NativeSelect>
          </Field>
          {draft.kind === "compare" ? (
            <>
              <Field>
                <FieldTitle>Compare</FieldTitle>
                <Side name="Compare" fields={draft.left ?? [""]} choices={choices} onChange={(left) => set({ left })} />
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-op`}>Comparison</FieldLabel>
                <NativeSelect id={`${id}-op`} className="w-full" value={draft.op} onChange={(e) => set({ op: e.target.value as Op })}>
                  {Object.entries(ops).map(([op, sign]) => <option key={op} value={op}>{sign}</option>)}
                </NativeSelect>
                <FieldDescription>
                  Numbers and dates compare as such; other values only as the same (=) or different (≠), ignoring case, spaces and
                  punctuation. Names: the field is the name the other field's code has in its list (its rule's values, as code = name).
                </FieldDescription>
                {draft.op !== "names" && (
                  <NativeSelect aria-label="Compare as" className="w-full" value={draft.as ?? "values"}
                    onChange={(e) => set({ as: e.target.value === "codes" ? "codes" : undefined })}>
                    <option value="values">As values</option>
                    <option value="codes">As codes: digits only, leading zeros ignored; anything else can't be told</option>
                  </NativeSelect>
                )}
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-with`}>With</FieldLabel>
                <NativeSelect id={`${id}-with`} className="w-full" value={draft.value === undefined ? "fields" : "value"}
                  onChange={(e) => set(e.target.value === "value" ? { value: "", right: undefined } : { value: undefined, right: [""] })}>
                  <option value="fields">Fields</option>
                  <option value="value">A value</option>
                </NativeSelect>
                {draft.value === undefined
                  ? <Side name="With" fields={draft.right ?? [""]} choices={choices} onChange={(right) => set({ right })} />
                  : <Input aria-label="Value" placeholder="e.g. 11, or 4 August 1914" value={draft.value} onChange={(e) => set({ value: e.target.value })} />}
              </Field>
            </>
          ) : (
            <>
              <Field>
                <FieldTitle>If</FieldTitle>
                <div className="flex flex-wrap gap-2">
                  <div className="min-w-56 flex-1"><FieldSelect label="If field" value={draft.if ?? ""} choices={choices} onChange={(value) => set({ if: value })} /></div>
                  <NativeSelect aria-label="If it" value={draft.is} onChange={(e) => set({ is: e.target.value as State })}>
                    {Object.entries(states).map(([state, [is]]) => <option key={state} value={state}>{is}</option>)}
                  </NativeSelect>
                  {draft.is === "is" && <Input aria-label="If value" className="w-48" placeholder="e.g. Killed" value={draft.isValue ?? ""} onChange={(e) => set({ isValue: e.target.value })} />}
                </div>
              </Field>
              <Field>
                <FieldTitle>Then</FieldTitle>
                <div className="flex flex-wrap gap-2">
                  <div className="min-w-56 flex-1"><FieldSelect label="Then field" value={draft.then ?? ""} choices={choices} onChange={(value) => set({ then: value })} /></div>
                  <NativeSelect aria-label="It must" value={draft.must} onChange={(e) => set({ must: e.target.value as State })}>
                    {Object.entries(states).map(([state, [, must]]) => <option key={state} value={state}>must {must}</option>)}
                  </NativeSelect>
                  {draft.must === "is" && <Input aria-label="Then value" className="w-48" value={draft.mustValue ?? ""} onChange={(e) => set({ mustValue: e.target.value })} />}
                </div>
              </Field>
            </>
          )}
          <Field>
            <FieldLabel htmlFor={`${id}-message`}>Flag says</FieldLabel>
            <Input id={`${id}-message`} placeholder="Optional: otherwise it says what failed, e.g. Living + Bedrooms (2 + 3) should equal Total rooms (6)"
              value={draft.message ?? ""} onChange={(e) => set({ message: e.target.value })} />
          </Field>
          {!missing && <p className="text-sm"><span className="text-muted-foreground">Reads: </span>{sentence(draft, choices)}</p>}
        </FieldGroup>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={Boolean(missing)} title={missing} onClick={() => onDone(cleanCheck(draft))}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
