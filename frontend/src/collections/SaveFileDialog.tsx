import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

const CHOICES = [
  { value: "everything", title: "Everything", detail: "The series, their setup, and every page read and reviewed. To carry on elsewhere, or keep a copy." },
  { value: "setup", title: "Setup only", detail: "The series and how they're read, with no pages. To start reading from scratch." },
] as const;

// Saving everything here as a PrestCribe file (GET /state), or only the series' setup.
export default function SaveFileDialog({ onClose }: { onClose: () => void }) {
  const id = useId();
  const [content, setContent] = useState("everything");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    setSaving(true);
    setError("");
    try {
      const response = await fetch(`/api/state?content=${content}`);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status}).`);
      }
      const name = response.headers.get("Content-Disposition")?.match(/filename="?([^";]+)"?/)?.[1]
        ?? `PrestCribe ${new Date().toISOString().slice(0, 10)}.prestcribe`;
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000); // Safari cancels a download whose URL is revoked before it starts
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The file couldn't be saved.");
      setSaving(false);
    }
  }
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Save a PrestCribe file</DialogTitle>
          <DialogDescription>Open it in PrestCribe on another computer, from its home page.</DialogDescription>
        </DialogHeader>
        <RadioGroup aria-label="What to save" value={content} onValueChange={setContent} className="gap-4">
          {CHOICES.map((c) => (
            <div key={c.value} className="flex items-start gap-3">
              <RadioGroupItem value={c.value} id={`${id}-${c.value}`} className="mt-0.5" />
              <label htmlFor={`${id}-${c.value}`}>
                <span className="block text-sm font-medium">{c.title}</span>
                <span className="block text-sm text-muted-foreground">{c.detail}</span>
              </label>
            </div>
          ))}
        </RadioGroup>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={saving} onClick={save}>{saving ? "Saving…" : "Save"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
