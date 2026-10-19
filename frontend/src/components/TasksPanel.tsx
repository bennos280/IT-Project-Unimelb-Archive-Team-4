import { useState } from "react";
import { ListChecks } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { jobStages } from "../progress/backend";
import { isActive, refreshTasks, useTasks, type Task } from "../progress/tasks";

const statusWords = { waiting: "Waiting", running: "Running", done: "Done", failed: "Failed" } as const;

// One task: what it is, how it stands, and for a running one how far it has got.
function TaskRow({ task }: { task: Task }) {
  const active = isActive(task);
  const percent = task.total > 0 ? Math.min(100, (task.done / task.total) * 100) : 0;
  const stage = task.kind === "bundle" && task.status === "running" && task.step
    ? (task.step === "group" ? "Grouping pages" : jobStages[task.step] ?? task.step)
    : "";
  const count = task.total > 0 ? `${task.done.toLocaleString()} of ${task.total.toLocaleString()} ${task.unit}` : "Starting…";
  return (
    <li className="grid gap-1.5 py-3">
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0 font-medium [overflow-wrap:anywhere]">
          {task.href ? <a href={task.href} className="hover:underline">{task.label}</a> : task.label}
        </span>
        <Badge variant={task.status === "failed" ? "destructive" : task.status === "running" ? "default" : "outline"}>
          {statusWords[task.status]}
        </Badge>
      </div>
      {active && (
        <Progress className="h-2" aria-label={`${task.label} progress`} value={percent}
          {...(task.total > 0 ? { "aria-valuenow": task.done, max: task.total } : {})} />
      )}
      {active && (
        <p className="text-muted-foreground">
          {task.status === "waiting" ? "Waiting to start" : [stage, count].filter(Boolean).join(" · ")}
        </p>
      )}
      {task.status === "failed" && task.error && <p className="text-destructive [overflow-wrap:anywhere]">{task.error}</p>}
    </li>
  );
}

// The header's Tasks button, with how many tasks are waiting or running, and the list it opens.
export default function TasksPanel() {
  const { tasks, error } = useTasks();
  const [open, setOpen] = useState(false);
  const active = (tasks ?? []).filter(isActive);
  const recent = (tasks ?? []).filter((task) => !isActive(task));
  return (
    <>
      <Button type="button" variant="outline" aria-label={active.length ? `Tasks, ${active.length} active` : "Tasks"}
        onClick={() => { setOpen(true); void refreshTasks(); }}>
        <ListChecks /> Tasks
        {active.length > 0 && <Badge aria-hidden="true" className="ml-1">{active.length}</Badge>}
      </Button>
      {open && (
        <Dialog open onOpenChange={(next) => { if (!next) setOpen(false); }}>
          <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>Tasks</DialogTitle>
              <DialogDescription>Work the app is doing in the background.</DialogDescription>
            </DialogHeader>
            {error && <p className="text-muted-foreground">Couldn't refresh the tasks: {error}</p>}
            {tasks && !tasks.length && <p className="text-muted-foreground">No tasks yet.</p>}
            {!tasks && !error && <p role="status" className="text-muted-foreground">Loading tasks…</p>}
            {active.length > 0 && (
              <section aria-label="Active tasks">
                <h3 className="font-medium text-muted-foreground">Active</h3>
                <ul className="divide-y">{active.map((task) => <TaskRow key={task.id} task={task} />)}</ul>
              </section>
            )}
            {recent.length > 0 && (
              <section aria-label="Recent tasks">
                <h3 className="font-medium text-muted-foreground">Recent</h3>
                <ul className="divide-y">{recent.map((task) => <TaskRow key={task.id} task={task} />)}</ul>
              </section>
            )}
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
