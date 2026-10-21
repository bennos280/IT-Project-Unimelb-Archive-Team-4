import { useEffect, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backendRequest } from "../progress/backend";
import type { ModelData } from "../progress/ModelControls";

// GET /accuracy: one row per model, effort, page type and prompt and template version, from the pages reviewers saved since they were read
type Accuracy = { model: string; effort: string | null; pageType: string; promptVersion: number | null;
  templateVersion: number | null; pages: number; fields: number; changed: number };
type Total = { model: string; effort: string | null; pages: number; fields: number; changed: number };
// GET /instruction-versions: every prompt and template version, oldest first; number counts the versions of one kind from 1
type Version = { id: number; kind: string; label: string; number: number; current: boolean; body: string;
  reviewer: string | null; note: string | null; createdAt: string };
type Versions = Version[] | null | undefined; // undefined: loading; null: failed

const share = (row: Total) => (row.fields ? (row.fields - row.changed) / row.fields : -1);
const percent = (row: Total) => (row.fields ? `${(100 * share(row)).toFixed(1)}%` : "No fields");
const head = (labels: string[]) => (
  <TableHeader><TableRow>{labels.map((label) => <TableHead key={label} className="whitespace-normal">{label}</TableHead>)}</TableRow></TableHeader>
);
const title = (v: Version) => (v.kind === "prompt" ? `Prompt v${v.number}` : `${v.label} template v${v.number}`);

// Who saved a version and when, and which version pages are read with from now on.
function describe(v: Version, versions: Version[]) {
  const origin = v.reviewer ? `by ${v.reviewer}` : "from the files";
  const saved = v.createdAt ? `Saved ${new Date(v.createdAt).toLocaleString()} ${origin}.` : `${origin[0].toUpperCase()}${origin.slice(1)}.`;
  const newest = Math.max(...versions.filter((other) => other.kind === v.kind).map((other) => other.number));
  return `${saved} Pages read from now on use ${v.current ? "this version" : `v${newest}`}.`;
}

// A version's number as a button that opens its text; the id itself while the versions are not loaded.
function VersionCell({ id, versions, open }: { id: number | null; versions: Versions; open: (v: Version) => void }) {
  const version = versions?.find((v) => v.id === id);
  return (
    <TableCell>
      {id === null ? "Not recorded" : !version ? id
        : <Button variant="link" className="h-auto p-0" aria-label={title(version)} onClick={() => open(version)}>{`v${version.number}`}</Button>}
    </TableCell>
  );
}

function ModelTable({ data, versions, open }: { data: ModelData; versions: Versions; open: (v: Version) => void }) {
  return (
    <div className="space-y-3 text-sm">
      {data.configured
        ? <p><strong>Current default:</strong> {data.configured.model} · {data.configured.provider} · {data.configured.effort} effort</p>
        : <p><strong>Current default:</strong> No transcription model is set. <a className="underline" href="/?view=settings">Choose one on the Settings page</a>.</p>}
      <p className="text-muted-foreground">Recorded transcription configurations for pages currently in the database. Historical model names do not guarantee current availability.</p>
      <Table className="min-w-[800px] table-auto">
        {head(["Model", "Provider", "Effort", "Page type", "Prompt", "Template", "Pages processed", "Average processing time / page"])}
        <TableBody>{data.models.map((model, index) => (
          <TableRow key={index} className="align-top">
            <TableCell className="min-w-44 whitespace-normal [overflow-wrap:anywhere]">{model.model}</TableCell>
            <TableCell>{model.provider ?? "Not recorded"}</TableCell><TableCell>{model.effort ?? "Not recorded"}</TableCell>
            <TableCell>{versions?.find((v) => v.id === model.templateVersion)?.label ?? "Not recorded"}</TableCell>
            <VersionCell id={model.promptVersion} versions={versions} open={open} /><VersionCell id={model.templateVersion} versions={versions} open={open} />
            <TableCell>{model.pages}</TableCell><TableCell>{model.averageSeconds === null ? "Not recorded" : `${model.averageSeconds.toFixed(1)} s`}</TableCell>
          </TableRow>
        ))}</TableBody>
      </Table>
      {!data.models.length && <p className="text-muted-foreground">No model history recorded yet.</p>}
      <p className="text-muted-foreground">Cost is not recorded in this data. Names joined by “+” indicate multiple models reported for a transcription, rather than one selectable model.</p>
    </div>
  );
}

// The Performance tab: the models that have read pages here, and how often reviewers changed what each read.
export default function Performance() {
  const [models, setModels] = useState<ModelData | null | undefined>(undefined); // undefined: loading; null: failed
  const [accuracy, setAccuracy] = useState<Accuracy[] | null | undefined>(undefined);
  const [versions, setVersions] = useState<Versions>(undefined);
  const [selected, setSelected] = useState<Version | null>(null); // the version whose text is shown, kept while its dialog closes
  const [shown, setShown] = useState(false);
  const open = (v: Version) => { setSelected(v); setShown(true); };
  useEffect(() => {
    backendRequest<ModelData>("/transcription-models").then(setModels, () => setModels(null));
    backendRequest<Accuracy[]>("/accuracy").then(setAccuracy, () => setAccuracy(null));
    backendRequest<Version[]>("/instruction-versions").then(setVersions, () => setVersions(null));
  }, []);
  // each model and effort across its page types and versions, the most accurate first
  const byModel = Object.values((accuracy ?? []).reduce<Record<string, Total>>((all, row) => {
    const total = (all[`${row.model}|${row.effort}`] ??= { model: row.model, effort: row.effort, pages: 0, fields: 0, changed: 0 });
    total.pages += row.pages;
    total.fields += row.fields;
    total.changed += row.changed;
    return all;
  }, {})).sort((a, b) => share(b) - share(a));
  return (
    <>
      <section id="models" className="space-y-3">
        <h2 className="text-xl font-semibold tracking-tight">Models used</h2>
        <p className="text-sm text-muted-foreground">
          Each model that has read pages here, with the prompt and template versions it read them with. Select a version to read it.
        </p>
        {versions === null && <Alert variant="destructive"><AlertDescription>The prompt and template versions could not be loaded.</AlertDescription></Alert>}
        {models === undefined ? <p role="status" className="text-sm text-muted-foreground">Loading models…</p>
          : models === null ? <Alert variant="destructive"><AlertDescription>The models could not be loaded.</AlertDescription></Alert>
          : <ModelTable data={models} versions={versions} open={open} />}
      </section>
      <section id="accuracy" className="space-y-3">
        <h2 className="text-xl font-semibold tracking-tight">Accuracy</h2>
        <p className="text-sm text-muted-foreground">
          How often reviewers changed what each model read, on the pages they have saved since. A field counts as wrong when the
          value a reviewer saved differs from what the model read.
        </p>
        {accuracy === undefined ? <p role="status" className="text-sm text-muted-foreground">Loading accuracy…</p>
          : accuracy === null ? <Alert variant="destructive"><AlertDescription>Accuracy could not be loaded.</AlertDescription></Alert>
          : !accuracy.length ? <p className="text-sm text-muted-foreground">No reviewed pages yet: accuracy appears here once reviewers save pages a model has read.</p>
          : <>
            <h3 className="font-semibold">By model</h3>
            <Table className="table-auto" aria-label="Accuracy by model">
              {head(["Model", "Effort", "Pages reviewed", "Fields changed", "Accuracy"])}
              <TableBody>{byModel.map((row) => (
                <TableRow key={`${row.model}|${row.effort}`}>
                  <TableCell className="whitespace-normal [overflow-wrap:anywhere]">{row.model}</TableCell><TableCell>{row.effort ?? "Not recorded"}</TableCell>
                  <TableCell>{row.pages}</TableCell><TableCell>{row.changed} of {row.fields}</TableCell><TableCell>{percent(row)}</TableCell>
                </TableRow>
              ))}</TableBody>
            </Table>
            <h3 className="font-semibold">By page type and version</h3>
            <Table className="min-w-[800px] table-auto" aria-label="Accuracy by page type and version">
              {head(["Model", "Effort", "Page type", "Prompt", "Template", "Pages reviewed", "Fields changed", "Accuracy"])}
              <TableBody>{accuracy.map((row, index) => (
                <TableRow key={index} className="align-top">
                  <TableCell className="min-w-44 whitespace-normal [overflow-wrap:anywhere]">{row.model}</TableCell><TableCell>{row.effort ?? "Not recorded"}</TableCell>
                  <TableCell>{versions?.find((v) => v.kind === row.pageType)?.label ?? row.pageType}</TableCell>
                  <VersionCell id={row.promptVersion} versions={versions} open={open} /><VersionCell id={row.templateVersion} versions={versions} open={open} />
                  <TableCell>{row.pages}</TableCell><TableCell>{row.changed} of {row.fields}</TableCell><TableCell>{percent(row)}</TableCell>
                </TableRow>
              ))}</TableBody>
            </Table>
          </>}
      </section>
      <Dialog open={shown} onOpenChange={setShown}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{selected && title(selected)}</DialogTitle>
            <DialogDescription>{selected && describe(selected, versions ?? [])}</DialogDescription>
            {selected?.note && <p className="text-sm">Note: {selected.note}</p>}
          </DialogHeader>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 font-mono text-xs">{selected?.body}</pre>
        </DialogContent>
      </Dialog>
    </>
  );
}
