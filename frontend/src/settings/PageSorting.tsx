import { useCallback, useEffect, useId, useState, type ReactNode } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect, NativeSelectOptGroup, NativeSelectOption } from "@/components/ui/native-select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { me } from "../person";
import { backendRequest, providerNames } from "../progress/backend";

type Sorter = { provider: string; model: string; effort: string };
type Sorting = {
  method: "local" | "model"; unsure: "review" | "model"; sorter: Sorter | null; localAvailable: boolean;
  checked: { ok: boolean; seconds: number } | null;
};
type Check = { ok: boolean; seconds?: number; detail?: string };
type ModelOption = { value: string; label: string; efforts: string[] | null; defaultEffort: string | null };
type ProviderOptions = { available: boolean; models: ModelOption[]; efforts: string[]; error: string | null };
type SortingModel = { id: number; passed: boolean; active: boolean; createdAt: string; pages: number };
type Install = { installable: boolean; running: boolean; ok: boolean | null; detail: string | null; seconds: number | null };

const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
const NO_INSTALL: Install = { installable: false, running: false, ok: null, detail: "Could not check whether PyTorch can be installed.", seconds: null };
const SAME = ""; // the "Model that sorts" choice for the transcription model
const keyOf = (provider: string, model: string) => `${provider}\u0000${model}`;

// How a read sorts pages into its series' page types: by the reading model (asked what each page is; the default, as it works
// for any series on any computer), or by the page sorting model on this computer (PyTorch), checked as soon as it's the
// choice (PyTorch is installed from here when it isn't). Each card holds its own settings; every change is saved at once.
export default function PageSorting() {
  const id = useId();
  const [sorting, setSorting] = useState<Sorting | null>(null);
  const [error, setError] = useState("");
  const [check, setCheck] = useState<Check | "checking" | null>(null);
  const [options, setOptions] = useState<Record<string, ProviderOptions>>({});
  const [trained, setTrained] = useState<SortingModel[]>([]);
  const [retrain, setRetrain] = useState("");
  const [install, setInstall] = useState<Install | null>(null);

  const checkHere = useCallback(async () => {
    setCheck("checking");
    try {
      setCheck(await backendRequest<Check>("/page-sorting/check", { method: "POST" }));
    } catch (e) {
      setCheck({ ok: false, detail: message(e, "Could not check it.") });
    }
  }, []);

  useEffect(() => {
    backendRequest<Sorting>("/page-sorting").then((s) => {
      setSorting(s);
      // whether it can be installed, or (when it's the choice) whether it runs; a check that passed is remembered by the API
      if (s.checked) setCheck(s.checked);
      else if (s.localAvailable && s.method === "local") checkHere();
      if (!s.localAvailable) backendRequest<Install>("/page-sorting/install").then(setInstall).catch(() => setInstall(NO_INSTALL));
    }).catch((e) => setError(message(e, "Could not load it.")));
    backendRequest<Record<string, ProviderOptions>>("/transcription-options").then(setOptions).catch(() => setOptions({}));
    backendRequest<SortingModel[]>("/sorting-models").then(setTrained).catch(() => setTrained([]));
  }, [checkHere]);

  const installing = install?.running;
  useEffect(() => {
    if (!installing) return;
    const timer = setInterval(async () => {
      const now = await backendRequest<Install>("/page-sorting/install").catch(() => null);
      if (!now) return;
      setInstall(now);
      if (now.running || !now.ok) return;
      try {
        setSorting(await backendRequest<Sorting>("/page-sorting"));
        checkHere();
      } catch (e) {
        setError(message(e, "Could not load it."));
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [installing, checkHere]);

  async function startInstall() {
    setError("");
    try {
      setInstall(await backendRequest<Install>("/page-sorting/install", { method: "POST" }));
    } catch (e) {
      setInstall((i) => ({ ...(i ?? NO_INSTALL), installable: true, running: false, ok: false, detail: message(e, "Could not start the install.") }));
    }
  }

  async function save(change: Partial<Sorting> | { sameAsTranscription: true }) {
    const before = sorting;
    setError("");
    setSorting((s) => s && { ...s, ...("sameAsTranscription" in change ? { sorter: null } : change) }); // shown at once; put back if not saved
    try {
      setSorting(await backendRequest<Sorting>("/page-sorting", json("PUT", change)));
    } catch (e) {
      setSorting(before);
      setError(message(e, "Could not save it."));
    }
  }

  function choose(method: string) {
    save({ method: method as Sorting["method"] });
    if (method === "local" && check === null) checkHere();
  }

  function chooseSorter(value: string) {
    if (value === SAME) return save({ sameAsTranscription: true });
    const [provider, model] = value.split("\u0000");
    const option = options[provider]?.models.find((m) => m.value === model);
    const efforts = option?.efforts?.length ? option.efforts : options[provider]?.efforts ?? [];
    // sorting is an easy question: the lowest effort offered, or the API's default
    const effort = efforts.includes("low") ? "low" : option?.defaultEffort ?? efforts[0] ?? "default";
    save({ sorter: { provider, model, effort } });
  }

  async function chooseTrained(value: string) {
    const modelId = value ? Number(value) : null;
    setError("");
    try {
      await backendRequest("/sorting-models/active", json("PUT", { modelId, reviewerId: me().id }));
      setTrained((all) => all.map((m) => ({ ...m, active: m.id === modelId })));
    } catch (e) {
      setError(message(e, "Could not save it."));
    }
  }

  async function startRetrain() {
    setError("");
    setRetrain("");
    try {
      await backendRequest("/sorting-models", json("POST", { reviewerId: me().id }));
      setRetrain("Waiting for the worker; a retrained version that passes its check is used from then on.");
    } catch (e) {
      setError(message(e, "Could not start retraining."));
    }
  }

  const failed = check && check !== "checking" && !check.ok ? check : null;
  const here = sorting?.localAvailable;
  const installFailed = install?.ok === false && !install.running;
  const installable = !!install?.installable && !install.running;
  const notice = !sorting ? ""
    : here ? (check === "checking" ? "Loading the page sorting model (slower the first time)…"
      : check?.ok ? `Checked: a test page sorted in ${check.seconds} s.` : check?.detail ?? "")
    : !install ? ""
    : install.running ? "Installing PyTorch, which can take a few minutes…"
    : installFailed ? install.detail ?? "The install didn't finish."
    : installable ? "Downloads PyTorch, about 2 GB. Pages are sorted by the reading model meanwhile." : install.detail ?? "";
  const bad = here ? !!failed : installFailed || (!!install && !install.installable);
  const providers = Object.entries(options).filter(([, o]) => o.available && !o.error && o.models.length);
  const sorter = sorting?.sorter;
  const listed = sorter && options[sorter.provider]?.models.some((m) => m.value === sorter.model);
  const passed = trained.filter((m) => m.passed);

  return (
    <section id="page-sorting" aria-labelledby={`${id}-title`} className="space-y-3">
      <div>
        <h2 id={`${id}-title`} className="text-xl font-semibold tracking-tight">Page sorting</h2>
        <p className="text-sm text-muted-foreground">How each page is sorted into its series' page types before it's read.</p>
      </div>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      {sorting && (
        <RadioGroup aria-labelledby={`${id}-title`} value={sorting.method} onValueChange={choose} className="gap-3">
          <Choice id={id} value="model" chosen={sorting.method} title="By the reading model"
            facts="Works for any series, on any computer. One more request to your provider for each page.">
            {(sorting.method === "model" || sorting.unsure === "model") && (
              <Setting label="Model that sorts" hint="A cheaper model is usually enough to tell page types apart.">
                <NativeSelect value={sorter ? keyOf(sorter.provider, sorter.model) : SAME} onChange={(e) => chooseSorter(e.target.value)}>
                  <NativeSelectOption value={SAME}>Same as the transcription model</NativeSelectOption>
                  {sorter && !listed && (
                    <NativeSelectOption value={keyOf(sorter.provider, sorter.model)}>
                      {sorter.model} ({providerNames[sorter.provider] ?? sorter.provider})
                    </NativeSelectOption>
                  )}
                  {providers.map(([provider, o]) => (
                    <NativeSelectOptGroup key={provider} label={providerNames[provider] ?? provider}>
                      {o.models.map((m) => <NativeSelectOption key={m.value} value={keyOf(provider, m.value)}>{m.label}</NativeSelectOption>)}
                    </NativeSelectOptGroup>
                  ))}
                </NativeSelect>
              </Setting>
            )}
          </Choice>
          <Choice id={id} value="local" chosen={sorting.method} title="On this computer" disabled={!sorting.localAvailable}
            facts="Free and quick, with no requests. Knows only the page types it was trained on (the Wilfred Prest Survey's)."
            status={!here ? (!install ? null : install.running ? <Badge variant="secondary">Installing…</Badge>
                : install.installable ? <Badge variant="secondary">Not installed</Badge> : <Badge variant="destructive">Can't run here</Badge>)
              : check === "checking" ? <Badge variant="secondary">Checking…</Badge>
              : check?.ok ? <Badge variant="outline">Ready</Badge>
              : failed ? <Badge variant="destructive">Not working</Badge> : null}>
            <p role="status" className={!notice ? "sr-only" : bad ? "text-sm text-destructive" : "text-sm text-muted-foreground"}>{notice}</p>
            {installable && (
              <div>
                <Button type="button" variant="outline" size="sm" onClick={startInstall}>{installFailed ? "Try again" : "Install PyTorch"}</Button>
              </div>
            )}
            {failed && here && (
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" onClick={checkHere}>Try again</Button>
                {sorting.method === "local" && (
                  <Button type="button" variant="outline" size="sm" onClick={() => choose("model")}>Use the reading model instead</Button>
                )}
              </div>
            )}
            {sorting.method === "local" && (
              <>
                <Setting label="When it isn't sure" hint="A page it can't place, or one of a type it doesn't know.">
                  <NativeSelect value={sorting.unsure} onChange={(e) => save({ unsure: e.target.value as Sorting["unsure"] })}>
                    <NativeSelectOption value="review">Leave it for a reviewer</NativeSelectOption>
                    <NativeSelectOption value="model">Ask the reading model</NativeSelectOption>
                  </NativeSelect>
                </Setting>
                <Setting label="Trained version" hint="Retrained versions learn from the pages reviewers sorted.">
                  <NativeSelect value={String(passed.find((m) => m.active)?.id ?? "")} onChange={(e) => chooseTrained(e.target.value)}>
                    <NativeSelectOption value="">The one PrestCribe came with</NativeSelectOption>
                    {passed.map((m) => (
                      <NativeSelectOption key={m.id} value={String(m.id)}>
                        Retrained {new Date(m.createdAt).toLocaleDateString()} ({m.pages} pages)
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Setting>
                <div className="flex flex-wrap items-center gap-3">
                  <Button type="button" variant="outline" size="sm" onClick={startRetrain}>Retrain on reviewed pages</Button>
                  <span role="status" className={retrain ? "text-sm text-muted-foreground" : "sr-only"}>{retrain}</span>
                </div>
              </>
            )}
          </Choice>
        </RadioGroup>
      )}
    </section>
  );
}

// One way of sorting, as a card chosen by its radio; its settings show inside it.
function Choice({ id, value, chosen, title, facts, status, disabled, children }: {
  id: string; value: string; chosen: string; title: string; facts: string; status?: ReactNode; disabled?: boolean; children?: ReactNode;
}) {
  return (
    <div className={`space-y-3 rounded-xl border p-4 ${chosen === value ? "border-primary bg-primary/5" : ""}`}>
      <div className="flex items-start gap-3">
        <RadioGroupItem value={value} id={`${id}-${value}`} disabled={disabled} className="mt-0.5" />
        <label htmlFor={`${id}-${value}`} className="flex-1">
          <span className="flex flex-wrap items-center gap-2 text-sm font-medium">{title} {status}</span>
          <span className="block text-sm text-muted-foreground">{facts}</span>
        </label>
      </div>
      <div className="space-y-3 pl-7 empty:hidden">{children}</div>
    </div>
  );
}

function Setting({ label, hint, children }: { label: string; hint: string; children: ReactNode }) {
  return (
    <label className="block max-w-md space-y-1">
      <span className="block text-sm font-medium">{label}</span>
      {children}
      <span className="block text-xs text-muted-foreground">{hint}</span>
    </label>
  );
}
