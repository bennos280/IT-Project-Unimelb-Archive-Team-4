import { useEffect, useMemo, useRef, useState } from "react";
import { Plus, Minus, Maximize, Search } from "lucide-react";
import type { SurveyPage } from "./model";
import { getPageName } from "./model";
import { getSourceRegion } from "./fieldLocations";

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
  const selectedField = page.fields.find((f) => f.id === selection?.fieldId);
  const region = useMemo(
    () =>
      selectedField ? getSourceRegion(page.type, selectedField.id) : undefined,
    [page.type, selectedField],
  );
  // Zoom first, then centre the selected region after the resized image has rendered.
  useEffect(() => {
    if (!selection || !region || !loaded || page.type === "notes") return;
    let second = 0;
    const first = requestAnimationFrame(() => {
      setZoom(200);
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
  }, [selection, region, loaded, page.type]);
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  // Increment zoom within the supported 1–300 percent range.
  const change = (delta: number) => {
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
    <div className="viewer">
      <div
        className="image-viewport"
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
          <div className="empty">
            The source image could not be loaded. Check its URL in database.
          </div>
        ) : (
          <div className="scan-stage" ref={stage} style={{ width: `${zoom}%` }}>
            <img
              ref={image}
              src={page.imageUrl}
              alt={`Original ${getPageName(page.type)} for survey ${page.id}`}
              draggable={false}
              style={{ width: "100%" }}
              onLoad={() => setLoaded(true)}
              onError={() => setError(true)}
            />
            {region && (
              <div
                className="source-highlight"
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
      <div className="image-tools">
        <div className="zoom">
          <button
            aria-label="Zoom out"
            disabled={zoom <= 1}
            onClick={() => change(-25)}
          >
            <Minus size={19} />
          </button>
          <output>{Math.round(zoom)}%</output>
          <button
            aria-label="Zoom in"
            disabled={zoom === 300}
            onClick={() => change(25)}
          >
            <Plus size={19} />
          </button>
        </div>
        <div className="image-tools-center">
          <button disabled={!loaded || error} onClick={fitToPage}>
            <Maximize size={16} /> Fit to Page
          </button>
          <button
            onClick={() => {
              // Reset to the viewer-width baseline and return to the image origin.
              setZoom(100);
              viewport.current?.scrollTo(0, 0);
            }}
          >
            <Search size={16} /> Actual Size (100%)
          </button>
        </div>
        <div className="image-tools-right">
          <span className="preview-label">Preview Mode</span>
          <button
            aria-label="Fullscreen scan"
            onClick={() => {
              // Toggle fullscreen for the scan viewport.
              if (document.fullscreenElement) void document.exitFullscreen();
              else void viewport.current?.requestFullscreen();
            }}
          >
            <Maximize size={19} />
          </button>
        </div>
      </div>
    </div>
  );
}
