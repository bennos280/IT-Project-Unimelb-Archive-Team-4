import { useEffect, useRef, useState } from "react";
import { backendRequest, type AvailableBundle } from "./backend";

export type ModelChoice = { model: string; provider: string; effort: string };

type ModelData = {
  configured: ModelChoice;
  models: { provider: string | null; model: string; effort: string | null;
    promptVersion: number | null; templateVersion: number | null;
    pages: number; averageSeconds: number | null }[];
};

export default function TranscriptionDialog({ source, busy, error, onClose, onStart }: {
  source: AvailableBundle; busy: boolean; error: string;
  onClose: () => void; onStart: (choice: ModelChoice) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [choice, setChoice] = useState<ModelChoice>({ model: "", provider: "claude", effort: "" });
  const [table, setTable] = useState(false);
  const [data, setData] = useState<ModelData | null>(null);
  const [failure, setFailure] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    let active = true;
    backendRequest<ModelData>("/transcription-models").then((result) => {
      if (active) { setData(result); setChoice(result.configured); setFailure(""); }
    }).catch((e) => { if (active) setFailure(e instanceof Error ? e.message : "Could not load models."); });
    return () => { active = false; };
  }, [attempt]);
  return <dialog className={`progress-dialog ${table ? "model-table-dialog" : ""}`} ref={dialog}
    aria-labelledby="transcribe-title" onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <h2 id="transcribe-title">{table ? "Transcription models" : "Transcribe scans"}</h2>
    <p>Bundle {source.name}</p>
    {failure && <p role="alert">{failure} <button onClick={() => setAttempt((n) => n + 1)}>Try again</button></p>}
    {!data && !failure && <p role="status">Loading model information…</p>}
    {data && (table ? <>
      <p><strong>Current default:</strong> {data.configured.model} · {data.configured.provider} · {data.configured.effort} effort</p>
      <p>Recorded transcription configurations for pages currently in the database. Historical model names do not guarantee current availability.</p>
      <div className="model-table-scroll"><table className="progress-table">
        <thead><tr>{["Model", "Provider", "Effort", "Prompt version", "Template version", "Pages processed", "Average processing time / page"].map((label) => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>{data.models.map((model, index) => <tr key={index}>
          <td>{model.model}</td><td>{model.provider ?? "Not recorded"}</td><td>{model.effort ?? "Not recorded"}</td>
          <td>{model.promptVersion ?? "Not recorded"}</td><td>{model.templateVersion ?? "Not recorded"}</td>
          <td>{model.pages}</td><td>{model.averageSeconds === null ? "Not recorded" : `${model.averageSeconds.toFixed(1)} s`}</td>
        </tr>)}</tbody>
      </table></div>
      {!data.models.length && <p>No model history recorded yet.</p>}
      <p>Cost and accuracy are not recorded in this data. Names joined by “+” indicate multiple models reported for a transcription, rather than one selectable model.</p>
    </> : <>
      <label className="transcription-model">Provider
        <select value={choice.provider} disabled={busy} onChange={(e) => setChoice({ ...choice, provider: e.target.value, model: "" })}>
          <option value="claude">Claude</option><option value="codex">Codex</option>
        </select>
      </label>
      <label className="transcription-model">Model
        <input list="transcription-model-options" value={choice.model} disabled={busy} onChange={(e) => setChoice({ ...choice, model: e.target.value })} placeholder="Choose or enter a model name" />
        <datalist id="transcription-model-options">{[...new Set([...(data.configured.provider === choice.provider ? [data.configured.model] : []), ...(choice.provider === "claude" ? ["sonnet", "opus", "haiku"] : []), ...data.models.filter((m) => m.provider === choice.provider && !m.model.includes("+")).map((m) => m.model)])].map((model) => <option key={model} value={model} />)}</datalist>
      </label>
      <label className="transcription-model">Effort
        <input value={choice.effort} disabled={busy} onChange={(e) => setChoice({ ...choice, effort: e.target.value })} />
      </label>
      <button onClick={() => setTable(true)}>View model table</button>
      <p>Your selected model and effort are saved with this job. Use a model supported by the selected provider. Transcription may incur model charges.</p>
    </>)}
    {error && <p role="alert">{error}</p>}
    <div className="progress-dialog-actions">
      {table ? <button onClick={() => setTable(false)}>Back to transcription</button> : <>
        <button disabled={busy} onClick={onClose}>Cancel</button>
        <button disabled={busy || !data || Boolean(failure) || !choice.model.trim() || !choice.effort.trim()} onClick={() => onStart(choice)}>{busy ? "Starting…" : "Start transcription"}</button>
      </>}
    </div>
  </dialog>;
}
