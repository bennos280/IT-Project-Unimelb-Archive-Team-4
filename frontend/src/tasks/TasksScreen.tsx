import { useEffect, useState } from "react";

import AppHeader from "@/components/AppHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableOpenArrow, TableRow, TableRowLink } from "@/components/ui/table";
import { backendRequest, jobStages } from "../progress/backend";
import { isActive, refreshTasks, useTasks, type Task } from "../progress/tasks";

const statusWords = { waiting: "Waiting", running: "Running", done: "Done", failed: "Failed" } as const;
const opens = { items: "Open the series", bundle: "Open the item", page: "Open the page", train: "" } as const;
const when = (time: string | null) => (time ? new Date(time).toLocaleString() : "");
// What the worker calls each step, in words.
const stepWords: Record<string, string> = { ...jobStages, adding: "Adding items", train: "Training page sorting" };
const lower = (words: string) => words.charAt(0).toLowerCase() + words.slice(1); // "Transcribing PDF pages": "transcribing PDF pages"

function StatusBadge({ task }: { task: Task }) {
  return (
    <Badge variant={task.status === "failed" ? "destructive" : task.status === "running" ? "default" : "outline"}>
      {statusWords[task.status]}
    </Badge>
  );
}

// How far a task has got, in words: "12,400 of 60,772 read", "Transcribing pages · 40 of 227 pages", "Waiting to start".
function progressWords(task: Task) {
  const count = task.total > 0 ? `${task.done.toLocaleString()} of ${task.total.toLocaleString()} ${task.unit === "items" ? "read" : task.unit}` : "";
  if (!isActive(task)) return count || "—";
  if (task.status === "waiting") return "Waiting to start";
  const stage = task.kind === "bundle" && task.step ? stepWords[task.step] ?? task.step : "";
  return [stage, count || "Starting…"].filter(Boolean).join(" · ");
}

// How far a task has got in the Tasks list: while it's active its words and a bar, once finished its count.
function TaskProgress({ task }: { task: Task }) {
  if (!isActive(task)) return <span className="text-muted-foreground">{progressWords(task)}</span>;
  return (
    <div className="flex max-w-xs flex-col gap-1.5">
      <span>{progressWords(task)}</span>
      <Progress className="h-2" aria-label={`${task.label} progress`} value={task.total > 0 ? Math.min(100, (task.done / task.total) * 100) : 0}
        {...(task.total > 0 ? { "aria-valuenow": task.done, max: task.total } : {})} />
    </div>
  );
}

// The app's background work: what's waiting or running, then what finished lately, each with its series and progress.
export default function TasksScreen() {
  const { tasks, error } = useTasks();
  useEffect(() => void refreshTasks(), []);
  const listed = [...(tasks ?? []).filter(isActive), ...(tasks ?? []).filter((task) => !isActive(task))];
  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader crumbs={[{ label: "Series", href: "/" }, { label: "Tasks" }]} />
      <main className="space-y-4 p-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tasks</h1>
          <p className="text-sm text-muted-foreground">
            Work the app is doing in the background: what's waiting or running, then what finished lately.
          </p>
        </div>
        {error && <p className="text-muted-foreground">Couldn't refresh the tasks: {error}</p>}
        {!tasks && !error && <p role="status" className="text-muted-foreground">Loading tasks…</p>}
        {tasks && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Task</TableHead>
                <TableHead>Series</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead className="w-10"><span className="sr-only">Open</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {listed.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">No tasks yet.</TableCell>
                </TableRow>
              ) : listed.map((task) => (
                <TableRow key={task.id} clickable>
                  <TableCell className="whitespace-normal [overflow-wrap:anywhere]">
                    <TableRowLink href={`/?view=tasks&task=${task.id}`}>{task.label}</TableRowLink>
                    {task.status === "failed" && task.error && <p className="text-destructive">{task.error}</p>}
                  </TableCell>
                  <TableCell className="whitespace-normal">{task.series}</TableCell>
                  <TableCell><StatusBadge task={task} /></TableCell>
                  <TableCell className="whitespace-normal"><TaskProgress task={task} /></TableCell>
                  <TableCell className="text-muted-foreground">{when(task.updatedAt)}</TableCell>
                  <TableCell><TableOpenArrow /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </main>
    </div>
  );
}

// A task as its page has it (GET /jobs/<id>/log): its log, oldest first; the items its latest count says it has added and skipped;
// an items task's series' items now; and whether a worker is running (null: unknown, no worker has run since it could tell).
type TaskLog = Task & {
  startedAt: string | null; log: { time: string; text: string }[]; added: number | null; skipped: number | null;
  seriesItems: number | null; workerRunning: boolean | null;
};

// A span of seconds, roughly: "1 h 45 min", "4 min", "under a minute".
function duration(seconds: number) {
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return "under a minute";
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

// A line of the worker's log in words: it writes "started: items", "step: transcribe", "done" and "failed during transcribe".
function said(text: string) {
  const [, what, step] = text.match(/^(started|step|done|failed during|stopped during)\b:?\s*(.*)$/) ?? [];
  if (what === "started" || what === "done") return what === "started" ? "Started" : "Done";
  if (what === "step") return stepWords[step] ?? step;
  if (what) return `${what === "failed during" ? "Failed" : "Stopped"}${stepWords[step] ? ` while ${lower(stepWords[step])}` : ""}`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl font-semibold tracking-tight">{value}</CardTitle>
        {note && <CardDescription>{note}</CardDescription>}
      </CardHeader>
    </Card>
  );
}

// A time, without its date when that's the day the page loaded.
const at = (time: string, now: number) =>
  new Date(time).toDateString() === new Date(now).toDateString() ? new Date(time).toLocaleTimeString() : new Date(time).toLocaleString();
const counts = new Set(["adding", "transcribe"]); // the steps whose progress counts what the task is doing

// One task (/?view=tasks&task=<id>): its status, series and times on a line; how far it has got, with its time left and speed while
// it counts; what it has added; and its lines in the worker's log, newest first. It refreshes every 5 seconds until it's finished.
export function TaskScreen({ id }: { id: string }) {
  const [task, setTask] = useState<TaskLog | null>(null);
  const [now, setNow] = useState(0); // when it was loaded
  const [error, setError] = useState("");
  const active = !task || isActive(task);
  useEffect(() => {
    const load = () => backendRequest<TaskLog>(`/jobs/${encodeURIComponent(id)}/log`)
      .then((loaded) => { setTask(loaded); setNow(Date.now()); setError(""); })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load the task."));
    void load();
    if (!active) return;
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 5000);
    return () => window.clearInterval(timer);
  }, [id, active]);

  if (!task) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <AppHeader crumbs={[{ label: "Series", href: "/" }, { label: "Tasks", href: "/?view=tasks" }, { label: "Task" }]} />
        <main className="p-6">
          <p role={error ? undefined : "status"} className="text-muted-foreground">{error ? `Couldn't load the task: ${error}` : "Loading the task…"}</p>
        </main>
      </div>
    );
  }
  // Speed and time left from when the step that counts began (the start, for a log without steps), while the worker runs it.
  const running = task.status === "running" && task.workerRunning !== false;
  const stepAt = [...task.log].reverse().find((entry) => entry.text.startsWith("step:"))?.time ?? task.startedAt;
  const seconds = running && task.step && counts.has(task.step) && stepAt ? (Date.parse(task.updatedAt) - Date.parse(stepAt)) / 1000 : 0;
  const rate = seconds > 0 && task.done > 0 ? task.done / seconds : 0; // a second
  const left = rate > 0 && task.total > task.done ? (task.total - task.done) / rate : 0; // seconds
  const lastAt = task.log.at(-1)?.time; // a finished task's end, even one the worker was cut off in
  const started = !task.startedAt ? (task.status === "waiting" ? "not started yet" : "")
    : `started ${at(task.startedAt, now)}${running ? `, running for ${duration((now - Date.parse(task.startedAt)) / 1000)}`
      : !isActive(task) && lastAt ? `, took ${duration((Date.parse(lastAt) - Date.parse(task.startedAt)) / 1000)}` : ""}`;
  const facts = [
    left > 0 && `About ${duration(left)} left`,
    left > 0 && `done around ${new Date(now + left * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`,
    rate > 0 && (rate >= 1 ? `${Math.round(rate).toLocaleString()} ${task.unit} a second` : `${Math.round(rate * 60).toLocaleString()} ${task.unit} a minute`),
  ].filter(Boolean).join(" · ");
  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader crumbs={[{ label: "Series", href: "/" }, { label: "Tasks", href: "/?view=tasks" }, { label: task.label }]} />
      <main className="space-y-4 p-6">
        {error && <p className="text-muted-foreground">Couldn't refresh the task: {error}</p>}
        <div className="space-y-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h1 className="text-2xl font-semibold tracking-tight [overflow-wrap:anywhere]">{task.label}</h1>
            {task.href && <Button asChild variant="outline"><a href={task.href}>{opens[task.kind]}</a></Button>}
          </div>
          <p data-testid="task-summary" className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <StatusBadge task={task} />
            {[task.series, started, task.updatedAt && `updated ${at(task.updatedAt, now)}`].filter(Boolean).join(" · ")}
          </p>
        </div>
        {task.workerRunning === false && isActive(task) && (
          <Alert>
            <AlertDescription>
              {task.status === "waiting"
                ? <span>The worker isn't running, so this task won't start. Start it with <code>uv run worker</code>.</span>
                : <span>The worker isn't running, so this task has stopped. Start it with <code>uv run worker</code>, then run the task again.</span>}
            </AlertDescription>
          </Alert>
        )}
        {task.error && <Alert variant="destructive"><AlertDescription>{task.error}</AlertDescription></Alert>}
        <Card data-testid="task-progress">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-baseline justify-between gap-3 text-xl font-semibold tracking-tight">
              <span>{progressWords(task)}</span>
              {task.total > 0 && <span className="text-muted-foreground">{Math.floor((task.done / task.total) * 100)}%</span>}
            </CardTitle>
            {facts && <CardDescription>{facts}</CardDescription>}
          </CardHeader>
        </Card>
        {(task.added !== null || task.seriesItems !== null) && (
          <div className="grid grid-cols-3 gap-2 sm:gap-4">
            {task.added !== null && <Stat label="Added" value={task.added.toLocaleString()} />}
            {task.skipped !== null && <Stat label="Skipped" value={task.skipped.toLocaleString()} note="Listed already, Reading Room only or not scanned" />}
            {task.seriesItems !== null && <Stat label="In the series now" value={task.seriesItems.toLocaleString()} />}
          </div>
        )}
        <section className="space-y-3 pt-2">
          <h2 className="text-xl font-semibold tracking-tight">Log</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-48">Time</TableHead>
                <TableHead>What happened</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {task.log.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={2} className="py-8 text-center text-muted-foreground">Nothing logged for this task.</TableCell>
                </TableRow>
              ) : task.log.map((entry, n) => (
                <TableRow key={n}>
                  <TableCell className="text-muted-foreground">{at(entry.time, now)}</TableCell>
                  <TableCell className="whitespace-normal">{said(entry.text)}</TableCell>
                </TableRow>
              )).reverse()}
            </TableBody>
          </Table>
        </section>
      </main>
    </div>
  );
}
