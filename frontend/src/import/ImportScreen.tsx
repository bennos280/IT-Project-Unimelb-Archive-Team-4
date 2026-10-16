import { useRef, useState } from "react";
import { ArrowLeft, Upload } from "lucide-react";
import "./import.css";

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
      if (!/\.(pdf|jpe?g|png)$/i.test(file.name) || file.size === 0 || file.size > 250 * 1024 * 1024) {
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
        ? `Choose non-empty PDF, JPG or PNG files up to 250 MB. Not added: ${rejected.join(", ")}`
        : "",
    );
  }

  return (
    <div className="import-screen">
      <header className="import-header">
        <div>
          <h1>Wilfred Prest Survey</h1>
        </div>
        <a href="/">
          <ArrowLeft size={18} /> Back to all bundles
        </a>
      </header>
      <main className="import-main">
        <h2>Import survey bundles</h2>
        <p className="import-intro">
          Upload your survey files and enter a bundle number for each file.
        </p>
        <div
          className={`import-dropzone ${dragging ? "dragging" : ""}`}
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
          <Upload size={52} aria-hidden="true" />
          <strong>Drag and drop files here</strong>
          <span>or</span>
          <button type="button" disabled={uploading} onClick={() => input.current?.click()}>
            Choose files
          </button>
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
          <p role="alert" className="import-error">
            {message}
          </p>
        )}
        <h3 aria-live="polite">Selected files ({files.length})</h3>
        {files.length === 0 ? (
          <p className="import-muted">No files selected.</p>
        ) : (
          <div className="import-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Size</th>
                  <th>Bundle number *</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {files.map((item, index) => {
                  const error = !/^[0-9]{1,30}$/.test(item.bundle.trim())
                    ? "Enter a bundle number containing 1–30 digits."
                    : "";
                  return (
                    <tr key={item.id}>
                      <td>{item.file.name}{item.uploaded && <small>Uploaded</small>}</td>
                      <td>
                        {item.file.size < 1024 * 1024
                          ? `${Math.max(1, Math.ceil(item.file.size / 1024))} KB`
                          : `${(item.file.size / (1024 * 1024)).toFixed(1)} MB`}
                      </td>
                      <td>
                        <input
                          disabled={uploading || item.uploaded}
                          aria-label={`Bundle number for ${item.file.name}`}
                          aria-invalid={Boolean(error)}
                          aria-describedby={
                            error ? `bundle-error-${index}` : undefined
                          }
                          value={item.bundle}
                          placeholder="Enter bundle number"
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
                          <small id={`bundle-error-${index}`}>{error}</small>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          disabled={uploading}
                          aria-label={`Remove ${item.file.name}`}
                          onClick={() =>
                            setFiles((current) =>
                              current.filter((entry) => entry.id !== item.id),
                            )
                          }
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="import-muted">
          Each file must have a bundle number before import.
        </p>
        <footer className="import-footer">
          <p id="import-availability" role="status">
            {progress || "Files are saved to the data folder. Uploading does not start transcription."}
          </p>
          <button onClick={uploadFiles} disabled={uploading || !pending.length || pending.some((item) => !/^[0-9]{1,30}$/.test(item.bundle.trim()))} aria-describedby="import-availability">
            Import files
          </button>
        </footer>
      </main>
    </div>
  );
}
