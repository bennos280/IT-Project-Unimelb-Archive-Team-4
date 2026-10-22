import { useEffect, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";

import AppHeader from "@/components/AppHeader";
import SeriesHeader, { type SeriesSummary } from "@/components/SeriesHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backendRequest, seriesParam } from "./backend";
import type { ModelData } from "./ModelControls";
import VersionDialog from "./VersionDialog";
import { versionName, type Version } from "./versions";

// GET /accuracy: one row per model, effort, page type and prompt and template version, from the pages reviewers saved since they were read
type Accuracy = { model: string; effort: string | null; pageType: string; promptVersion: number | null;
  templateVersion: number | null; pages: number; fields: number; changed: number };
type Count = { pages: number; fields: number; changed: number };
// GET /page-types: templateVersion is the id of its newest template, null without one
type PageType = { name: string; label: string; unknown: boolean; templateVersion: number | null };
type Versions = Version[] | null | undefined; // undefined: loading; null: failed
// What was read with one model, effort, page type and prompt and template version, joined to what reviewers changed of it
type SetUp = { model: string; effort: string | null; pageType: string; prompt: number | null; template: number | null; providers: string[];
  read: number | null; timed: number; time: number; reviewed: Count | null };

// Fewer reviewed pages than this are too few to rely on the figure.
const RELIABLE_PAGES = 30;
const NUMBER = "text-right tabular-nums";

const share = (row: Pick<Count, "fields" | "changed">) => (row.fields ? (row.fields - row.changed) / row.fields : -1);
const percent = (row: Pick<Count, "fields" | "changed">) => (row.fields ? `${(100 * share(row)).toFixed(1)}%` : "No fields");
const n = (count: number) => count.toLocaleString();
const sum = (rows: Count[]): Count => rows.reduce((all, row) => ({ pages: all.pages + row.pages, fields: all.fields + row.fields, changed: all.changed + row.changed }),
  { pages: 0, fields: 0, changed: 0 });
// the last `numbers` labels are numbers, aligned right
const head = (labels: string[], numbers = 0) => (
  <TableHeader><TableRow>{labels.map((label, i) => (
    <TableHead key={label} className={`whitespace-normal${i >= labels.length - numbers ? " text-right" : ""}`}>{label}</TableHead>
  ))}</TableRow></TableHeader>
);
const title = (v: Version) => `${versionName(v)} v${v.number}`;

// A version as a button that opens its text; it says its number unless given other words.
function VersionButton({ version, text, open }: { version: Version; text?: string; open: (v: Version) => void }) {
  return <Button variant="link" className="h-auto p-0" aria-label={text ? undefined : title(version)} onClick={() => open(version)}>{text ?? `v${version.number}`}</Button>;
}

// A table cell with a version's button; the id itself while the versions are not loaded.
function VersionCell({ id, versions, open }: { id: number | null; versions: Versions; open: (v: Version) => void }) {
  const version = versions?.find((v) => v.id === id);
  return <TableCell>{id === null ? "Not recorded" : !version ? id : <VersionButton version={version} open={open} />}</TableCell>;
}

// Marks a part of the next run that differs from what was read so far.
const Changed = () => <Badge variant="secondary" className="bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">changed</Badge>;

const Muted = ({ children }: { children: ReactNode }) => <span className="text-muted-foreground">{children}</span>;

// A part of the next run, with the mark when it differs from what was read so far.
const Next = ({ changed, children }: { changed?: boolean; children: ReactNode }) => (
  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">{children}{changed && <Changed />}</div>
);

// One row of the comparison: what was read so far, what the next run will use, and where to change it.
const Row = ({ label, left, right, action }: { label: string; left: ReactNode; right: ReactNode; action?: ReactNode }) => (
  <TableRow>
    <TableHead scope="row" className="whitespace-normal">{label}</TableHead>
    <TableCell className="whitespace-normal [overflow-wrap:anywhere]">{left}</TableCell>
    <TableCell className="whitespace-normal [overflow-wrap:anywhere]">{right}</TableCell>
    <TableCell className="text-right">{action}</TableCell>
  </TableRow>
);

// A figure with what it is made of.
function Figure({ count, testId }: { count: Count; testId: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span data-testid={testId} className="text-2xl font-semibold tabular-nums">{percent(count)}</span>
      <Muted>({n(count.changed)} of {n(count.fields)} fields, {n(count.pages)} {count.pages === 1 ? "page" : "pages"})</Muted>
    </div>
  );
}

// What was read and what was reviewed, one row for each model, effort, page type and prompt and template version, a page type's
// rows together, the one read most first, its newest template and prompt first.
function setUps(models: ModelData | null | undefined, rows: Accuracy[], versions: Versions) {
  const all = new Map<string, SetUp>();
  const get = (r: Pick<Accuracy, "model" | "effort" | "promptVersion" | "templateVersion">, pageType: string) => {
    const key = JSON.stringify([r.model, r.effort, pageType, r.promptVersion, r.templateVersion]);
    if (!all.has(key)) all.set(key, { model: r.model, effort: r.effort, pageType, prompt: r.promptVersion, template: r.templateVersion, providers: [],
      read: null, timed: 0, time: 0, reviewed: null });
    return all.get(key)!;
  };
  for (const m of models?.models ?? []) {
    const one = get(m, versions?.find((v) => v.id === m.templateVersion)?.kind ?? "");
    one.read = (one.read ?? 0) + m.pages;
    if (m.provider && !one.providers.includes(m.provider)) one.providers.push(m.provider);
    if (m.averageSeconds !== null) { one.timed += m.pages; one.time += m.pages * m.averageSeconds; }
  }
  for (const r of rows) get(r, r.pageType).reviewed = r;
  const read = new Map<string, number>();
  for (const s of all.values()) read.set(s.pageType, (read.get(s.pageType) ?? 0) + (s.read ?? 0));
  return [...all.values()].sort((a, b) => (read.get(b.pageType)! - read.get(a.pageType)!) || a.pageType.localeCompare(b.pageType)
    || (b.template ?? -1) - (a.template ?? -1) || (b.prompt ?? -1) - (a.prompt ?? -1) || (b.read ?? 0) - (a.read ?? 0) || a.model.localeCompare(b.model));
}

// The rows of one model, effort and prompt together, the group with the most reviewed pages first, then the one that read the most.
function groupSetUps(rows: SetUp[]) {
  const all = new Map<string, SetUp[]>();
  for (const s of rows) {
    const key = JSON.stringify([s.model, s.effort, s.prompt]);
    all.set(key, [...(all.get(key) ?? []), s]);
  }
  const reviewed = (group: SetUp[]) => sum(group.flatMap((s) => s.reviewed ?? [])).pages;
  const read = (group: SetUp[]) => group.reduce((pages, s) => pages + (s.read ?? 0), 0);
  return [...all.values()].sort((a, b) => (reviewed(b) - reviewed(a)) || (read(b) - read(a)));
}

// Every row of every set-up as one table; failed: the accuracy could not be loaded, so a row not reviewed is not known to be.
function SetUps({ rows, failed, label, versions, open }: { rows: SetUp[]; failed: boolean; label: (pageType: string) => string;
  versions: Versions; open: (v: Version) => void }) {
  return (
    <div className="mt-3 space-y-3">
      <Table className="table-auto" aria-label="All set-ups">
        {head(["Page type", "Model", "Prompt", "Template", "Pages read", "Reviewed", "Accuracy", "Time per page"], 4)}
        <TableBody>{rows.map((s, index) => (
          <TableRow key={index} className="align-top">
            <TableCell className="whitespace-normal">{label(s.pageType)}</TableCell>
            <TableCell className="min-w-44 whitespace-normal">
              <div className="[overflow-wrap:anywhere]">{s.model}</div>
              <div className="text-muted-foreground">{s.providers.join(", ") || "Not recorded"} · {s.effort ? `${s.effort} effort` : "Not recorded"}</div>
            </TableCell>
            <VersionCell id={s.prompt} versions={versions} open={open} />
            <VersionCell id={s.template} versions={versions} open={open} />
            <TableCell className={NUMBER}>{s.read === null ? "—" : n(s.read)}</TableCell>
            <TableCell className={NUMBER}>{s.reviewed ? n(s.reviewed.pages) : "—"}</TableCell>
            <TableCell className={NUMBER}>{s.reviewed ? percent(s.reviewed) : <span className="text-muted-foreground">{failed ? "—" : "Not reviewed"}</span>}</TableCell>
            <TableCell className={NUMBER}>{s.read === null ? "—" : s.timed ? `${(s.time / s.timed).toFixed(1)} s` : "Not recorded"}</TableCell>
          </TableRow>
        ))}</TableBody>
      </Table>
      {rows.some((s) => s.model.includes("+")) && (
        <p className="text-muted-foreground">Names joined by “+” indicate multiple models reported for a transcription, rather than one selectable model.</p>
      )}
    </div>
  );
}

// A series' Accuracy tab: how often reviewers changed what the model read of its pages, beside what the next run will read them with.
export default function AccuracyScreen() {
  const collectionId = Number(seriesParam(new URLSearchParams(location.search))) || 1;
  const [series, setSeries] = useState<SeriesSummary | null>(null);
  const [seriesFailed, setSeriesFailed] = useState(false);
  const [models, setModels] = useState<ModelData | null | undefined>(undefined); // undefined: loading; null: failed
  const [accuracy, setAccuracy] = useState<Accuracy[] | null | undefined>(undefined);
  const [versions, setVersions] = useState<Versions>(undefined);
  const [types, setTypes] = useState<PageType[] | null | undefined>(undefined);
  const [selected, setSelected] = useState<Version | null>(null); // the version whose text is shown, kept while its dialog closes
  const [shown, setShown] = useState(false);
  const open = (v: Version) => { setSelected(v); setShown(true); };
  useEffect(() => {
    backendRequest<SeriesSummary>(`/collections/${collectionId}`).then(setSeries, () => setSeriesFailed(true));
    backendRequest<ModelData>(`/transcription-models?collection=${collectionId}`).then(setModels, () => setModels(null));
    backendRequest<Accuracy[]>(`/accuracy?collection=${collectionId}`).then(setAccuracy, () => setAccuracy(null));
    backendRequest<Version[]>(`/instruction-versions?collection=${collectionId}`).then(setVersions, () => setVersions(null));
    backendRequest<PageType[]>(`/page-types?collection=${collectionId}`).then(setTypes, () => setTypes(null));
  }, [collectionId]);
  const name = series?.name ?? "";
  const label = (pageType: string) => (pageType ? types?.find((t) => t.name === pageType)?.label ?? versions?.find((v) => v.kind === pageType)?.label ?? pageType : "Not recorded");
  const version = (id: number | null) => versions?.find((v) => v.id === id);
  const prompt = versions?.find((v) => v.kind === "prompt" && v.current);
  const cfg = models?.configured;
  const templates = (types ?? []).flatMap((type) => {
    const v = version(type.templateVersion);
    return v ? [{ type, version: v }] : [];
  });
  // the newest prompt and the newest template of the page type
  const isNext = (pageType: string, promptId: number | null, template: number | null) =>
    promptId !== null && promptId === prompt?.id && template !== null && template === types?.find((t) => t.name === pageType)?.templateVersion;

  // The set-ups wait for the versions: a row's page type comes from its template's version.
  const loading = accuracy === undefined || models === undefined || versions === undefined;
  const rows = loading ? [] : setUps(models, accuracy ?? [], versions);
  const sets = groupSetUps(rows);
  const left = sets[0]; // read so far: undefined when nothing was read or reviewed
  const was = left && sum(left.flatMap((s) => s.reviewed ?? []));
  const modelChanged = !!left && !!cfg && (cfg.model !== left[0].model || cfg.effort !== left[0].effort);
  const promptChanged = !!left && !!prompt && prompt.id !== left[0].prompt;
  const templateChanged = (type: PageType) => !!left && left.some((s) => s.pageType === type.name) && !left.some((s) => s.template === type.templateVersion);
  // reviewed pages read with the next run's model, prompt and templates
  const next = rows.filter((s) => s.reviewed && cfg && s.model === cfg.model && s.effort === cfg.effort && isNext(s.pageType, s.prompt, s.template));
  const measured = sum(next.flatMap((s) => s.reviewed ?? []));
  const providers = [...new Set((left ?? []).flatMap((s) => s.providers))];
  // a row for each page type of the set-up on the left, then each other with a newest template; first: the left's newest template of it
  const total = (of: SetUp[], key: "read" | "timed" | "time") => of.reduce((all, s) => all + (s[key] ?? 0), 0);
  const tell = !!(accuracy && models && versions && types);
  const byType = loading || types === undefined ? [] : [...new Set([...(left ?? []).map((s) => s.pageType), ...templates.map(({ type }) => type.name)])].map((name) => {
    const mine = (left ?? []).filter((s) => s.pageType === name);
    const read = mine.filter((s) => s.read !== null);
    const reviewed = sum(mine.flatMap((s) => s.reviewed ?? []));
    const now = sum(next.filter((s) => s.pageType === name).flatMap((s) => s.reviewed ?? []));
    return { name, first: mine[0], type: types?.find((t) => t.name === name), reviewed, now,
      read: read.length ? total(read, "read") : null, timed: total(read, "timed"), time: total(read, "time") };
  });
  const showNext = tell && byType.some((t) => t.now.pages > 0);
  const waiting = loading || types === undefined;
  const failed = accuracy === null || models === null || versions === null || types === null;
  const leftFigure = was && accuracy?.length ? was : null;
  const nextFigure = next.length > 0 ? measured : null;
  const tooFew = [leftFigure, nextFigure].some((count) => count && count.pages < RELIABLE_PAGES);
  const templateRows = byType.filter((t) => t.name); // a page type not known by name is not a row
  const failures: [boolean, string][] = [[seriesFailed, "The series could not be loaded."], [versions === null, "The prompt and template versions could not be loaded."],
    [types === null, "The page types could not be loaded."], [accuracy === null, "Accuracy could not be loaded."], [models === null, "The models could not be loaded."]];
  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader series={{ id: collectionId, name }} />
      <main className="space-y-8 p-6">
        <SeriesHeader series={{ id: collectionId, name, ...series }} tab="accuracy" />
        {failures.map(([failed, text]) => failed && <Alert key={text} variant="destructive"><AlertDescription>{text}</AlertDescription></Alert>)}
        <section className="space-y-6">
          <h2 className="text-xl font-semibold tracking-tight">Accuracy</h2>
          <Table className="min-w-xl table-auto" aria-label="Read so far and next run">
            <TableHeader><TableRow>
              <TableHead><span className="sr-only">Setting</span></TableHead>
              <TableHead>Read so far</TableHead>
              <TableHead>Next run</TableHead>
              <TableHead><span className="sr-only">Change</span></TableHead>
            </TableRow></TableHeader>
            <TableBody>
              <Row label="Model"
                left={loading ? <Muted>Loading…</Muted> : left ? `${left[0].model} · ${providers.join(", ") || "provider not recorded"} · ${left[0].effort ? `${left[0].effort} effort` : "effort not recorded"}` : "—"}
                right={models === undefined ? <span role="status" className="text-muted-foreground">Loading models…</span>
                  : models === null ? <Muted>Not loaded</Muted>
                  : cfg ? <Next changed={modelChanged}>{`${cfg.model} · ${cfg.provider} · ${cfg.effort} effort`}</Next> : "No model chosen"}
                action={<Button asChild variant="outline" size="sm"><a href="/?view=settings&tab=transcription">Change model</a></Button>} />
              <Row label="Prompt"
                left={loading ? <Muted>Loading…</Muted> : versions === null ? <Muted>Not loaded</Muted> : left ? (version(left[0].prompt) ? <VersionButton version={version(left[0].prompt)!} open={open} /> : "Not recorded") : "—"}
                right={versions === undefined ? <Muted>Loading…</Muted> : versions === null ? <Muted>Not loaded</Muted>
                  : prompt ? <Next changed={promptChanged}><VersionButton version={prompt} open={open} /></Next> : "From the files"}
                action={prompt && <Button variant="outline" size="sm" onClick={() => open(prompt)}>View</Button>} />
              {templateRows.length ? templateRows.map((t) => {
                const newest = version(t.type?.templateVersion ?? null);
                const mine = t.first && version(t.first.template);
                return (
                  <Row key={t.name} label={`${label(t.name)} template`}
                    left={!t.first ? "—" : versions === null ? <Muted>Not loaded</Muted> : mine ? <VersionButton version={mine} open={open} /> : "Not recorded"}
                    right={types === null || versions === null ? <Muted>Not loaded</Muted>
                      : newest ? <Next changed={!!t.type && templateChanged(t.type)}><VersionButton version={newest} open={open} /></Next> : <Muted>None yet</Muted>}
                    action={<Button asChild variant="outline" size="sm"><a href={`/?series=${collectionId}&view=setup`}>Edit templates</a></Button>} />
                );
              }) : (
                <Row label="Templates" left={loading ? <Muted>Loading…</Muted> : "—"}
                  right={waiting ? <Muted>Loading…</Muted> : types === null || versions === null ? <Muted>Not loaded</Muted> : <Muted>None yet</Muted>}
                  action={<Button asChild variant="outline" size="sm"><a href={`/?series=${collectionId}&view=setup`}>Edit templates</a></Button>} />
              )}
              <Row label="Accuracy"
                left={loading ? <span role="status" className="text-muted-foreground">Loading accuracy…</span>
                  : leftFigure ? <Figure count={leftFigure} testId="accuracy-percent" /> : accuracy ? <Muted>No reviewed pages yet</Muted> : "—"}
                right={waiting ? <Muted>Loading…</Muted> : failed ? "—" : nextFigure ? <Figure count={nextFigure} testId="next-accuracy-percent" /> : <Muted>Not measured yet</Muted>}
                action={<Button asChild size="sm"><a href={`/?series=${collectionId}`}>Review more pages</a></Button>} />
            </TableBody>
          </Table>
          {(leftFigure || nextFigure) && (
            <div className="space-y-1">
              {tooFew && <p role="status" className="text-muted-foreground">Too few pages to rely on yet: review about {RELIABLE_PAGES}.</p>}
              <p className="text-muted-foreground">Blank fields count too, so pages with many blanks score higher.</p>
            </div>
          )}
          {byType.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-base font-medium">By page type</h3>
              <Table className="table-auto" aria-label="By page type">
                {head(["Page type", "Pages read", "Time a page", "Reviewed", "Accuracy", ...(showNext ? ["Next run accuracy"] : [])], showNext ? 5 : 4)}
                <TableBody>{byType.map((t) => (
                  <TableRow key={t.name}>
                    <TableCell>{label(t.name)}</TableCell>
                    <TableCell className={NUMBER}>{t.read === null ? "—" : n(t.read)}</TableCell>
                    <TableCell className={NUMBER}>{t.read === null ? "—" : t.timed ? `${(t.time / t.timed).toFixed(1)} s` : "Not recorded"}</TableCell>
                    <TableCell className={NUMBER}>{t.reviewed.pages ? n(t.reviewed.pages) : "—"}</TableCell>
                    <TableCell className={NUMBER}>{t.reviewed.pages ? percent(t.reviewed) : <span className="text-muted-foreground">{accuracy ? "not reviewed" : "—"}</span>}</TableCell>
                    {showNext && <TableCell className={NUMBER}>{t.now.pages ? percent(t.now) : <span className="text-muted-foreground">not measured yet</span>}</TableCell>}
                  </TableRow>
                ))}</TableBody>
              </Table>
            </div>
          )}
          {sets.length > 1 && (
            <Collapsible className="text-sm">
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm" className="text-muted-foreground">
                  <ChevronRight aria-hidden className="transition-transform group-data-[state=open]/button:rotate-90" />All set-ups ({sets.length})
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent><SetUps rows={rows} failed={accuracy === null} label={label} versions={versions} open={open} /></CollapsibleContent>
            </Collapsible>
          )}
        </section>
      </main>
      <VersionDialog versions={versions ?? []} selected={selected} onSelect={setSelected} open={shown} onOpenChange={setShown} />
    </div>
  );
}
