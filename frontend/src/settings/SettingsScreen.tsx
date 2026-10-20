import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { Check, Circle, CircleAlert, CircleCheck, CircleX, TriangleAlert, type LucideIcon } from "lucide-react";

import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { backendRequest, providerNames } from "../progress/backend";
import type { ModelChoice } from "../progress/ModelControls";
import ApiKeys, { type ApiKey } from "./ApiKeys";
import PageSorting from "./PageSorting";
import About from "./About";

const hasKey = (k: ApiKey) => !k.needsKey || k.saved || k.fromEnvironment; // Ollama needs none
import TranscriptionDefaults from "./TranscriptionDefaults";

type Connection = {
  installed: boolean; signedIn: boolean; method: string | null; plan: string | null; version: string | null;
  warnings: string[]; error: string | null; login: { running: boolean; exitCode: number | null };
};
type Connections = Record<"claude" | "codex", Connection>;
type TestState = { running: boolean; result?: { ok: boolean; seconds: number; model: string; message: string }; error?: string };
const jsonPost = { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" };

const providers = [
  { id: "claude", name: "Claude Code", signIn: "Open Claude Code sign-in", command: "claude auth login",
    install: "https://code.claude.com/docs/en/setup", usage: "https://claude.ai/settings/usage" },
  { id: "codex", name: "Codex CLI", signIn: "Open Codex sign-in", command: "codex login",
    install: "https://developers.openai.com/codex/cli", usage: "https://chatgpt.com/codex/settings/usage" },
] as const;

// The badge shows Ready only when signed in with the subscription (not an API key).
function badge(c: Connection): { label: string; variant: "default" | "secondary" | "outline" | "destructive"; icon: LucideIcon } {
  if (!c.installed) return { label: "Not installed", variant: "outline", icon: CircleX };
  if (c.error) return { label: "Status check failed", variant: "destructive", icon: CircleAlert };
  if (!c.signedIn) return { label: "Not signed in", variant: "secondary", icon: Circle };
  if (c.method === "claude.ai" || c.method === "chatgpt") return { label: "Ready", variant: "default", icon: CircleCheck };
  return { label: "Signed in with an API key", variant: "outline", icon: TriangleAlert };
}

// "<plan> · <version>" under the card title; parts that are unknown are left out.
function subtitle(c: Connection): string {
  const plan = !c.signedIn ? null : c.method === "api_key" ? "API key" : c.method === "chatgpt" ? "ChatGPT plan"
    : c.plan ? `${c.plan[0].toUpperCase() + c.plan.slice(1)} plan` : null;
  return [plan, c.version].filter(Boolean).join(" · ");
}
const TEST_NOTE = "Sends one tiny request on your plan.";

// One line when a transcription can start, else what is still needed. saved: the saved choice (null: none; undefined: not loaded); signedIn: provider id -> signed in (null: not loaded).
// The status element is always there, empty and unseen until the line appears, so screen readers announce it.
function Checklist({ saved, signedIn, show }: { saved: ModelChoice | null | undefined; signedIn: Record<string, boolean> | null; show: (tab: string) => void }) {
  const loaded = saved !== undefined && signedIn !== null;
  // A plain click shows the link's tab and section here, keeping unsaved edits; other clicks (new tab, window) follow the href.
  function follow(e: MouseEvent<HTMLAnchorElement>) {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    const { searchParams, hash } = new URL(e.currentTarget.href);
    show(searchParams.get("tab")!);
    history.replaceState(null, "", e.currentTarget.href);
    requestAnimationFrame(() => document.getElementById(hash.slice(1))?.scrollIntoView());
  }
  const name = saved && (providerNames[saved.provider] ?? saved.provider);
  const signed = loaded && (saved ? Boolean(signedIn[saved.provider]) : Object.values(signedIn).some(Boolean));
  const line = loaded && signed ? saved : null;
  const items = [
    { done: saved !== null, text: "Choose a transcription model", action: "Choose model", href: "?view=settings&tab=transcription#transcription-defaults" },
    { done: signed, text: name ? `Sign in to ${name}, or give it a key` : "Sign in to Claude Code or the Codex CLI, or add an API key",
      action: "Sign in or add a key",
      href: `?view=settings&tab=accounts${saved && !["claude", "codex"].includes(saved.provider) ? "#api-keys" : "#connections"}` },
  ];
  return (
    <>
      <div role="status" className={line ? "flex items-start gap-2 text-sm" : "sr-only"}>
        {line && (
          <>
            <CircleCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-green-700 dark:text-green-400" />
            <span>
              <span className="font-medium">Ready to transcribe</span>
              <span className="text-muted-foreground"> · {line.model} · {line.effort} on {name}</span>
            </span>
          </>
        )}
      </div>
      {loaded && !line && (
        <section aria-labelledby="ready-heading"
          className="flex gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="min-w-0 flex-1 space-y-3">
            <h2 id="ready-heading" className="font-semibold">Finish setup to start transcribing</h2>
            <ul className="space-y-2">
              {items.map(({ done, text, href, action }) => (
                <li key={text} className="flex flex-wrap items-center gap-2 text-sm">
                  {done ? <CircleCheck aria-hidden="true" className="size-4 text-green-700 dark:text-green-400" />
                    : <Circle aria-hidden="true" className="size-4 text-amber-700 dark:text-amber-300" />}
                  <span className="flex-1">{text}<span className="sr-only">{done ? ": done" : ": to do"}</span></span>
                  {!done && <Button size="sm" variant="outline" className="bg-background" asChild><a href={href} onClick={follow}>{action}</a></Button>}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </>
  );
}

const TABS = ["transcription", "accounts", "about"];

// Settings in tabs, the one shown kept in the URL (?tab=): Transcription (the model, and page sorting), Accounts and API keys, and
// About (the version and updates, where this copy keeps its files, help); they stay loaded, as the checklist above counts them.
export default function SettingsScreen() {
  const [tab, setTab] = useState(() => TABS.find((t) => t === new URLSearchParams(location.search).get("tab")) ?? "transcription");
  function show(next: string) {
    const url = new URL(location.href);
    url.searchParams.set("tab", next);
    url.hash = "";
    history.replaceState(null, "", url);
    setTab(next);
  }
  const [data, setData] = useState<Connections | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [signingOut, setSigningOut] = useState<(typeof providers)[number] | null>(null);
  const [saved, setSaved] = useState<ModelChoice | null | undefined>(undefined); // the saved transcription choice; undefined until loaded
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [keysVersion, setKeysVersion] = useState(0); // a key saved or removed: the model lists load again
  const keysChanged = useCallback((keys: ApiKey[]) => { setApiKeys(keys); setKeysVersion((n) => n + 1); }, []);
  const [tests, setTests] = useState<Partial<Record<string, TestState>>>({});
  const polling = Boolean(data && (data.claude.login.running || data.codex.login.running));

  // Only the latest request may set the state, so a slow older reply can't undo a newer one.
  const latest = useRef(0);
  const load = useCallback(() => {
    const mine = ++latest.current;
    return backendRequest<Connections>("/connections").then((result) => {
      if (mine !== latest.current) return;
      setData(result);
      setLoadError("");
    }).catch((e) => {
      if (mine === latest.current) setLoadError(e instanceof Error ? e.message : "Could not load sign-in status.");
    });
  }, []);

  // Load on open and when the window regains focus (after signing in elsewhere).
  useEffect(() => {
    load();
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);

  // Poll only while a sign-in is running.
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [polling, load]);

  async function login(provider: string, method: "POST" | "DELETE") {
    setBusy(true);
    setActionError("");
    try {
      await backendRequest(`/connections/${provider}/login`, method === "POST" ? jsonPost : { method });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Request failed.");
    }
    await load();
    setBusy(false);
  }

  async function signOut(provider: string) {
    setBusy(true);
    setActionError("");
    try {
      await backendRequest(`/connections/${provider}/logout`, jsonPost);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Request failed.");
    }
    setSigningOut(null);
    setTests((t) => ({ ...t, [provider]: undefined }));
    await load();
    setBusy(false);
  }

  async function test(provider: string) {
    setTests((t) => ({ ...t, [provider]: { running: true } }));
    try {
      const result = await backendRequest<NonNullable<TestState["result"]>>(`/connections/${provider}/test`, jsonPost);
      setTests((t) => ({ ...t, [provider]: { running: false, result } }));
    } catch (e) {
      setTests((t) => ({ ...t, [provider]: { running: false, error: e instanceof Error ? e.message : "Request failed." } }));
    }
  }

  // What stops each provider from transcribing, for the warning under the defaults.
  const notReady: Record<string, string> = Object.fromEntries([
    ...(data ? providers.filter((p) => badge(data[p.id]).label !== "Ready").map((p) => [p.id, badge(data[p.id]).label]) : []),
    ...apiKeys.filter((k) => !hasKey(k)).map((k) => [k.provider, "No key"])]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader crumbs={[{ label: "Settings" }]} />
      <TooltipProvider>
        <main className="space-y-8 p-6">
          <div className="flex flex-col gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
              <p className="text-sm text-muted-foreground">How pages are read, and the accounts that read them</p>
            </div>
            <Checklist saved={saved} show={show} signedIn={data && { claude: data.claude.signedIn, codex: data.codex.signedIn,
              ...Object.fromEntries(apiKeys.map((k) => [k.provider, hasKey(k)])) }} />
          </div>
          <Tabs value={tab} onValueChange={show} className="gap-6">
            <TabsList aria-label="Settings">
              <TabsTrigger value="transcription">Transcription</TabsTrigger>
              <TabsTrigger value="accounts">Accounts and API keys</TabsTrigger>
              <TabsTrigger value="about">About</TabsTrigger>
            </TabsList>
            <TabsContent value="transcription" forceMount className="space-y-8 data-[state=inactive]:hidden">
          <TranscriptionDefaults notReady={notReady} onSaved={setSaved} version={keysVersion} />
          <PageSorting />
            </TabsContent>
            <TabsContent value="accounts" forceMount className="space-y-8 data-[state=inactive]:hidden">
          <section id="connections" className="space-y-3">
            <div>
              <h2 className="text-xl font-semibold tracking-tight">Accounts</h2>
              <p className="text-sm text-muted-foreground">
                Uses your own Claude or ChatGPT subscription on this computer. Usage counts against it.
              </p>
            </div>
            {loadError && (
              <Alert variant="destructive">
                <AlertDescription className="flex flex-wrap items-center gap-2">
                  {loadError} <Button variant="outline" size="sm" onClick={load}>Try again</Button>
                </AlertDescription>
              </Alert>
            )}
            {actionError && <Alert variant="destructive"><AlertDescription>{actionError}</AlertDescription></Alert>}
            {!data && !loadError && (
              <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
                <Spinner role="presentation" aria-hidden="true" /> Checking sign-in status…
              </p>
            )}
            {data && (
              <div className="grid gap-4 md:grid-cols-2">
                {providers.map((p) => {
                  const c = data[p.id];
                  const { label, variant, icon: Icon } = badge(c);
                  const code = <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">{p.command}</code>;
                  const canSignIn = c.installed && !c.error && label !== "Ready";
                  const subscription = c.method === "claude.ai" || c.method === "chatgpt";
                  const t = tests[p.id];
                  const line = subtitle(c);
                  return (
                    <Card key={p.id} role="group" aria-label={p.name}>
                      <CardHeader>
                        <CardTitle className="flex flex-wrap items-center gap-2">
                          {p.name}
                          {saved?.provider === p.id && <Badge variant="secondary">Used for transcription</Badge>}
                        </CardTitle>
                        {line && <CardDescription>{line}</CardDescription>}
                        <CardAction><Badge variant={variant}><Icon aria-hidden="true" className="size-3" />{label}</Badge></CardAction>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        {c.warnings.map((w) => (
                          <Alert key={w}><AlertDescription>{w}</AlertDescription></Alert>
                        ))}
                        {!c.installed && (
                          <div className="flex flex-wrap items-center gap-2">
                            <Button asChild variant="outline">
                              <a href={p.install} target="_blank" rel="noopener noreferrer">Install {p.name}</a>
                            </Button>
                            <Button variant="outline" onClick={load}>Check again</Button>
                          </div>
                        )}
                        {c.error && (
                          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                            {c.error} <Button variant="outline" size="sm" onClick={load}>Check again</Button>
                          </div>
                        )}
                        {c.installed && !c.error && c.signedIn && (
                          <div className="space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button variant="outline" disabled={t?.running || busy} aria-describedby={`${p.id}-test-note`} onClick={() => test(p.id)}>
                                    {t?.running && <Spinner role="presentation" aria-hidden="true" />} Test connection
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent side="bottom" sideOffset={6}>{TEST_NOTE}</TooltipContent>
                              </Tooltip>
                              <span id={`${p.id}-test-note`} className="sr-only">{TEST_NOTE}</span>
                              {subscription && (
                                <Button asChild variant="outline">
                                  <a href={p.usage} target="_blank" rel="noopener noreferrer">Check usage</a>
                                </Button>
                              )}
                              <Button variant="ghost" className="ml-auto text-destructive hover:bg-destructive/10 hover:text-destructive" disabled={busy}
                                onClick={() => setSigningOut(p)}>Sign out</Button>
                            </div>
                            {t?.running && <p role="status" className="text-sm text-muted-foreground">Waiting for a reply…</p>}
                            {t?.result?.ok && (
                              <p role="status" className="flex items-center gap-1.5 text-sm text-green-700 dark:text-green-400">
                                <Check className="size-4" /> Works · replied in {t.result.seconds} s ({t.result.model})
                              </p>
                            )}
                            {t?.result && !t.result.ok && <Alert variant="destructive"><AlertDescription>{t.result.message}</AlertDescription></Alert>}
                            {t?.error && <Alert variant="destructive"><AlertDescription>{t.error}</AlertDescription></Alert>}
                          </div>
                        )}
                        {c.login.running && label !== "Ready" ? (
                          <div className="space-y-2 text-sm">
                            <p role="status" className="flex items-center gap-2">
                              <Spinner role="presentation" aria-hidden="true" />
                              Finish signing in in the browser window that opened.
                            </p>
                            <Button variant="outline" disabled={busy} onClick={() => login(p.id, "DELETE")}>Cancel</Button>
                            <p className="text-xs text-muted-foreground">
                              Browser didn't open? Run {code} in a terminal, then come back.
                            </p>
                          </div>
                        ) : (
                          <>
                            {c.login.exitCode !== null && c.login.exitCode !== 0 && !c.signedIn && (
                              <Alert variant="destructive">
                                <AlertDescription>
                                  Sign-in didn't finish. Try again, or run {code} in a terminal.
                                </AlertDescription>
                              </Alert>
                            )}
                            {canSignIn && (
                              <Button disabled={busy} onClick={() => login(p.id, "POST")}>{p.signIn}</Button>
                            )}
                          </>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </section>
          <ApiKeys onChange={keysChanged} />
            </TabsContent>
            <TabsContent value="about" forceMount className="space-y-8 data-[state=inactive]:hidden">
              <About />
            </TabsContent>
          </Tabs>
        </main>
      </TooltipProvider>
      <Dialog open={signingOut !== null} onOpenChange={(open) => { if (!open && !busy) setSigningOut(null); }}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Sign out of {signingOut?.name}?</DialogTitle>
            <DialogDescription>
              This signs {signingOut?.name} out on this computer, including in your terminal. Transcription with it stops until you sign in again.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setSigningOut(null)}>Cancel</Button>
            <Button variant="destructive" disabled={busy} onClick={() => signingOut && signOut(signingOut.id)}>Sign out</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
