import { Sun } from "lucide-react";
import { type CSSProperties, useEffect, useRef, useState } from "react";
import type { DemLayer, Meta, View } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { clamp } from "../../ui/math.js";
import { hillshade, terrariumHeights } from "./hillshade.js";
import { fillTileTemplate, tileAt } from "./tiles.js";
import "./layers.css";

/**
 * Previews show the catalogue's opening view, so every layer is seen on the
 * same patch of ground: at Avebury, the henge and the village round it.
 */
export const PREVIEW_ZOOM = 14;
/** The preview shows the middle of a tile at twice its size, so this much of the tile is seen across. */
const PREVIEW_SCALE = 2;

/** The tile behind a preview, and where the spot falls in it. */
function previewTile(meta: Meta, minzoom: number, maxzoom: number) {
  const [lng, lat] = meta.layers.initial_view.center;
  return tileAt(lng, lat, Math.round(clamp(PREVIEW_ZOOM, minzoom, maxzoom)));
}

/** Offsets that put the spot in the middle of the box without showing past the tile's edge. */
function framing(fx: number, fy: number): CSSProperties {
  const offset = (fraction: number) => `${clamp(50 - fraction * PREVIEW_SCALE * 100, (1 - PREVIEW_SCALE) * 100, 0)}%`;
  return { width: `${PREVIEW_SCALE * 100}%`, height: `${PREVIEW_SCALE * 100}%`, left: offset(fx), top: offset(fy) };
}

function RasterPreview({ meta, view }: { meta: Meta; view: Extract<View, { type: "raster" }> }) {
  const [failed, setFailed] = useState(false);
  const template = view.tiles[0];
  if (!template || failed) return <span className="fc-view-preview fc-view-preview--empty" aria-hidden="true" />;
  const tile = previewTile(meta, view.minzoom, view.maxzoom);
  return (
    <span className="fc-view-preview" aria-hidden="true">
      <img
        src={fillTileTemplate(template, tile)}
        alt=""
        loading="lazy"
        decoding="async"
        draggable={false}
        style={framing(tile.fx, tile.fy)}
        onError={() => setFailed(true)}
      />
    </span>
  );
}

/** Pixels of elevation read for the raking preview, square. Drawn at 1:1, so the encoding isn't blurred. */
const RAKING_PIXELS = 128;

interface Heights {
  values: Float32Array;
  cellSize: number;
}

/** Heights around the preview spot, from the elevation tiles, or null if they can't be read. */
function useHeights(meta: Meta, dem: DemLayer): Heights | null | "loading" {
  const [heights, setHeights] = useState<Heights | null | "loading">("loading");
  const template = dem.tiles[0];
  const tile = previewTile(meta, dem.minzoom, dem.maxzoom);
  const url = template ? fillTileTemplate(template, tile) : null;
  const { fx, fy, z } = tile;
  const lat = meta.layers.initial_view.center[1];

  useEffect(() => {
    if (url === null) {
      setHeights(null);
      return;
    }
    let cancelled = false;
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.decoding = "async";
    image.onload = () => {
      if (cancelled) return;
      try {
        const size = image.naturalWidth;
        const canvas = document.createElement("canvas");
        canvas.width = RAKING_PIXELS;
        canvas.height = RAKING_PIXELS;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) throw new Error("No 2D canvas");
        context.imageSmoothingEnabled = false;
        const sx = clamp(Math.round(fx * size - RAKING_PIXELS / 2), 0, size - RAKING_PIXELS);
        const sy = clamp(Math.round(fy * size - RAKING_PIXELS / 2), 0, size - RAKING_PIXELS);
        context.drawImage(image, sx, sy, RAKING_PIXELS, RAKING_PIXELS, 0, 0, RAKING_PIXELS, RAKING_PIXELS);
        const pixels = context.getImageData(0, 0, RAKING_PIXELS, RAKING_PIXELS).data;
        const cellSize = (40075016.686 * Math.cos((lat * Math.PI) / 180)) / (2 ** z * size);
        setHeights({ values: terrariumHeights(pixels, RAKING_PIXELS, RAKING_PIXELS), cellSize });
      } catch {
        // A tile from another site without CORS can't be read back. The preview stays plain.
        setHeights(null);
      }
    };
    image.onerror = () => {
      if (!cancelled) setHeights(null);
    };
    image.src = url;
    return () => {
      cancelled = true;
    };
  }, [url, fx, fy, z, lat]);
  return heights;
}

function RakingPreview({ meta }: { meta: Meta }) {
  const heights = useHeights(meta, meta.layers.dem);
  const sun = useMapStore((state) => state.sun);
  const exaggeration = useMapStore((state) => state.hillshadeExaggeration);
  const canvas = useRef<HTMLCanvasElement>(null);
  const ready = heights !== null && heights !== "loading";

  useEffect(() => {
    const target = canvas.current;
    const context = target?.getContext("2d");
    if (!ready || !context) return;
    const grey = hillshade(heights.values, RAKING_PIXELS, RAKING_PIXELS, heights.cellSize, { ...sun, exaggeration });
    const image = context.createImageData(RAKING_PIXELS, RAKING_PIXELS);
    grey.forEach((value, i) => {
      image.data.set([value, value, value, 255], i * 4);
    });
    context.putImageData(image, 0, 0);
  }, [ready, heights, sun, exaggeration]);

  return (
    <span className="fc-view-preview fc-view-preview--raking" aria-hidden="true">
      {ready ? (
        <canvas ref={canvas} width={RAKING_PIXELS} height={RAKING_PIXELS} />
      ) : (
        <Sun size={22} className="fc-view-preview__icon" />
      )}
    </span>
  );
}

/** A small picture of what a view looks like, for the layer panel. Decorative: the title and description say it in words. */
export function ViewPreview({ meta, view }: { meta: Meta; view: View }) {
  return view.type === "raking" ? <RakingPreview meta={meta} /> : <RasterPreview meta={meta} view={view} />;
}
