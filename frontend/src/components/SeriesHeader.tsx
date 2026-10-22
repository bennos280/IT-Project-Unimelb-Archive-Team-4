import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { cn } from "cn";

import { ARCHIVE } from "../progress/backend";

export type SeriesSummary = { id: number; name: string; archiveIdentifier?: string | null; archiveSeries?: number | null };

// A series' own heading on its screens: its name, where it is on the archive, its actions, and its tabs: Items (its dashboard),
// Accuracy (how often reviewers changed what the models read) and Setup (how its pages are read and checked).
export default function SeriesHeader({ series, tab, actions }: { series: SeriesSummary; tab: "items" | "accuracy" | "setup"; actions?: ReactNode }) {
  const tabs = [["items", "Items", `/?series=${series.id}`], ["accuracy", "Accuracy", `/?series=${series.id}&view=accuracy`],
    ["setup", "Setup", `/?series=${series.id}&view=setup`]] as const;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight [overflow-wrap:anywhere]">{series.name || "Series"}</h1>
          {series.archiveIdentifier && (
            <p className="text-sm text-muted-foreground">
              {series.archiveSeries ? (
                <a href={`${ARCHIVE}/nodes/view/${series.archiveSeries}`} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:underline">
                  {series.archiveIdentifier} <ExternalLink aria-hidden="true" className="size-3.5" />
                </a>
              ) : series.archiveIdentifier}
            </p>
          )}
        </div>
        {actions}
      </div>
      <nav aria-label="Series" className="flex gap-6 border-b">
        {tabs.map(([key, label, href]) => (
          <a key={key} href={href} aria-current={tab === key ? "page" : undefined}
            className={cn("-mb-px border-b-2 px-0.5 pb-2 text-sm font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
              tab === key ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
            {label}
          </a>
        ))}
      </nav>
    </div>
  );
}
