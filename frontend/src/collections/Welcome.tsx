import { useEffect, useId, useState, type FormEvent } from "react";
import { Library, ListChecks } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { keepPerson } from "../person";
import { createReviewer, getReviewers, type Reviewer } from "../review-screen/api";

const STEPS = [
  { icon: Library, text: "Add a series" },
  { icon: ListChecks, text: "Read the rest, then check each record" },
];

// The home page's welcome, until this browser knows who is working: what PrestCribe does, and whose name goes with what's saved
// (one saved before or a new one, kept in this browser).
export default function Welcome({ onChosen }: { onChosen: (person: Reviewer) => void }) {
  const id = useId();
  const [people, setPeople] = useState<Reviewer[] | null>(null);
  const [chosen, setChosen] = useState(""); // a person's id, or "new"
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    getReviewers().then(setPeople).catch(() => setPeople([]));
  }, []);
  const someoneNew = chosen === "new" || people?.length === 0;

  async function go(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const person = someoneNew ? await createReviewer(name) : people!.find((p) => String(p.id) === chosen)!;
      keepPerson(person);
      onChosen(person);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save your name.");
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={`${id}-welcome`} className="grid items-center gap-8 rounded-xl border bg-muted/40 p-6 sm:p-10 lg:grid-cols-[1.3fr_1fr]">
      <div className="space-y-6">
        <div className="space-y-2">
          <img src="/favicon.svg" alt="" className="mb-4 size-20" />
          <h1 id={`${id}-welcome`} className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">Welcome to PrestCribe</h1>
          <p className="text-lg text-muted-foreground text-pretty">Turn scanned archive records into checked, searchable data.</p>
        </div>
        <ol aria-label="How it works" className="space-y-3">
          {STEPS.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-center gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-background">
                <Icon aria-hidden="true" className="size-4.5" />
              </span>
              {text}
            </li>
          ))}
        </ol>
      </div>
      <form onSubmit={go} aria-labelledby={`${id}-who`} className="space-y-4 rounded-lg border bg-card p-6">
        <div className="space-y-1">
          <h2 id={`${id}-who`} className="text-lg font-semibold tracking-tight">Who's working?</h2>
          <p className="text-sm text-muted-foreground">Your name goes with everything you save. This browser remembers it.</p>
        </div>
        {people === null ? <p role="status" className="text-sm text-muted-foreground">Loading…</p> : (
          <>
            {people.length > 0 && (
              <Field>
                <FieldLabel htmlFor={id}>Your name</FieldLabel>
                <NativeSelect id={id} className="w-full" value={chosen} onChange={(e) => setChosen(e.target.value)}>
                  <option value="">Choose your name</option>
                  {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  <option value="new">Someone new…</option>
                </NativeSelect>
              </Field>
            )}
            {someoneNew && (
              <Field>
                <FieldLabel htmlFor={`${id}-new`}>{people.length ? "New name" : "Your name"}</FieldLabel>
                <Input id={`${id}-new`} autoFocus maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
            )}
            {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
            <Button type="submit" className="w-full" disabled={busy || (someoneNew ? !name.trim() : !chosen)}>Continue</Button>
          </>
        )}
      </form>
    </section>
  );
}
