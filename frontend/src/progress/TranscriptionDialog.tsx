import { useEffect, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { backendRequest, itemTitle, type AvailableBundle } from "./backend";

import { ModelFields, ModelTable, type ModelChoice, type ModelData } from "./ModelControls";
export type { ModelChoice } from "./ModelControls";

const NO_CHOICE: ModelChoice = { model: "", provider: "", effort: "" }; // nothing prefilled

export default function TranscriptionDialog({ source, busy, error, onClose, onStart }: {
  source: AvailableBundle; busy: boolean; error: string;
  onClose: () => void; onStart: (choice: ModelChoice) => void;
}) {
  const [choice, setChoice] = useState<ModelChoice>(NO_CHOICE);
  const [table, setTable] = useState(false);
  const [data, setData] = useState<ModelData | null>(null);
  const [failure, setFailure] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    backendRequest<ModelData>("/transcription-models").then((result) => {
      if (active) { setData(result); setChoice(result.configured ?? NO_CHOICE); setFailure(""); }
    }).catch((e) => { if (active) setFailure(e instanceof Error ? e.message : "Could not load models."); });
    return () => { active = false; };
  }, [attempt]);
  return <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
    <DialogContent showCloseButton={false}
      className={table ? "max-h-[90dvh] overflow-y-auto sm:max-w-5xl" : "max-h-[90dvh] overflow-y-auto sm:max-w-lg"}
      onInteractOutside={(event) => event.preventDefault()}>
      <DialogHeader>
        <DialogTitle>{table ? "Transcription models" : "Transcribe scans"}</DialogTitle>
        <DialogDescription>{itemTitle(source.name)}</DialogDescription>
      </DialogHeader>
      {failure && <Alert variant="destructive"><AlertDescription className="flex flex-wrap items-center gap-2">{failure} <Button variant="outline" size="sm" onClick={() => setAttempt((n) => n + 1)}>Try again</Button></AlertDescription></Alert>}
      {!data && !failure && <p role="status" className="flex items-center gap-2 text-muted-foreground"><Spinner role="presentation" aria-hidden="true" />Loading model information…</p>}
      {data && (table ? <>
        <ModelTable data={data} />
      </> : <>
        <ModelFields data={data} choice={choice} setChoice={setChoice} busy={busy} onViewTable={()=>setTable(true)} />
        <p className="text-muted-foreground">Your selected model and effort are saved with this job. Use a model supported by the selected provider. Transcription may incur model charges.</p>
      </>)}
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <DialogFooter>
        {table ? <Button variant="outline" onClick={() => setTable(false)}>Back to transcription</Button> : <>
          <Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !data || Boolean(failure) || !choice.provider || !choice.model.trim() || !choice.effort.trim()} onClick={() => onStart(choice)}>{busy ? "Starting…" : "Start transcription"}</Button>
        </>}
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}
