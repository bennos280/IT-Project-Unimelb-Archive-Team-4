import { ListChecks } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { isActive, useTasks } from "../progress/tasks";

// The header's link to the Tasks page, with how many tasks are waiting or running.
export default function TasksButton() {
  const { tasks } = useTasks();
  const active = (tasks ?? []).filter(isActive).length;
  return (
    <Button asChild variant="outline" size={active ? "default" : "icon"} title="Tasks">
      <a href="/?view=tasks" aria-label={active ? `Tasks, ${active} active` : "Tasks"}>
        <ListChecks />
        {active > 0 && <Badge aria-hidden="true">{active}</Badge>}
      </a>
    </Button>
  );
}
