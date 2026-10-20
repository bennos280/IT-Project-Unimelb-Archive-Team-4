import { Fragment, useEffect, useState, type MouseEvent } from "react";
import { ChevronsUpDown, Settings } from "lucide-react";
import { DropdownMenu } from "radix-ui";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { backendRequest } from "../progress/backend";

type Crumb = { label: string; href?: string; onClick?: (event: MouseEvent<HTMLAnchorElement>) => void };
type Series = { id: number; name: string };

// The one top bar: the app's name (home); where you are, as the series (a menu of its Items, the other series, and all
// of them) and the levels below it, of which a phone shows the last two; and what's for the whole app and Settings.
// A screen's own title and actions sit below it.
export default function AppHeader({ series, crumbs = [] }: { series?: Series; crumbs?: Crumb[] }) {
  return (
    <header className="flex min-h-14 flex-wrap items-center gap-x-3 gap-y-2 border-b px-4 py-2 sm:px-6">
      <a href="/" className="flex items-center gap-2 rounded-sm text-lg font-semibold tracking-tight">
        <img src="/favicon.svg" alt="" className="size-7" />PrestCribe
      </a>
      {(series || crumbs.length > 0) && (
        <Breadcrumb className="min-w-0">
          <BreadcrumbList>
            {series && (
              <>
                <BreadcrumbSeparator />
                <BreadcrumbItem><SeriesMenu current={series} /></BreadcrumbItem>
              </>
            )}
            {crumbs.map((crumb, i) => {
              const last = i === crumbs.length - 1;
              const phone = i < crumbs.length - 2 ? "max-sm:hidden" : undefined; // the level above, and where you are
              return (
                <Fragment key={i}>
                  <BreadcrumbSeparator className={phone} />
                  <BreadcrumbItem className={phone}>
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
      </div>
    </header>
  );
}

const menuItem = "flex rounded-sm px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground";
const menuLabel = "px-2 pt-1.5 pb-1 text-xs text-muted-foreground";

// The series you're in, as a menu of links: its Items, another series, or all of them.
function SeriesMenu({ current }: { current: Series }) {
  const [all, setAll] = useState<Series[]>([]);
  useEffect(() => {
    backendRequest<Series[]>("/collections?brief=true").then(setAll).catch(() => {});
  }, []);
  const others = all.filter((s) => s.id !== current.id);
  const name = current.name || "Series";
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="ghost" size="sm" className="max-w-64 font-medium" aria-label={`Series: ${name}`}>
          <span className="truncate">{name}</span>
          <ChevronsUpDown aria-hidden="true" className="text-muted-foreground" />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="start" sideOffset={4} className="z-50 max-h-96 min-w-56 overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md">
          <DropdownMenu.Label className={menuLabel}>{name}</DropdownMenu.Label>
          <DropdownMenu.Item asChild><a className={menuItem} href={`/?series=${current.id}`}>Items</a></DropdownMenu.Item>
          {others.length > 0 && (
            <>
              <DropdownMenu.Separator className="my-1 h-px bg-border" />
              <DropdownMenu.Label className={menuLabel}>Other series</DropdownMenu.Label>
              {others.map((s) => (
                <DropdownMenu.Item key={s.id} asChild><a className={menuItem} href={`/?series=${s.id}`}>{s.name}</a></DropdownMenu.Item>
              ))}
            </>
          )}
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <DropdownMenu.Item asChild><a className={menuItem} href="/">All series</a></DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
