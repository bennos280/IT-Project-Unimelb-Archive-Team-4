import { Fragment, useEffect, useState, type MouseEvent } from "react";
import { Settings } from "lucide-react";

import TasksButton from "@/components/TasksButton";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { backendRequest } from "../progress/backend";

type Crumb = { label: string; href?: string; onClick?: (event: MouseEvent<HTMLAnchorElement>) => void };
type Series = { id: number; name: string };

// The one top bar: the app's name (home); where you are, as the series (switched from a list) and the levels below it, of which a
// phone shows only the last; and what's for the whole app, Settings and Tasks. A screen's own title and actions sit below it.
export default function AppHeader({ series, crumbs = [] }: { series?: Series; crumbs?: Crumb[] }) {
  return (
    <header className="flex min-h-14 flex-wrap items-center gap-x-3 gap-y-2 border-b px-4 py-2 sm:px-6">
      <a href="/" className="rounded-sm text-lg font-semibold tracking-tight">PrestCribe</a>
      {(series || crumbs.length > 0) && (
        <Breadcrumb className="min-w-0">
          <BreadcrumbList>
            <BreadcrumbSeparator />
            {series && <BreadcrumbItem><SeriesSwitcher current={series} /></BreadcrumbItem>}
            {crumbs.map((crumb, i) => {
              const last = i === crumbs.length - 1;
              return (
                <Fragment key={i}>
                  {(series || i > 0) && <BreadcrumbSeparator className={last ? undefined : "max-sm:hidden"} />}
                  <BreadcrumbItem className={last ? undefined : "max-sm:hidden"}>
                    {last ? <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                      : <BreadcrumbLink href={crumb.href} onClick={crumb.onClick}>{crumb.label}</BreadcrumbLink>}
                  </BreadcrumbItem>
                </Fragment>
              );
            })}
          </BreadcrumbList>
        </Breadcrumb>
      )}
      <div className="ml-auto flex items-center gap-2">
        <Button asChild variant="outline" size="icon" title="Settings">
          <a href="/?view=settings" aria-label="Settings"><Settings /></a>
        </Button>
        <TasksButton />
      </div>
    </header>
  );
}

// The series you're in, and a quick way to another (on the same tab) or to all of them.
function SeriesSwitcher({ current }: { current: Series }) {
  const [all, setAll] = useState<Series[]>([]);
  useEffect(() => {
    backendRequest<Series[]>("/collections?brief=true").then(setAll).catch(() => {});
  }, []);
  const listed = all.some((s) => s.id === current.id) ? all : [current, ...all];
  return (
    <NativeSelect aria-label="Series" size="sm" className="max-w-64 font-medium" value={current.id} onChange={(e) => {
      const tab = new URLSearchParams(location.search).get("view") === "setup" ? "&view=setup" : "";
      window.location.href = e.target.value ? `/?collection=${e.target.value}${tab}` : "/";
    }}>
      {listed.map((s) => <option key={s.id} value={s.id}>{s.name || "Series"}</option>)}
      <option value="">All series</option>
    </NativeSelect>
  );
}
