# Spike — Would terrain tiles drawn past zoom 16 show small features more clearly?

**Status:** Resolved (2026-11-13) — PARTIAL; a zoom 18 tile drawn from the elevation was visibly crisper than the enlarged zoom 16 tile for Composite and only slightly for Multi-direction shade, and neither showed anything the one-metre survey doesn't hold

## Question

Is a terrain tile drawn at zoom 18 from the elevation mirror clearer than the zoom 16 tile the browser enlarges today, by enough to be worth serving?

## Why this is in question

On 2026-11-13 the owner found small features hard to mark. The terrain styles stop at zoom 16 (`MAXZOOM` in `backend/src/fieldclub/terrain/styles.py`), where a pixel is about 0.7 m of ground. Closer in, the browser enlarges those tiles, and by zoom 18 the picture is a blur. The elevation is sampled with a cubic B-spline (`terrain/sources.py`), so a tile can be drawn at any zoom. Whether doing so shows more, or only a smoother blur, wasn't known.

## Approach

- **Q1.** Does a zoom 18 tile drawn from the elevation look clearer than the same ground cut from the zoom 16 tile and enlarged four times?
  - Step 1: With the local mirror, draw one zoom 16 tile and the zoom 18 tile inside it at Avebury, for Multi-direction shade and for Composite, through `TileRenderer.render_window`, which doesn't check the zoom.
  - Step 2: Set the two side by side and look.
- **Q2.** What does a zoom 18 tile cost to draw?
  - Step 1: Time each call on the same machine.

## Decision matrix

| Outcome | Means | Action |
|---|---|---|
| No clearer | The blur is the survey's, not the enlarging's | Leave `MAXZOOM` at 16 |
| Clearer for some styles | A gain where the style works on a neighbourhood | Consider zooms 17 and 18 after timing on the live machines |
| Clearer for all | The enlarging was the limit | Plan zooms 17 and 18 |

## Findings

- 2026-11-13: Composite at zoom 18 was visibly crisper than the enlarged zoom 16: finer texture, sharper edges to banks and hollows, and small pits better defined. Its sky-view and openness are worked out afresh on the finer grid.
- 2026-11-13: Multi-direction shade at zoom 18 was only slightly crisper. It is a function of slope alone, and the slope of a smoothly interpolated surface is close to the enlarged picture of the slope.
- 2026-11-13: Neither showed a feature the zoom 16 tile lacked. The survey is one-metre data, so something five metres across is five cells across however it is drawn.
- 2026-11-13: On the development machine one tile took 0.03 s for Multi-direction shade at zoom 18 against 0.13 s at zoom 16, and 0.45 s for Composite at zoom 18 against 0.12 s at zoom 16. Composite's buffer is a distance on the ground, so it is more pixels at a closer zoom. The live machines are slower and weren't timed.
- 2026-11-13: A view at zoom 18 covers a sixteenth of the ground of one at zoom 16, so the same number of tiles is drawn for a screen, each new to the cache.

## Outcome

Drawing terrain past zoom 16 gives a modest gain for the styles that work on a neighbourhood and little for the default view, and it can't show what the survey doesn't hold. The owner's difficulty was the map's own zoom limit, which was raised from 20 to 22 the same day. Zooms 17 and 18 stay a possible later step for Composite, to be timed on the live machines first.
