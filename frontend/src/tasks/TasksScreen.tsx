import { useEffect } from "react";

import AppHeader from "@/components/AppHeader";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableOpenArrow, TableRow, TableRowLink } from "@/components/ui/table";
import { jobStages } from "../progress/backend";
import { isActive, refreshTasks, useTasks, type Task } from "../progress/tasks";

const statusWords = { waiting: "Waiting", running: "Running", done: "Done", failed: "Failed" } as const;

// How far a task has got: while it's active a bar and its count (and a transcription's stage), once finished its count.
function TaskProgress({ task }: { task: Task }) {
  const count = task.total > 0 ? `${task.done.toLocaleString()} of ${task.total.toLocaleString()} ${task.unit}` : "";
  if (!isActive(task)) return <span className="text-muted-foreground">{count || "—"}</span>;
  const stage = task.kind === "bundle" && task.status === "running" && task.step
    ? (task.step === "group" ? "Grouping pages" : jobStages[task.step] ?? task.step)
    : "";
  return (
    <div className="flex max-w-xs flex-col gap-1.5">
      <span>{task.status === "waiting" ? "Waiting to start" : [stage, count || "Starting…"].filter(Boolean).join(" · ")}</span>
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
                <TableRow key={task.id} clickable={Boolean(task.href)}>
                  <TableCell className="whitespace-normal [overflow-wrap:anywhere]">
                    {task.href ? <TableRowLink href={task.href}>{task.label}</TableRowLink> : <span className="font-medium">{task.label}</span>}
                    {task.status === "failed" && task.error && <p className="text-destructive">{task.error}</p>}
                  </TableCell>
                  <TableCell className="whitespace-normal">{task.series}</TableCell>
                  <TableCell>
                    <Badge variant={task.status === "failed" ? "destructive" : task.status === "running" ? "default" : "outline"}>
                      {statusWords[task.status]}
                    </Badge>
                  </TableCell>
                  <TableCell className="whitespace-normal"><TaskProgress task={task} /></TableCell>
                  <TableCell className="text-muted-foreground">{task.updatedAt ? new Date(task.updatedAt).toLocaleString() : ""}</TableCell>
                  <TableCell>{task.href && <TableOpenArrow />}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </main>
    </div>
  );
}
