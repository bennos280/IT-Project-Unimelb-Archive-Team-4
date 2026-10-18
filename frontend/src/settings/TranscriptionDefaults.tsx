import { useEffect, useId, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { backendRequest, providerNames } from "../progress/backend";
import type { ModelChoice, ModelData } from "../progress/ModelControls";

type ModelOption = { value: string; label: string; group: "used" | "latest" | "listed"; efforts: string[] | null; defaultEffort: string | null };
type ProviderOptions = { available: boolean; models: ModelOption[]; efforts: string[]; error: string | null };
const groupLabels = { used: "Used in this project", latest: "Latest", listed: "From Codex" } as const;
const EMPTY: ModelChoice = { provider: "", model: "", effort: "" };
const OTHER = "\u0000other"; // not a possible model name
const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// The provider, model and effort used when a transcription is started without choosing them: chosen here (there is no default) and saved in the database.
// notReady: provider id -> what its connection card says, for the providers that can't transcribe yet.
// onSaved: told the saved choice (null: none yet), on load and after every save.
export default function TranscriptionDefaults({ notReady, onSaved }: { notReady: Record<string, string>; onSaved: (saved: ModelChoice | null) => void }) {
  const id = useId();
  const [data, setData] = useState<ModelData | null>(null);
  const [saved, setSaved] = useState<ModelChoice | null>(null);
  const [choice, setChoice] = useState<ModelChoice>(EMPTY);
  const [options, setOptions] = useState<Record<string, ProviderOptions> | null>(null);
  const [other, setOther] = useState(false); // "Other…" picked, whatever the typed name is
  const [loadError, setLoadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(""); // "Saved ✓" until the next edit

  useEffect(() => {
    backendRequest<ModelData>("/transcription-models").then((result) => {
      setData(result);
      setSaved(result.configured);
      onSaved(result.configured);
      if (result.configured) setChoice(result.configured);
    }).catch((e) => setLoadError(e instanceof Error ? e.message : "Could not load the defaults."));
    backendRequest<Record<string, ProviderOptions>>("/transcription-options").then(setOptions).catch(() => setOptions(null));
  }, [onSaved]);

  // Every edit goes through here so the notice goes away with it.
  function edit(next: ModelChoice) {
    setNotice("");
    setChoice(next);
  }

  async function save() {
    setBusy(true);
    setSaveError("");
    setNotice("");
    try {
      const result = await backendRequest<ModelChoice>("/transcription-defaults",
        json("PUT", { provider: choice.provider, model: choice.model.trim(), effort: choice.effort.trim() }));
      setSaved(result);
      onSaved(result);
      setNotice("Saved ✓");
      setOther(false);
      setChoice({ provider: result.provider, model: result.model, effort: result.effort });
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Could not save the defaults.");
    }
    setBusy(false);
  }

  const suggestions = data ? [...new Set([
    ...(saved?.provider === choice.provider ? [saved.model] : []),
    ...(choice.provider === "claude" ? ["sonnet", "opus", "haiku"] : []),
    ...data.models.filter((m) => m.provider === choice.provider && !m.model.includes("+")).map((m) => m.model),
  ])] : [];
  const warning = notReady[choice.provider];
  const complete = Boolean(choice.provider && choice.model.trim() && choice.effort.trim());
  const dirty = !saved || choice.provider !== saved.provider || choice.model.trim() !== saved.model || choice.effort.trim() !== saved.effort;

  // The dropdowns need the provider's list; without it (or with an error from the program) the text boxes stay.
  const providerOptions = options?.[choice.provider];
  const lists = providerOptions && !providerOptions.error && providerOptions.models.length > 0 ? providerOptions : null;
  const optionsNote = options === null ? "The model lists couldn't be loaded." : providerOptions?.error;
  const current = lists?.models.find((m) => m.value === choice.model);
  const modelValue = lists && (other || (choice.model !== "" && !current)) ? OTHER : choice.model;
  const effortList = lists && [...new Set([...supportedEfforts(current, lists), ...(choice.effort ? [choice.effort] : [])])];

  // The efforts a model lists, or its provider's when it lists none.
  function supportedEfforts(model: ModelOption | undefined, provider: ProviderOptions) {
    return model?.efforts?.length ? model.efforts : provider.efforts;
  }

  // The effort kept if the model supports it, else none: the effort is always chosen.
  function effortFor(model: ModelOption, provider: ProviderOptions, effort: string) {
    return supportedEfforts(model, provider).includes(effort) ? effort : "";
  }

  function pickProvider(provider: string) {
    setOther(false);
    edit({ provider, model: "", effort: "" });
  }

  function pickModel(value: string) {
    const model = lists?.models.find((m) => m.value === value);
    setOther(!model);
    edit({ ...choice, model: model ? model.value : "", effort: model && lists ? effortFor(model, lists, choice.effort) : choice.effort });
  }

  return (
    <section id="transcription-defaults" className="space-y-3">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Transcription model</h2>
        <p className="text-sm text-muted-foreground">Used for new transcriptions. Shared with the team.</p>
      </div>
      {loadError && <Alert variant="destructive"><AlertDescription>{loadError}</AlertDescription></Alert>}
      {data && (
        <Card>
          <CardContent className="flex flex-col gap-4">
            <div className="grid items-start gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_minmax(0,1fr)_auto]">
              <Field>
                <FieldLabel htmlFor={`${id}-provider`}>Provider</FieldLabel>
                <NativeSelect id={`${id}-provider`} className="w-full" value={choice.provider} disabled={busy}
                  onChange={(e) => pickProvider(e.target.value)}>
                  {!choice.provider && <option value="" disabled>Choose…</option>}
                  <option value="claude">Claude</option><option value="codex">Codex</option>
                </NativeSelect>
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-model`}>Model</FieldLabel>
                {lists ? (
                  <>
                    <NativeSelect id={`${id}-model`} className="w-full" value={modelValue} disabled={busy} onChange={(e) => pickModel(e.target.value)}>
                      {modelValue === "" && <option value="" disabled>Choose…</option>}
                      {(["used", "latest", "listed"] as const).map((group) => {
                        const items = lists.models.filter((m) => m.group === group);
                        return items.length > 0 && (
                          <optgroup key={group} label={groupLabels[group]}>
                            {items.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                          </optgroup>
                        );
                      })}
                      <option value={OTHER}>Other…</option>
                    </NativeSelect>
                    {modelValue === OTHER && (
                      <Input aria-label="Custom model name" value={choice.model} disabled={busy} placeholder="Enter a model name"
                        onChange={(e) => edit({ ...choice, model: e.target.value })} />
                    )}
                  </>
                ) : (
                  <>
                    <Input id={`${id}-model`} list={`${id}-models`} value={choice.model} disabled={busy}
                      placeholder="Choose or enter a model name" onChange={(e) => edit({ ...choice, model: e.target.value })} />
                    <datalist id={`${id}-models`}>{suggestions.map((m) => <option key={m} value={m} />)}</datalist>
                  </>
                )}
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-effort`}>Effort</FieldLabel>
                {effortList ? (
                  <NativeSelect id={`${id}-effort`} className="w-full" value={choice.effort} disabled={busy}
                    onChange={(e) => edit({ ...choice, effort: e.target.value })}>
                    {!choice.effort && <option value="" disabled>Choose…</option>}
                    {effortList.map((effort) => <option key={effort} value={effort}>{effort}</option>)}
                  </NativeSelect>
                ) : (
                  <Input id={`${id}-effort`} value={choice.effort} disabled={busy} onChange={(e) => edit({ ...choice, effort: e.target.value })} />
                )}
              </Field>
              <Field>
                <FieldLabel aria-hidden="true" className="invisible max-md:hidden">&nbsp;</FieldLabel>
                <Button disabled={busy || !dirty || !complete} onClick={save}>Save defaults</Button>
              </Field>
            </div>
            {!lists && optionsNote && <p className="text-sm text-muted-foreground">{optionsNote}</p>}
            {warning && (
              <Alert><AlertDescription>
                {providerNames[choice.provider] ?? choice.provider} isn't ready ({warning.toLowerCase()}), so transcription with these defaults won't work until it is.
              </AlertDescription></Alert>
            )}
            {saveError && <Alert variant="destructive"><AlertDescription>{saveError}</AlertDescription></Alert>}
            <p role="status" className={notice ? "text-sm text-green-700 dark:text-green-400" : "sr-only"}>{notice}</p>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
