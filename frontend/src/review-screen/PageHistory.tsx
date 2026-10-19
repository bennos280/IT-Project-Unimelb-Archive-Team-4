import { Fragment, useState } from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Spinner } from '@/components/ui/spinner';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

type Row = Record<string, unknown>;
type Snapshot = Record<string, Row[]>;
type Change = { field: string; previous: unknown; saved: unknown };
type History = { revision: number; events: { id: string; time: string | null; reviewer: string; title: string; details: string; snapshot: Snapshot | null; changes?: Change[] }[] };
const text = (value: unknown) => value === null || value === undefined || value === '' ? '—' : String(value);
const label = (value: string) => value.replaceAll('_', ' ');
const wrap = 'whitespace-pre-wrap align-top [overflow-wrap:anywhere]';
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
  return <Table className="table-fixed">
    <TableHeader><TableRow><TableHead scope="col">Field</TableHead><TableHead scope="col">Previous value</TableHead><TableHead scope="col">Saved value</TableHead></TableRow></TableHeader>
    <TableBody>{changes.map((change, index) => <TableRow key={index}><TableHead scope="row" className={`h-auto ${wrap}`}>{label(change.field)}</TableHead><TableCell className={wrap}>{text(change.previous)}</TableCell><TableCell className={wrap}>{text(change.saved)}</TableCell></TableRow>)}</TableBody>
  </Table>;
}

// Viewing history never modifies a page or its pending review edits.
export default function PageHistory({ pageId }: { pageId: string }) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [history, setHistory] = useState<History | null>(null);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function open() {
    setHistory(null); setExpanded([]); setError(''); setLoading(true);
    setDialogOpen(true);
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
    <Button type="button" variant="outline" size="sm" onClick={() => void open()}>History</Button>
    <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
      <DialogContent showCloseButton={false} onInteractOutside={e => e.preventDefault()} className="max-h-[90vh] overflow-y-auto sm:max-w-[1100px]">
        <DialogHeader>
          <DialogTitle className="text-lg">Page history</DialogTitle>
          <DialogDescription>Page {pageId}</DialogDescription>
        </DialogHeader>
        {loading && <p role="status" className="flex items-center gap-2 text-muted-foreground"><Spinner role={undefined} aria-hidden="true" />Loading history…</p>}
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        {history && <>
          <p>Current revision: {history.revision}</p>
          <p className="text-muted-foreground">Snapshots show data before a page type change or retranscription. History is read-only.</p>
          {!history.events.length ? <p>No history has been recorded for this page yet.</p> : <Table className="min-w-[680px] table-auto">
            <TableHeader><TableRow><TableHead scope="col">Date and time</TableHead><TableHead scope="col">Reviewer</TableHead><TableHead scope="col">Action</TableHead><TableHead scope="col">Change</TableHead><TableHead scope="col">Details</TableHead></TableRow></TableHeader>
            <TableBody>{history.events.map(event => {
              const isOpen = expanded.includes(event.id);
              const changes = event.snapshot ? snapshotChanges(event.snapshot) : event.changes ?? [];
              return <Fragment key={event.id}><TableRow>
                <TableCell className={wrap}>{event.time ? new Date(event.time).toLocaleString() : 'Date unavailable'}</TableCell><TableCell className={wrap}>{event.reviewer}</TableCell><TableCell className={wrap}>{event.title}</TableCell><TableCell className={wrap}>{event.details}</TableCell>
                <TableCell className="align-top"><Button type="button" variant="outline" size="sm" aria-expanded={isOpen} aria-controls={`history-${event.id}`} onClick={() => setExpanded(ids => isOpen ? ids.filter(id => id !== event.id) : [...ids, event.id])}>{isOpen ? 'Hide details' : event.snapshot ? 'View snapshot' : 'View details'}</Button></TableCell>
              </TableRow>{isOpen && <TableRow id={`history-${event.id}`}><TableCell colSpan={5} className="space-y-3 whitespace-normal bg-muted/30 p-4">
                <h3 className="font-medium">{event.title}</h3>
                {event.snapshot && <p className="text-muted-foreground">Previous data and the latest saved review values in this snapshot. “Not reviewed” means no saved review was present.</p>}
                {changes.length > 0 ? <ChangesTable changes={changes} /> : <p>{event.details}</p>}
                {!!event.snapshot?.flags?.length && <><h4 className="font-medium">Previous flags</h4><Table className="table-auto"><TableHeader><TableRow><TableHead>Field</TableHead><TableHead>Flag</TableHead><TableHead>Reason</TableHead></TableRow></TableHeader><TableBody>{event.snapshot.flags.map((flag, i) => <TableRow key={i}><TableCell className={wrap}>{text(flag.field_title)}</TableCell><TableCell className={wrap}>{text(flag.kind)}</TableCell><TableCell className={wrap}>{text(flag.reason)}</TableCell></TableRow>)}</TableBody></Table></>}
              </TableCell></TableRow>}</Fragment>;
            })}</TableBody>
          </Table>}
        </>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>;
}
