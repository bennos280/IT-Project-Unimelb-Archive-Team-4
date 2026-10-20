import * as React from "react"
import { ChevronRight } from "lucide-react"
import { cn } from "cn"

function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto rounded-md border"
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b", className)}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

const INTERACTIVE = "a, button, input, select, textarea, label, [role=button], [role=checkbox], [role=menuitem]"

// clickable: a row that opens something, through the TableRowLink in it (with a TableOpenArrow at its end). A click anywhere
// else in the row clicks that link, unless it lands on another control or ends a text selection.
function TableRow({ className, clickable, onClick, ...props }: React.ComponentProps<"tr"> & { clickable?: boolean }) {
  function open(event: React.MouseEvent<HTMLTableRowElement>) {
    onClick?.(event)
    if (event.defaultPrevented || (event.target as Element).closest(INTERACTIVE) || window.getSelection()?.toString()) return
    const { ctrlKey, metaKey, shiftKey, altKey } = event  // so ctrl/cmd-click still opens a new tab
    event.currentTarget.querySelector("a[data-slot=table-row-link]")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, ctrlKey, metaKey, shiftKey, altKey }))
  }
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b transition-colors hover:bg-muted/50 has-aria-expanded:bg-muted/50 data-[state=selected]:bg-muted",
        clickable && "cursor-pointer hover:bg-muted focus-within:bg-muted",
        className
      )}
      onClick={clickable ? open : onClick}
      {...props}
    />
  )
}

// A clickable row's link: what the row opens, and how it's reached from the keyboard.
function TableRowLink({ className, ...props }: React.ComponentProps<"a">) {
  return (
    <a
      data-slot="table-row-link"
      className={cn(
        "rounded-sm font-medium outline-none hover:underline focus-visible:underline focus-visible:ring-3 focus-visible:ring-ring/50",
        className
      )}
      {...props}
    />
  )
}

// The arrow at the end of a clickable row.
function TableOpenArrow() {
  return <ChevronRight aria-hidden className="ml-auto size-4 text-muted-foreground" />
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-10 px-2 text-left align-middle font-medium whitespace-nowrap text-foreground [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "p-2 align-middle whitespace-nowrap [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableRowLink,
  TableOpenArrow,
  TableCell,
  TableCaption,
}
