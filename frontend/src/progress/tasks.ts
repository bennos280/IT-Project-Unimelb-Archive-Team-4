import { useSyncExternalStore } from "react";
import { backendRequest } from "./backend";

// One background job, as GET /jobs lists it: waiting and running ones, then the latest finished.
export type Task = {
  id: number;
  kind: "items" | "bundle" | "page" | "train";
  label: string;
  status: "waiting" | "running" | "done" | "failed";
  step: string | null;
  done: number;
  total: number;
  unit: "items" | "pages";
  error: string | null;
  updatedAt: string;
  collectionId: number | null;
  href: string | null;
};
export const isActive = (task: Task) => task.status === "waiting" || task.status === "running";

// The jobs are polled once for the whole page, whoever is looking: the header's Tasks button and the dashboard's banner.
// tasks is null until the first reply; a failed poll keeps the last list and says why.
type State = { tasks: Task[] | null; error: string };
let state: State = { tasks: null, error: "" };
const listeners = new Set<() => void>();
let timer: number | undefined;
let latest = 0;

// Fetches the jobs now; a reply that a newer fetch has overtaken is dropped.
export async function refreshTasks() {
  const request = ++latest;
  try {
    const tasks = await backendRequest<Task[]>("/jobs");
    if (request !== latest) return;
    if (!Array.isArray(tasks)) throw new Error("The server's list of tasks wasn't a list.");
    state = { tasks, error: "" };
  } catch (e) {
    if (request !== latest) return;
    state = { ...state, error: e instanceof Error ? e.message : "Could not load the tasks." };
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    void refreshTasks();
    timer = window.setInterval(() => { if (!document.hidden) void refreshTasks(); }, 5000);
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) window.clearInterval(timer);
  };
}

export const useTasks = () => useSyncExternalStore(subscribe, () => state);
