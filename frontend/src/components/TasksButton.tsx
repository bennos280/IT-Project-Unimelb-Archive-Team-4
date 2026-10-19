import { ListChecks } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { isActive, useTasks } from "../progress/tasks";

// The header's link to the Tasks page, with how many tasks are waiting or running.
export default function TasksButton() {
  const { tasks } = useTasks();
  const active = (tasks ?? []).filter(isActive).length;
  return (
    <Button asChild variant="outline">
      <a href="/?view=tasks" aria-label={active ? `Tasks, ${active} active` : "Tasks"}>
        <ListChecks /> Tasks
        {active > 0 && <Badge aria-hidden="true" className="ml-1">{active}</Badge>}
      </a>
    </Button>
  );
}
