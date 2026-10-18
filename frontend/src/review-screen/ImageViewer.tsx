import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { Info, Plus, Minus, Maximize, Search } from "lucide-react";
import type { SurveyPage } from "./model";
import { getPageName, isTextPage } from "./model";
import { getSourceRegion } from "./fieldLocations";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

// Render the source scan with zoom, drag-to-pan, fit, fullscreen and a mapped-field overlay.

export default function ImageViewer({
  page,
  selection,
}: {
  page: SurveyPage;
  selection: { fieldId: string; token: number } | null;
}) {
  const [zoom, setZoom] = useState(100),
    [error, setError] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const image = useRef<HTMLImageElement>(null);
  const [loaded, setLoaded] = useState(false);
  // The selection whose note the reviewer dismissed by zooming themselves.
  const [dismissed, setDismissed] = useState<number | null>(null);
  const selectedField = page.fields.find((f) => f.id === selection?.fieldId);
  const region = useMemo(
    () =>
      selectedField
        ? (selectedField.sourceRegion ??
          getSourceRegion(page.type, selectedField.id))
        : undefined,
    [page.type, selectedField],
  );
  // A field with no mapped region shows the whole card and says why nothing is highlighted;
  // an annotation shows where the transcription saw it even when its area is highlighted.
  const isAnnotation = !!selectedField?.id.startsWith("annotations.");
  const note =
    selection && selectedField && loaded && !error && !isTextPage(page.type) && selection.token !== dismissed
      ? isAnnotation
        ? selectedField.location
          ? `Annotation: ${selectedField.location}`
          : region
            ? ""
            : "Annotations can be anywhere on the card"
        : region
          ? ""
          : "This field has no fixed place on the card"
      : "";
  const fitWholeCard = useEffectEvent(() => fitToPage());
  // Zoom first, then centre the selected region after the resized image has rendered.
  useEffect(() => {
    if (!selection || !selectedField || !loaded || isTextPage(page.type)) return;
    // Zooming by hand keeps the reviewer's zoom.
    if (selection.token === dismissed) return;
    if (!region) {
      const frame = requestAnimationFrame(fitWholeCard);
      return () => cancelAnimationFrame(frame);
    }
    let second = 0;
    const first = requestAnimationFrame(() => {
      // A box wider than 42.5% of the card zooms less so that it fits.
      setZoom(Math.min(200, Math.max(100, 85 / region.width)));
      second = requestAnimationFrame(() => {
        if (!viewport.current || !stage.current) return;
        const box = stage.current;
        viewport.current.scrollTo({
          left:
            (region.x + region.width / 2) * box.clientWidth -
            viewport.current.clientWidth / 2,
          top:
            (region.y + region.height / 2) * box.clientHeight -
            viewport.current.clientHeight / 2,
          behavior: "smooth",
        });
      });
    });
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
    };
  }, [selection, selectedField, region, loaded, page.type, dismissed]);
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  // Zooming by hand hides the current selection's note.
  const dismiss = () => setDismissed(selection?.token ?? null);
  // Increment zoom within the supported 1–300 percent range.
  const change = (delta: number) => {
    dismiss();
    setZoom((z) => Math.max(1, Math.min(300, z + delta)));
  };
  // Calculate a scale that fits the full image inside the viewport, accounting for borders and padding.
  function fitToPage() {
    const container = viewport.current;
    const scan = image.current;
    if (!container || !scan?.naturalWidth || !scan.naturalHeight) return;
    const style = getComputedStyle(container);
    // Use the content box: fullscreen mode adds padding around the scan.
    const width =
      container.offsetWidth -
      parseFloat(style.borderLeftWidth) -
      parseFloat(style.borderRightWidth) -
      parseFloat(style.paddingLeft) -
      parseFloat(style.paddingRight);
    const height =
      container.offsetHeight -
      parseFloat(style.borderTopWidth) -
      parseFloat(style.borderBottomWidth) -
      parseFloat(style.paddingTop) -
      parseFloat(style.paddingBottom);
    if (width <= 2 || height <= 2) return;
    const scale = Math.min(
      (width - 2) / scan.naturalWidth,
      (height - 2) / scan.naturalHeight,
    );
    // Zoom is expressed as a percentage of the viewer width.
    setZoom(((scan.naturalWidth * scale) / width) * 100);
    container.scrollTo(0, 0);
  }
  return (
    <div className="@container flex min-h-0 flex-1 flex-col">
      <div className="relative flex min-h-0 flex-1 flex-col">
        <div
          role="status"
          className={
            note
              ? "pointer-events-none absolute top-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full border bg-background/95 px-3.5 py-1.5 text-sm font-medium whitespace-nowrap text-muted-foreground shadow-sm"
              : "sr-only"
          }
        >
          {note && <Info className="size-4" aria-hidden />}
          {note}
        </div>
        <div
          className="min-h-[180px] flex-1 cursor-grab touch-none overflow-auto rounded-md border bg-muted outline-none focus-visible:ring-3 focus-visible:ring-ring/50 active:cursor-grabbing [&:fullscreen]:p-5"
          ref={viewport}
          tabIndex={0}
          aria-label="Survey scan. Use arrow keys to pan and plus or minus to zoom."
          onKeyDown={(e) => {
            // Handle keyboard zoom while the viewport has focus.
            if (e.key === "+" || e.key === "=") change(25);
            if (e.key === "-") change(-25);
          }}
          onPointerDown={(e) => {
            // Record the pointer and scroll origin so dragging pans the image.
            if (e.button !== 0) return;
            const el = e.currentTarget;
            drag.current = {
              x: e.clientX,
              y: e.clientY,
              left: el.scrollLeft,
              top: el.scrollTop,
            };
            el.setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => {
            // Apply the drag displacement to the viewport scroll position.
            if (!drag.current) return;
            e.currentTarget.scrollLeft =
              drag.current.left - e.clientX + drag.current.x;
            e.currentTarget.scrollTop =
              drag.current.top - e.clientY + drag.current.y;
          }}
          onPointerUp={() => (drag.current = null)}
          onPointerCancel={() => (drag.current = null)}
        >
          {error ? (
            <div className="p-8 text-center text-muted-foreground">
              The source image could not be loaded. Check its URL in database.
            </div>
          ) : (
            <div
              className="relative shrink-0 leading-[0]"
              ref={stage}
              style={{ width: `${zoom}%` }}
            >
              <img
                ref={image}
                className="block h-auto w-full max-w-none select-none"
                src={page.imageUrl}
                alt={`Original ${getPageName(page.type)} for survey ${page.id}`}
                draggable={false}
                onLoad={() => setLoaded(true)}
                onError={() => setError(true)}
              />
              {region && (
                <div
                  className="pointer-events-none absolute box-border rounded-lg bg-primary/20 ring-1 ring-primary/40"
                  aria-label={`Highlighted source: ${selectedField?.label}`}
                  style={{
                    left: `${region.x * 100}%`,
                    top: `${region.y * 100}%`,
                    width: `${region.width * 100}%`,
                    height: `${region.height * 100}%`,
                  }}
                />
              )}
            </div>
          )}
        </div>
      </div>
      <div className="mt-2.5 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 rounded-lg border p-1.5 @max-[570px]:grid-cols-2">
        <div className="flex items-center gap-2 justify-self-start">
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Zoom out"
            disabled={zoom <= 1}
            onClick={() => change(-25)}
          >
            <Minus />
          </Button>
          <output className="min-w-10 text-center text-sm font-semibold">
            {Math.round(zoom)}%
          </output>
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Zoom in"
            disabled={zoom === 300}
            onClick={() => change(25)}
          >
            <Plus />
          </Button>
        </div>
        <div className="flex justify-center gap-2 @max-[570px]:order-3 @max-[570px]:col-span-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!loaded || error}
            onClick={() => {
              dismiss();
              fitToPage();
            }}
          >
            <Maximize /> Fit to Page
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              // Reset to the viewer-width baseline and return to the image origin.
              dismiss();
              setZoom(100);
              viewport.current?.scrollTo(0, 0);
            }}
          >
            <Search /> Actual Size (100%)
          </Button>
        </div>
        <div className="flex items-center gap-2 justify-self-end">
          <Badge variant="outline" className="max-[1150px]:hidden">
            Preview Mode
          </Badge>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Fullscreen scan"
            onClick={() => {
              // Toggle fullscreen for the scan viewport.
              if (document.fullscreenElement) void document.exitFullscreen();
              else void viewport.current?.requestFullscreen();
            }}
          >
            <Maximize />
          </Button>
        </div>
      </div>
    </div>
  );
}
