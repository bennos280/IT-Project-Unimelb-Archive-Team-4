import { useEffect, useRef, useState } from "react";
import { Plus, Minus, Maximize, Search } from "lucide-react";
import type { SurveyPage } from "./model";
import { pageNames as names } from "./model";
import { fieldLocations } from "./fieldLocations";

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
  const region = selectedField
    ? fieldLocations[page.type][selectedField.id]
    : undefined;
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
  const change = (delta: number) => {
    setZoom((z) => Math.max(1, Math.min(300, z + delta)));
  };
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
          if (e.key === "+" || e.key === "=") change(25);
          if (e.key === "-") change(-25);
        }}
        onPointerDown={(e) => {
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
            The source image could not be loaded. Check its URL in US8.
          </div>
        ) : (
          <div className="scan-stage" ref={stage} style={{ width: `${zoom}%` }}>
            <img
              ref={image}
              src={page.imageUrl}
              alt={`Original ${names[page.type]} for survey ${page.id}`}
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
