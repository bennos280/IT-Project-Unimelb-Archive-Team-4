import { useId } from "react";
import { providerNames } from "./backend";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
export type ModelChoice = { model: string; provider: string; effort: string };

export type ModelData = {
  configured: ModelChoice | null; // the choice saved on the Settings page; null until one is saved
  models: { provider: string | null; model: string; effort: string | null;
    promptVersion: number | null; templateVersion: number | null;
    pages: number; averageSeconds: number | null }[];
};

export function ModelFields({data,choice,setChoice,busy}:{data:ModelData;choice:ModelChoice;setChoice:(choice:ModelChoice)=>void;busy:boolean}) {
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
      <a className="self-start text-sm underline underline-offset-4" href="/?view=settings&tab=performance" target="_blank" rel="noreferrer">See how models have performed</a>
  </FieldGroup>;
}
