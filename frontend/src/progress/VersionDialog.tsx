import { useId, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { diffRows, versionName, type DiffRow, type Version } from "./versions";

const origin = (v: Version) => (v.reviewer ? `by ${v.reviewer}` : "from the files");
const saved = (v: Version) => (v.createdAt ? new Date(v.createdAt).toLocaleString() : "");

// The sign carries the meaning of a line; the tint only adds to it.
const PREFIX = { add: "+ ", del: "- ", same: "  " };
const TINT = {
  add: "bg-green-100 text-green-900 dark:bg-green-900/40 dark:text-green-200",
  del: "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-200",
  same: "text-muted-foreground",
  gap: "text-muted-foreground",
};
const rowText = (row: DiffRow) => (row.kind === "gap" ? `⋯ ${row.count} unchanged ${row.count === 1 ? "line" : "lines"}` : `${PREFIX[row.kind]}${row.text}`);

const Field = ({ term, children }: { term: string; children: ReactNode }) => (
  <>
    <dt className="text-muted-foreground">{term}</dt>
    <dd className="min-w-0 [overflow-wrap:anywhere]">{children}</dd>
  </>
);

// A version's text and its history; with changes on, the text as lines added to and removed from the version before it.
export default function VersionDialog({ versions, selected, onSelect, open, onOpenChange }: {
  versions: Version[]; selected: Version | null; onSelect: (v: Version) => void; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [changes, setChanges] = useState(false); // off at every opening, kept while another version is chosen
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) { setWasOpen(open); if (open) setChanges(false); }
  const switchId = useId();
  const history = selected ? versions.filter((v) => v.kind === selected.kind).sort((a, b) => b.number - a.number) : []; // newest first
  const before = selected && history.find((v) => v.number < selected.number);
  const rows = selected && before && changes ? diffRows(before.body, selected.body) : null;
  const count = (kind: DiffRow["kind"]) => rows?.filter((row) => row.kind === kind).length;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-5xl" aria-describedby={undefined}
        // Focus starts on the dialog itself, not on the first version.
        onOpenAutoFocus={(event) => { event.preventDefault(); (event.currentTarget as HTMLElement).focus(); }}>
        {selected && <>
          <DialogHeader><DialogTitle>{versionName(selected)}</DialogTitle></DialogHeader>
          <div className="grid min-w-0 gap-4 md:grid-cols-[16rem_minmax(0,1fr)]">
            <div role="group" aria-label="Versions" className="flex max-h-48 min-w-0 flex-col gap-2 overflow-y-auto md:max-h-[60vh]">
              {history.map((v) => (
                <Button key={v.id} variant={v.id === selected.id ? "secondary" : "ghost"} aria-pressed={v.id === selected.id} onClick={() => onSelect(v)}
                  className="h-auto w-full flex-col items-start justify-start gap-1 px-3 py-2 text-left font-normal whitespace-normal">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="font-medium">v{v.number}</span>
                    {v.current && <Badge variant="secondary">Current</Badge>}
                    <span className="text-muted-foreground">{[saved(v), origin(v)].filter(Boolean).join(" ")}</span>
                  </span>
                  {v.note && <span className="text-muted-foreground [overflow-wrap:anywhere]">{v.note}</span>}
                </Button>
              ))}
            </div>
            <div className="min-w-0 space-y-3">
              <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-1">
                <Field term="Last updated">{saved(selected) || "Not recorded"}</Field>
                <Field term="By">{selected.reviewer ?? "From the files"}</Field>
                <Field term="Status">{selected.current ? "Current: pages read from now on use this version" : `Replaced by v${history[0]?.number ?? selected.number}`}</Field>
                {selected.note && <Field term="Note">{selected.note}</Field>}
              </dl>
              <div className="flex w-fit items-center gap-2">
                <Switch id={switchId} checked={!!rows} disabled={!before} onCheckedChange={setChanges} />
                <Label htmlFor={switchId} className={before ? "cursor-pointer" : "text-muted-foreground"}>{before ? `Show changes from v${before.number}` : "First version"}</Label>
              </div>
              {rows && before ? <>
                <p className="text-muted-foreground">{`+${count("add")} −${count("del")} lines`}</p>
                <div role="group" aria-label={`Changes from v${before.number}`} className="max-h-[60vh] overflow-auto rounded-md bg-muted py-3 font-mono text-xs">
                  {rows.map((row, i) => <div key={i} className={`px-3 whitespace-pre-wrap [overflow-wrap:anywhere] ${TINT[row.kind]}`}>{rowText(row)}</div>)}
                </div>
              </> : <pre className="max-h-[60vh] overflow-auto rounded-md bg-muted p-3 font-mono text-xs whitespace-pre-wrap">{selected.body}</pre>}
            </div>
          </div>
        </>}
      </DialogContent>
    </Dialog>
  );
}
