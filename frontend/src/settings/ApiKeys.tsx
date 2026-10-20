import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { backendRequest } from "../progress/backend";

export type ApiKey = { provider: string; label: string; keysUrl: string; needsKey: boolean; saved: boolean; fromEnvironment: boolean };

const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// Transcribing through an AI company's API with your own key, or a model on this computer (Ollama): each one's key saved here,
// replaced or removed. Keys stay on this computer, never in the database or a PrestCribe file, and are never shown again.
export default function ApiKeys({ onChange }: { onChange: (keys: ApiKey[]) => void }) {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    backendRequest<ApiKey[]>("/api-keys").then((found) => { setKeys(found); onChange(found); })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load the API keys."));
  }, [onChange]);

  async function save(provider: string, key: string) {
    setBusy(provider);
    setError("");
    try {
      const found = await backendRequest<ApiKey[]>(`/api-keys/${provider}`, json("PUT", { key }));
      setKeys(found);
      onChange(found);
      setDrafts((d) => ({ ...d, [provider]: "" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the key.");
    }
    setBusy("");
  }

  return (
    <section id="api-keys" className="space-y-3">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">API keys</h2>
        <p className="text-sm text-muted-foreground">
          Or transcribe through an AI company's API with your own key, paid per page. Keys stay on this computer: never in a
          PrestCribe file.
        </p>
      </div>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      {keys && (
        <Card className="py-0">
          <CardContent className="divide-y px-0">
            {keys.map((k) => (
              <div key={k.provider} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-48 flex-1">
                  <p className="font-medium">{k.label}</p>
                  <p className="text-sm text-muted-foreground">
                    {!k.needsKey ? "No key: install Ollama, then download a model that reads images, like llama3.2-vision."
                      : k.saved ? "Key saved" : k.fromEnvironment ? "Key from this computer's settings" : "No key"}
                  </p>
                </div>
                {k.needsKey && (
                  <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); void save(k.provider, drafts[k.provider] ?? ""); }}>
                    <Input type="password" autoComplete="off" aria-label={`${k.label} key`} className="w-64"
                      placeholder={k.saved ? "Paste a new key to replace it" : "Paste a key"} value={drafts[k.provider] ?? ""}
                      onChange={(e) => setDrafts((d) => ({ ...d, [k.provider]: e.target.value }))} />
                    <Button type="submit" size="sm" disabled={busy !== "" || !(drafts[k.provider] ?? "").trim()}>Save</Button>
                    {k.saved && <Button type="button" size="sm" variant="outline" disabled={busy !== ""} onClick={() => save(k.provider, "")}>Remove</Button>}
                  </form>
                )}
                <a href={k.keysUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline">
                  {k.needsKey ? "Get a key" : "Get Ollama"} <ExternalLink aria-hidden="true" className="size-3.5" />
                </a>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </section>
  );
}
