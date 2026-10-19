import { useId } from "react";
import { providerNames } from "./backend";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
export type ModelChoice = { model: string; provider: string; effort: string };

export type ModelData = {
  configured: ModelChoice | null; // the choice saved on the Settings page; null until one is saved
  models: { provider: string | null; model: string; effort: string | null;
    promptVersion: number | null; templateVersion: number | null;
    pages: number; averageSeconds: number | null }[];
};

export function ModelFields({data,choice,setChoice,busy,onViewTable}:{data:ModelData;choice:ModelChoice;setChoice:(choice:ModelChoice)=>void;busy:boolean;onViewTable:()=>void}) {
  const id = useId();
  const listId = `${id}-models`;
  return <FieldGroup className="gap-4">
      {!data.configured && <Alert role="status"><AlertDescription>No transcription model is set. <a className="underline" href="/?view=settings">Choose one on the Settings page</a>, or pick one here for this run.</AlertDescription></Alert>}
      <Field>
        <FieldLabel htmlFor={`${id}-provider`}>Provider</FieldLabel>
        <NativeSelect id={`${id}-provider`} className="w-full" value={choice.provider} disabled={busy} onChange={(e) => setChoice({ ...choice, provider: e.target.value, model: "" })}>
          {!choice.provider && <option value="" disabled>Choose…</option>}{Object.entries(providerNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </NativeSelect>
      </Field>
      <Field>
        <FieldLabel htmlFor={`${id}-model`}>Model</FieldLabel>
        <Input id={`${id}-model`} list={listId} value={choice.model} disabled={busy} onChange={(e) => setChoice({ ...choice, model: e.target.value })} placeholder="Choose or enter a model name" />
        <datalist id={listId}>{[...new Set([...(data.configured?.provider === choice.provider ? [data.configured.model] : []), ...(choice.provider === "claude" ? ["sonnet", "opus", "haiku"] : []), ...data.models.filter((m) => m.provider === choice.provider && !m.model.includes("+")).map((m) => m.model)])].map((model) => <option key={model} value={model} />)}</datalist>
      </Field>
      <Field>
        <FieldLabel htmlFor={`${id}-effort`}>Effort</FieldLabel>
        <Input id={`${id}-effort`} value={choice.effort} disabled={busy} onChange={(e) => setChoice({ ...choice, effort: e.target.value })} />
      </Field>
      <Button type="button" variant="outline" className="self-start" onClick={() => onViewTable()}>View model table</Button>
  </FieldGroup>;
}
export function ModelTable({data}:{data:ModelData}) { return <div className="space-y-3 text-sm">
      {data.configured
        ? <p><strong>Current default:</strong> {data.configured.model} · {data.configured.provider} · {data.configured.effort} effort</p>
        : <p><strong>Current default:</strong> No transcription model is set. <a className="underline" href="/?view=settings">Choose one on the Settings page</a>.</p>}
      <p className="text-muted-foreground">Recorded transcription configurations for pages currently in the database. Historical model names do not guarantee current availability.</p>
      <Table className="min-w-[800px] table-auto">
        <TableHeader><TableRow>{["Model", "Provider", "Effort", "Prompt version", "Template version", "Pages processed", "Average processing time / page"].map((label) => <TableHead key={label} className="whitespace-normal">{label}</TableHead>)}</TableRow></TableHeader>
        <TableBody>{data.models.map((model, index) => <TableRow key={index} className="align-top">
          <TableCell className="min-w-44 whitespace-normal [overflow-wrap:anywhere]">{model.model}</TableCell><TableCell>{model.provider ?? "Not recorded"}</TableCell><TableCell>{model.effort ?? "Not recorded"}</TableCell>
          <TableCell>{model.promptVersion ?? "Not recorded"}</TableCell><TableCell>{model.templateVersion ?? "Not recorded"}</TableCell>
          <TableCell>{model.pages}</TableCell><TableCell>{model.averageSeconds === null ? "Not recorded" : `${model.averageSeconds.toFixed(1)} s`}</TableCell>
        </TableRow>)}</TableBody>
      </Table>
      {!data.models.length && <p className="text-muted-foreground">No model history recorded yet.</p>}
      <p className="text-muted-foreground">Cost and accuracy are not recorded in this data. Names joined by “+” indicate multiple models reported for a transcription, rather than one selectable model.</p>
</div>; }
