import { Fragment, useEffect, useState, type MouseEvent } from "react";
import { Check, ChevronsUpDown, Link2, Settings, UserRound } from "lucide-react";
import { DropdownMenu } from "radix-ui";

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
import { keepPerson, storedPerson } from "../person";
import { backendRequest } from "../progress/backend";

type Crumb = { label: string; href?: string; onClick?: (event: MouseEvent<HTMLAnchorElement>) => void };
type Series = { id: number; name: string };

// The one top bar: the app's name (home); where you are, as the series (a menu of its Items, Accuracy and Setup, the other series, and all
// of them) and the levels below it, of which a phone shows the last two, then a copy of this page's link; and what's for the whole
// app, who is working, Settings and Tasks. A screen's own title and actions sit below it.
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
      <CopyLink />
      <div className="ml-auto flex items-center gap-2">
        <PersonMenu />
        <Button asChild variant="outline" size="icon" title="Settings">
          <a href="/?view=settings" aria-label="Settings"><Settings /></a>
        </Button>
        <TasksButton />
      </div>
    </header>
  );
}

// The app's own window has no address bar: this puts the page's address on the clipboard, and says so for two seconds.
function CopyLink() {
  const [said, setSaid] = useState("");
  useEffect(() => {
    if (!said) return;
    const timer = setTimeout(() => setSaid(""), 2000);
    return () => clearTimeout(timer);
  }, [said]);
  async function copy() {
    try {
      await navigator.clipboard.writeText(location.href);
      setSaid("Link copied");
    } catch {
      setSaid("Couldn't copy the link");
    }
  }
  return (
    <>
      <Button variant="ghost" size="icon-sm" aria-label="Copy link" title={said || "Copy link to this page"} onClick={copy}>
        {said === "Link copied" ? <Check aria-hidden="true" /> : <Link2 aria-hidden="true" />}
      </Button>
      {said && <span role="status" className="sr-only">{said}</span>}
    </>
  );
}

const menuItem = "flex rounded-sm px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground";
const menuLabel = "px-2 pt-1.5 pb-1 text-xs text-muted-foreground";

// Who is working, with a way to switch: home's welcome again, then back here. Nothing until someone is.
function PersonMenu() {
  const name = storedPerson()?.name;
  if (!name) return null;
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="ghost" size="sm" className="max-w-40" aria-label={`Working as ${name}`}>
          <UserRound aria-hidden="true" /><span className="truncate max-sm:sr-only">{name}</span>
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={4} className="z-50 min-w-48 rounded-md border bg-popover p-1 text-popover-foreground shadow-md">
          <DropdownMenu.Label className={menuLabel}>Working as {name}</DropdownMenu.Label>
          <DropdownMenu.Item className={menuItem} onSelect={() => { keepPerson(null); location.reload(); }}>Switch person</DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

// The series you're in, as a menu of links: its Items, Accuracy and Setup, another series (on the same tab), or all of them.
function SeriesMenu({ current }: { current: Series }) {
  const [all, setAll] = useState<Series[]>([]);
  useEffect(() => {
    backendRequest<Series[]>("/collections?brief=true").then(setAll).catch(() => {});
  }, []);
  const view = new URLSearchParams(location.search).get("view");
  const tab = view === "setup" || view === "accuracy" ? `&view=${view}` : "";
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
          <DropdownMenu.Item asChild><a className={menuItem} href={`/?series=${current.id}&view=accuracy`}>Accuracy</a></DropdownMenu.Item>
          <DropdownMenu.Item asChild><a className={menuItem} href={`/?series=${current.id}&view=setup`}>Setup</a></DropdownMenu.Item>
          {others.length > 0 && (
            <>
              <DropdownMenu.Separator className="my-1 h-px bg-border" />
              <DropdownMenu.Label className={menuLabel}>Other series</DropdownMenu.Label>
              {others.map((s) => (
                <DropdownMenu.Item key={s.id} asChild><a className={menuItem} href={`/?series=${s.id}${tab}`}>{s.name}</a></DropdownMenu.Item>
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
