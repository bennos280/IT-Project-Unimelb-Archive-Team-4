import { useId } from "react";
export type ModelChoice = { model: string; provider: string; effort: string };

export type ModelData = {
  configured: ModelChoice;
  models: { provider: string | null; model: string; effort: string | null;
    promptVersion: number | null; templateVersion: number | null;
    pages: number; averageSeconds: number | null }[];
};

export function ModelFields({data,choice,setChoice,busy,onViewTable}:{data:ModelData;choice:ModelChoice;setChoice:(choice:ModelChoice)=>void;busy:boolean;onViewTable:()=>void}) {
  const listId = useId();
  return <>
      <label className="transcription-model">Provider
        <select value={choice.provider} disabled={busy} onChange={(e) => setChoice({ ...choice, provider: e.target.value, model: "" })}>
          <option value="claude">Claude</option><option value="codex">Codex</option>
        </select>
      </label>
      <label className="transcription-model">Model
        <input list={listId} value={choice.model} disabled={busy} onChange={(e) => setChoice({ ...choice, model: e.target.value })} placeholder="Choose or enter a model name" />
        <datalist id={listId}>{[...new Set([...(data.configured.provider === choice.provider ? [data.configured.model] : []), ...(choice.provider === "claude" ? ["sonnet", "opus", "haiku"] : []), ...data.models.filter((m) => m.provider === choice.provider && !m.model.includes("+")).map((m) => m.model)])].map((model) => <option key={model} value={model} />)}</datalist>
      </label>
      <label className="transcription-model">Effort
        <input value={choice.effort} disabled={busy} onChange={(e) => setChoice({ ...choice, effort: e.target.value })} />
      </label>
      <button onClick={() => onViewTable()}>View model table</button>
</>;
}
export function ModelTable({data}:{data:ModelData}) { return <>
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
</>; }
