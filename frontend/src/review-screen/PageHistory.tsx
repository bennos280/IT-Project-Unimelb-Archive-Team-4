import { Fragment, useRef, useState } from 'react';

type Row = Record<string, unknown>;
type Snapshot = Record<string, Row[]>;
type Change = { field: string; previous: unknown; saved: unknown };
type History = { revision: number; events: { id: string; time: string | null; reviewer: string; title: string; details: string; snapshot: Snapshot | null; changes?: Change[] }[] };
const text = (value: unknown) => value === null || value === undefined || value === '' ? '—' : String(value);
const label = (value: string) => value.replaceAll('_', ' ');
// Composite identifiers keep residents, children and annotations separate.
function fieldKey(row: Row): string {
  if (row.resident_no != null) return `Resident ${Number(row.resident_no) + 1} · ${row.resident_field_title}`;
  if (row.child_no != null) return `Child ${Number(row.child_no) + 1} · ${row.child_residence ?? row.residence}`;
  if (row.annotation_no != null) return `Annotation ${Number(row.annotation_no) + 1}`;
  return String(row.field_title ?? 'Field');
}
function snapshotChanges(snapshot: Snapshot): Change[] {
  const edits = new Map<string, Row>();
  [...(snapshot.edits ?? [])].sort((a, b) => Number(a.edit_id) - Number(b.edit_id)).forEach(edit => edits.set(fieldKey(edit), edit));
  return ['fields', 'resident_fields', 'other_children', 'annotations'].flatMap(table => (snapshot[table] ?? []).map(row => {
    const key = fieldKey(row);
    return { field: key, previous: row.text_raw, saved: edits.has(key) ? edits.get(key)!.edit_text : 'Not reviewed' };
  }));
}
function ChangesTable({ changes }: { changes: Change[] }) {
  return <table className="history-values"><thead><tr><th scope="col">Field</th><th scope="col">Previous value</th><th scope="col">Saved value</th></tr></thead>
    <tbody>{changes.map((change, index) => <tr key={index}><th scope="row">{label(change.field)}</th><td>{text(change.previous)}</td><td>{text(change.saved)}</td></tr>)}</tbody></table>;
}

// Viewing history never modifies a page or its pending review edits.
export default function PageHistory({ pageId }: { pageId: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function open() {
    setHistory(null); setExpanded([]); setError(''); setLoading(true);
    dialog.current?.showModal();
    try {
      const response = await fetch(`/api/page-history/${encodeURIComponent(pageId)}`);
      const body = await response.json().catch(() => null);
      if (response.status === 404 && body?.detail === 'Not Found') throw new Error('Page history is unavailable. Restart the backend to load the new history endpoint, then try again.');
      if (!response.ok || !body) throw new Error(body?.detail || 'Could not load page history.');
      setHistory(body);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load page history.'); }
    finally { setLoading(false); }
  }
  return <>
    <button type="button" onClick={() => void open()}>History</button>
    <dialog ref={dialog} className="page-history-dialog" aria-label="Page history">
      <h2>Page history</h2><p>Page {pageId}</p>
      {loading && <p role="status">Loading history…</p>}
      {error && <p role="alert">{error}</p>}
      {history && <>
        <p>Current revision: {history.revision}</p>
        <p>Snapshots show data before a page type change or retranscription. History is read-only.</p>
        {!history.events.length ? <p>No history has been recorded for this page yet.</p> : <div className="history-table-scroll"><table className="history-table">
          <thead><tr><th scope="col">Date and time</th><th scope="col">Reviewer</th><th scope="col">Action</th><th scope="col">Change</th><th scope="col">Details</th></tr></thead>
          <tbody>{history.events.map(event => {
            const isOpen = expanded.includes(event.id);
            const changes = event.snapshot ? snapshotChanges(event.snapshot) : event.changes ?? [];
            return <Fragment key={event.id}><tr>
              <td>{event.time ? new Date(event.time).toLocaleString() : 'Date unavailable'}</td><td>{event.reviewer}</td><td>{event.title}</td><td>{event.details}</td>
              <td><button type="button" aria-expanded={isOpen} aria-controls={`history-${event.id}`} onClick={() => setExpanded(ids => isOpen ? ids.filter(id => id !== event.id) : [...ids, event.id])}>{isOpen ? 'Hide details' : event.snapshot ? 'View snapshot' : 'View details'}</button></td>
            </tr>{isOpen && <tr id={`history-${event.id}`}><td colSpan={5} className="history-expanded">
              <h3>{event.title}</h3>
              {event.snapshot && <p>Previous data and the latest saved review values in this snapshot. “Not reviewed” means no saved review was present.</p>}
              {changes.length > 0 ? <ChangesTable changes={changes} /> : <p>{event.details}</p>}
              {!!event.snapshot?.flags?.length && <><h4>Previous flags</h4><table><thead><tr><th>Field</th><th>Flag</th><th>Reason</th></tr></thead><tbody>{event.snapshot.flags.map((flag, i) => <tr key={i}><td>{text(flag.field_title)}</td><td>{text(flag.kind)}</td><td>{text(flag.reason)}</td></tr>)}</tbody></table></>}
            </td></tr>}</Fragment>;
          })}</tbody>
        </table></div>}
      </>}
      <footer><button type="button" onClick={() => dialog.current?.close()}>Close</button></footer>
    </dialog>
  </>;
}
