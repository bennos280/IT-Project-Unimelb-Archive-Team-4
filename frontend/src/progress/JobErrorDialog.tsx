import { useEffect, useRef } from "react";

// Displays the backend error for one bundle; the parent controls whether this dialog exists.
export default function JobErrorDialog({ bundle, message, onClose }: { bundle: string; message: string; onClose: () => void }) {
  // Keep a reference to the native dialog so it can open as a modal after mounting.
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  // Escape calls onClose too, keeping the parent state in sync with the visible dialog.
  return <dialog ref={dialog} className="progress-dialog" aria-labelledby="job-error-title" onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <h2 id="job-error-title">Transcription error</h2>
    <p>Bundle {bundle}</p>
    {/* Preserve error line breaks and allow long messages to wrap and scroll. */}
    <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: "50vh", overflowY: "auto" }}>{message}</pre>
    <div className="progress-dialog-actions"><button onClick={onClose}>Close</button></div>
  </dialog>;
}
