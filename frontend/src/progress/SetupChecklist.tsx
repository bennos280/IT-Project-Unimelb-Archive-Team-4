import { useEffect, useState } from "react";
import { Circle, CircleCheck, LoaderCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress as ProgressBar } from "@/components/ui/progress";
import { backendRequest, itemTitle } from "./backend";
import { isSetUp, setUpSteps, type SeriesCounts } from "./setup";

type PageType = { name: string; label: string; unknown: boolean; templateVersion: number | null };
type Step = { title: string; done: boolean; busy?: boolean; optional?: boolean; detail?: string; action?: { label: string; href: string } };

const list = (words: string[]) => (words.length > 1 ? `${words.slice(0, -1).join(", ")} and ${words.at(-1)}` : words[0] ?? "");

// Setting a series up, at the top of its Items page: each step ticked from what the series has, with what's missing and where
// to do it. Once set up, it points to the item read as a sample, until another is read. It loads again when the page is shown
// again, and every few seconds while an item is being read.
export default function SetupChecklist({ collectionId }: { collectionId: number }) {
  const [found, setFound] = useState<{ series: SeriesCounts; types: PageType[]; read: { id: string; name: string }[] } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    Promise.all([
      backendRequest<SeriesCounts>(`/collections/${collectionId}`),
      backendRequest<PageType[]>(`/page-types?collection=${collectionId}`),
      backendRequest<{ id: string; name: string }[]>(`/export/bundles?collection=${collectionId}`),
    ]).then(([series, types, read]) => { if (current) setFound({ series, types, read }); }).catch(() => {});
    return () => { current = false; };
  }, [collectionId, attempt]);
  useEffect(() => {
    const again = () => setAttempt((n) => n + 1);
    window.addEventListener("focus", again);
    window.addEventListener("pageshow", again);
    return () => { window.removeEventListener("focus", again); window.removeEventListener("pageshow", again); };
  }, []);
  const running = found?.series.running ?? 0;
  const hidden = !found || (isSetUp(found.series) && found.series.bundles > 1);
  useEffect(() => {
    if (!running || hidden) return;
    const timer = window.setInterval(() => setAttempt((n) => n + 1), 5000);
    return () => window.clearInterval(timer);
  }, [running, hidden]);
  if (hidden) return null;

  const done = setUpSteps(found.series);
  const own = found.types.filter((t) => !t.unknown);
  const missing = own.filter((t) => !t.templateVersion).map((t) => t.label);
  const setup = `/?collection=${collectionId}&view=setup`;
  const sample = found.read[0];
  const steps: Step[] = [
    { title: "Add its page types", done: done.types, detail: done.types ? list(own.map((t) => t.label)) : "The kinds of page in it, like a form or a letter.",
      action: done.types ? undefined : { label: "Add page types", href: `${setup}&section=page-types` } },
    { title: "Give each page type a template", done: done.templates,
      detail: done.templates ? undefined : missing.length ? `${list(missing)} ${missing.length === 1 ? "has" : "have"} none yet.` : "What to read from each kind of page.",
      action: done.templates ? undefined : { label: "Write templates", href: `${setup}&section=page-types` } },
    { title: "Read one item as a sample", done: done.sample, busy: !done.sample && running > 0,
      detail: done.sample ? (sample ? itemTitle(sample.name) : undefined) : running ? "Reading…" : "Press Transcribe on one of its items below.",
      action: done.sample && sample ? { label: "Check it", href: `/?collection=${collectionId}&bundle=${encodeURIComponent(sample.name)}` } : undefined },
    { title: "Say what a record is", done: done.record, optional: true,
      detail: done.record ? undefined : "Without it, each item is one record.", action: done.record ? undefined : { label: "Set levels", href: setup } },
  ];
  const required = steps.filter((s) => !s.optional);
  const count = required.filter((s) => s.done).length;
  const ready = count === required.length;
  return (
    <section aria-labelledby="setup-checklist" className="space-y-4 rounded-lg border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="setup-checklist" className="text-lg font-semibold tracking-tight">{ready ? "Series set up" : "Set up series"}</h2>
          <p className="text-sm text-muted-foreground">
            {ready ? "Check the sample came out right, then read the other items." : `${count} of ${required.length} done`}
          </p>
        </div>
        <ProgressBar className="h-2 w-40" aria-label="Setup progress" value={(count / required.length) * 100} />
      </div>
      <ol aria-label="Setup steps" className="divide-y rounded-md border">
        {steps.map((s) => (
          <li key={s.title} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
            {s.busy ? <LoaderCircle aria-hidden="true" className="size-5 shrink-0 animate-spin text-muted-foreground" />
              : s.done ? <CircleCheck aria-hidden="true" className="size-5 shrink-0 text-emerald-600" />
              : <Circle aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />}
            <div className="min-w-0 flex-1">
              <p className="font-medium">
                {s.title}<span className="sr-only">{s.done ? ": done" : ": to do"}</span>
                {s.optional && <Badge variant="secondary" className="ml-2">Optional</Badge>}
              </p>
              {s.detail && <p className="text-muted-foreground">{s.detail}</p>}
            </div>
            {s.action && (
              <Button variant="outline" size="sm" asChild><a href={s.action.href}>{s.action.label}</a></Button>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
