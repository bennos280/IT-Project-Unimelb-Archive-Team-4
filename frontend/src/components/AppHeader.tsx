import { Fragment, type MouseEvent, type ReactNode } from "react";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

type Crumb = { label: string; href?: string; onClick?: (event: MouseEvent<HTMLAnchorElement>) => void };

// Shared top bar: the app name, a breadcrumb trail ending at the current screen, and screen actions.
export default function AppHeader({ crumbs, actions }: { crumbs: Crumb[]; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-b px-6 py-4">
      <div className="min-w-0 space-y-1">
        <a href="/" className="flex items-center gap-2 rounded-sm text-2xl font-semibold tracking-tight">
          <img src="/favicon.svg" alt="" className="size-7" />PrestCribe
        </a>
        <Breadcrumb>
          <BreadcrumbList>
            {crumbs.map((crumb, i) => (
              <Fragment key={i}>
                {i > 0 && <BreadcrumbSeparator />}
                <BreadcrumbItem>
                  {i === crumbs.length - 1 ? (
                    <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                  ) : (
                    <BreadcrumbLink href={crumb.href} onClick={crumb.onClick}>{crumb.label}</BreadcrumbLink>
                  )}
                </BreadcrumbItem>
              </Fragment>
            ))}
          </BreadcrumbList>
        </Breadcrumb>
      </div>
      {actions}
    </header>
  );
}
