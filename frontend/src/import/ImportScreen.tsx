import { useState } from "react";
import { FolderOpen } from "lucide-react";

import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { backendRequest } from "../progress/backend";

// Opens a PrestCribe file in place of everything here: a series' setup (like the Prest survey's) or
// work saved from Export on another computer. What was here is kept as a backup (POST /state).
export default function ImportScreen() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function open() {
    if (!file || !window.confirm(`Replace everything here with ${file.name}? A backup of it is kept.`)) return;
    setBusy(true);
    setError("");
    try {
      await backendRequest("/state", { method: "POST", body: file });
      location.href = "/";
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open it.");
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader crumbs={[{ label: "Open a PrestCribe file" }]} />
      <main className="mx-auto max-w-3xl space-y-4 p-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Open a PrestCribe file</h1>
          <p className="text-sm text-muted-foreground">A series' setup, or work saved with Export. It replaces what's here; a backup is kept.</p>
        </div>
        <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8">
          <FolderOpen aria-hidden="true" className="size-8 text-muted-foreground" />
          <Input type="file" aria-label="PrestCribe file" className="max-w-sm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <Button disabled={busy || !file} onClick={open}>{busy ? "Opening…" : "Open"}</Button>
        </div>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      </main>
    </div>
  );
}
