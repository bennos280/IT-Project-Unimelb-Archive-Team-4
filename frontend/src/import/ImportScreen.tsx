import { useRef, useState } from "react";
import { Upload } from "lucide-react";

import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { backendRequest } from "../progress/backend";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type SelectedFile = { id: string; file: File; bundle: string; uploaded?: boolean };

// Select source files and upload them to the configured data directory.
export default function ImportScreen() {
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<SelectedFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [message, setMessage] = useState("");

  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");
  const pending = files.filter((item) => !item.uploaded);

  async function uploadFiles() {
    if (uploading || !pending.length || pending.some((item) => !/^[0-9]{1,30}$/.test(item.bundle.trim()))) return;
    setUploading(true);
    setMessage("");
    const failures: string[] = [];
    let saved = 0;
    try {
      for (const [index, item] of pending.entries()) {
        setProgress(`Uploading ${index + 1} of ${pending.length}: ${item.file.name}`);
        try {
          const query = new URLSearchParams({ bundle: item.bundle.trim(), filename: item.file.name });
          const response = await fetch(`/api/bundles/upload?${query}`, {
            method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: item.file,
          });
          if (!response.ok) {
            const result = await response.json().catch(() => null);
            throw new Error(typeof result?.detail === "string" ? result.detail : `Upload failed (${response.status}).`);
          }
          saved += 1;
          setFiles((current) => current.map((entry) => entry.id === item.id ? { ...entry, uploaded: true } : entry));
        } catch (error) {
          failures.push(`${item.file.name}: ${error instanceof Error ? error.message : "Upload failed."}`);
        }
      }
      setProgress(`${saved} of ${pending.length} files uploaded. Transcription has not started.`);
      setMessage(failures.join(" "));
    } finally {
      setUploading(false);
    }
  }

  // Accept supported files and avoid adding the same local file twice.
  function addFiles(incoming: FileList | File[]) {
    if (uploading) return;
    const accepted: SelectedFile[] = [];
    const rejected: string[] = [];
    for (const file of Array.from(incoming)) {
      if (!/\.(pdf|jpe?g|png)$/i.test(file.name) || file.size === 0 || file.size > 500 * 1024 * 1024) {
        rejected.push(file.name);
        continue;
      }
      accepted.push({
        id: JSON.stringify([file.name, file.size, file.lastModified]),
        file,
        bundle: "",
      });
    }
    setFiles((current) => {
      const ids = new Set(current.map((item) => item.id));
      return [
        ...current,
        ...accepted.filter((item) => {
          if (ids.has(item.id)) return false;
          ids.add(item.id);
          return true;
        }),
      ];
    });
    setMessage(
      rejected.length
        ? `Choose non-empty PDF, JPG or PNG files up to 500 MB. Not added: ${rejected.join(", ")}`
        : "",
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader crumbs={[{ label: "Import" }]} />
      <main className="mx-auto max-w-6xl space-y-4 p-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Import items</h1>
          <p className="text-sm text-muted-foreground">
            Upload scans (PDFs or page images) and enter an item number for each file.
            A PDF is a whole item. For page images, give every page of an item
            the same item number; pages are read in file name order.
          </p>
        </div>
        <div
          data-testid="dropzone"
          data-dragging={dragging}
          className="flex min-h-56 flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 text-sm text-muted-foreground data-[dragging=true]:border-foreground/50 data-[dragging=true]:bg-muted"
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={(event) => {
            if (
              !event.currentTarget.contains(event.relatedTarget as Node | null)
            )
              setDragging(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            addFiles(event.dataTransfer.files);
          }}
        >
          <Upload className="size-10" aria-hidden="true" />
          <strong className="text-base font-medium text-foreground">Drag and drop files here</strong>
          <span>or</span>
          <Button type="button" variant="outline" disabled={uploading} onClick={() => input.current?.click()}>
            Choose files
          </Button>
          <input
            ref={input}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png"
            hidden
            onChange={(event) => {
              if (event.target.files) addFiles(event.target.files);
              event.target.value = "";
            }}
          />
          <span>PDF, JPG or PNG</span>
        </div>
        {message && (
          <Alert variant="destructive">
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        )}
        <h2 aria-live="polite" className="pt-2 text-lg font-semibold tracking-tight">
          Selected files ({files.length})
        </h2>
        {files.length === 0 ? (
          <p className="text-sm text-muted-foreground">No files selected.</p>
        ) : (
            <Table className="min-w-[580px] table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[32%]">File</TableHead>
                  <TableHead className="w-[14%]">Size</TableHead>
                  <TableHead className="w-[36%]">Item number *</TableHead>
                  <TableHead className="w-[18%]">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {files.map((item, index) => {
                  const error = !/^[0-9]{1,30}$/.test(item.bundle.trim())
                    ? "Enter an item number containing 1–30 digits."
                    : "";
                  return (
                    <TableRow key={item.id} className="align-top">
                      <TableCell className="p-3 align-top whitespace-normal wrap-anywhere">
                        {item.file.name}
                        {item.uploaded && <Badge variant="secondary" className="mt-2 flex">Uploaded</Badge>}
                      </TableCell>
                      <TableCell className="p-3 align-top">
                        {item.file.size < 1024 * 1024
                          ? `${Math.max(1, Math.ceil(item.file.size / 1024))} KB`
                          : `${(item.file.size / (1024 * 1024)).toFixed(1)} MB`}
                      </TableCell>
                      <TableCell className="p-3 align-top whitespace-normal">
                        <Input
                          disabled={uploading || item.uploaded}
                          aria-label={`Item number for ${item.file.name}`}
                          aria-invalid={Boolean(error)}
                          aria-describedby={
                            error ? `bundle-error-${index}` : undefined
                          }
                          value={item.bundle}
                          placeholder="Enter item number"
                          required
                          onChange={(event) =>
                            setFiles((current) =>
                              current.map((entry) =>
                                entry.id === item.id
                                  ? { ...entry, bundle: event.target.value }
                                  : entry,
                              ),
                            )
                          }
                        />
                        {error && (
                          <p id={`bundle-error-${index}`} className="mt-2 text-xs text-destructive">
                            {error}
                          </p>
                        )}
                      </TableCell>
                      <TableCell className="p-3 align-top">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={uploading}
                          aria-label={`Remove ${item.file.name}`}
                          onClick={() =>
                            setFiles((current) =>
                              current.filter((entry) => entry.id !== item.id),
                            )
                          }
                        >
                          Remove
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
        )}
        <p className="text-sm text-muted-foreground">
          Each file must have an item number before import.
        </p>
        <footer className="flex flex-col items-start justify-between gap-4 border-t pt-4 sm:flex-row sm:items-center">
          <p id="import-availability" role="status" className="text-sm text-muted-foreground">
            {progress || "Files are saved to the data folder. Uploading does not start transcription."}
          </p>
          <Button onClick={uploadFiles} disabled={uploading || !pending.length || pending.some((item) => !/^[0-9]{1,30}$/.test(item.bundle.trim()))} aria-describedby="import-availability">
            Import files
          </Button>
        </footer>
        <OpenFile />
      </main>
    </div>
  );
}

// A PrestCribe file saved from Export on another computer, opened in place of everything here (what's here is kept as a backup).
function OpenFile() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function open() {
    if (!file || !window.confirm(`Replace everything in this PrestCribe with ${file.name}? What's here now is kept as a backup.`)) return;
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
    <section aria-labelledby="open-file" className="space-y-3 rounded-lg border p-5">
      <div>
        <h2 id="open-file" className="text-lg font-semibold tracking-tight">Open a PrestCribe file</h2>
        <p className="text-sm text-muted-foreground">
          Saved from Export on another computer: its series, setup, transcriptions and reviews. It replaces everything here.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Input type="file" accept=".prestcribe,.db" aria-label="PrestCribe file" className="max-w-sm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Button disabled={busy || !file} onClick={open}>{busy ? "Opening…" : "Open"}</Button>
      </div>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    </section>
  );
}
