import { useEffect, useRef, useState } from "react";
import { backendRequest, type AvailableBundle } from "./backend";

import { ModelFields, ModelTable, type ModelChoice, type ModelData } from "./ModelControls";
export type { ModelChoice } from "./ModelControls";

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
      <ModelTable data={data} />
    </> : <>
      <ModelFields data={data} choice={choice} setChoice={setChoice} busy={busy} onViewTable={()=>setTable(true)} />
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
