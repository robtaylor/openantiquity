# Decision 0034 — On a phone a point's kind is switched by a control or a long press on the point, not by pressure

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of a drawing tool where each point is straight or curved, and where Shift-click switches the kind on a computer, facing a phone that has no Shift key, we chose a visible control for the kind and a long press on a point's handle, and turned down pressure and a long press on the bare map, to keep every tap's feedback immediate and the map's own gestures intact, accepting that mixing kinds on a phone takes a tap on the bar or a press after the point is placed.

## Context

When this was written the outline tool added straight corners only. A right click, or a long press where the browser fires `contextmenu`, opened "open elsewhere" for the spot (`useRecordsOnMap.ts`). "Add a corner at the cross" added a point at the map's centre for keyboard and precise phone use. `docs/UI.md` required every action to give feedback within 100 ms.

On 2026-11-12 the owner said: "On computer it is fine to use shift+click, but on phones that could be a long click or increased pressure click."

Each of the two phone gestures was weighed against the platforms. Three of the facts below come from platform knowledge and weren't checked in this repository: that iOS Safari doesn't fire `contextmenu` for a long press on a canvas, which iPhones lack 3D Touch, and how Android devices report pressure.

- **A long press on the bare map** already opened "open elsewhere" where the browser fires `contextmenu`. iOS Safari doesn't fire it for a long press on a canvas and shows its own callouts elsewhere, so the gesture would behave differently by platform. It would also make every tap wait about half a second before the tool knew which kind of point to add.
- **Pressure.** The Pointer Events standard has a device without pressure report 0.5 while a button is down, so a pressure value can't be told apart from "no pressure". iPhones since the XR and 11 have no 3D Touch hardware, and Android devices report pressure inconsistently. Only a stylus such as the Apple Pencil gives a reliable value.

## Decision

1. Every way of choosing a point's kind has a visible control. The drawing bar's "Next point: Straight | Curved" sets the kind a tap adds and stays as set. The selected-point bar's "Make it straight" or "Make it curved" switches a point already placed.
2. On a computer, Shift-click on the map adds the other kind, and Shift-click on a point's handle switches it.
3. On a phone, a long press on a point's handle switches its kind. After 500 ms without moving more than 8 px, the kind switches and the dot changes shape at once, a square for a corner and a circle for a curve. A short vibration confirms it where `navigator.vibrate` exists. Handles are DOM buttons above the map canvas, so the gesture never reaches the map.
4. Handles carry `touch-action: none`, `user-select: none` and `-webkit-touch-callout: none`, and refuse `contextmenu`, so no browser menu or text selection appears.
5. A long press on the bare map isn't used by the drawing tool.
6. Pressure isn't used.
7. While drawing, double-tap and double-click zoom and Shift-drag box zoom are turned off, since both would otherwise act on taps meant for the tool. One finger still drags the map and two fingers pinch and rotate.

## Alternatives considered

- **A long press on the map adds the other kind** — rejected because the map's long press already opens "open elsewhere", because a wait on every tap breaks the 100 ms rule in `docs/UI.md`, and because iOS Safari would behave differently from other browsers.
- **A firmer press adds the other kind** — rejected because a pressure value can't be told apart from no pressure, and most phones in use can't report it reliably.
- **Shift-click alone, with no phone equivalent** — rejected because the owner asked for the tool to work on phones, and every gesture needs a control that does the same.

## Consequences

- Every tap gives its point at once, and the map's long press keeps its meaning.
- Nobody needs to know a gesture. The bar's controls do everything the gestures do.
- Mixing straight and curved points on a phone takes a tap on the bar between points, or a long press on a handle after the point is placed. That is slower than Shift-click on a computer.
- People who zoom by double-tapping have to pinch while drawing. That a double-tap would otherwise add two points before zooming is an inference still to be confirmed by a test.
- Stylus users don't get pressure, though their devices could report it.

## Walk-back options

- **If stylus users ask for pressure** — accept it for `pointerType` `pen` alone, where the value is reliable, and keep the controls for everyone else.
- **If a browser turns a long press on a handle into its own menu** — the bar's controls already cover it. Drop the gesture on that browser rather than the controls.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "The drawing tool" and "Phone gestures".
- `docs/UI.md` — the 100 ms feedback rule.
- Decision 0028 — the corner and smooth points a path is made of.
