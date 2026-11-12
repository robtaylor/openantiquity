# Decision 0031 — A point's kind is switched by a control or a long press on its handle, and overlapping findings are picked by their edges

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of a drawing tool where each point is straight or curved, on a map where shapes overlap, facing a phone with no Shift key and taps that hit only a marker under the exact tap position, we chose a visible control and a long press on a point's handle to switch its kind, never pressure or a long press on the map, and chose to pick areas by their edges, let the more specific candidate win and open a chooser between equals, accepting slower mixing of kinds on a phone and a road that hides the edge of a field system it crosses.

## Context

When this was written the outline tool added straight corners only. A right click, or a long press where the browser fires `contextmenu`, opened "open elsewhere" for the spot. `docs/UI.md` required feedback within 100 ms. A tap opened a finding only when a marker was under its exact position, and no saved line or area was drawn.

On 2026-11-12 the owner said: "On computer it is fine to use shift+click, but on phones that could be a long click or increased pressure click." Both phone gestures were weighed. A long press on the map already meant "open elsewhere", would make every tap wait about half a second, and behaves differently on iOS Safari, which doesn't fire `contextmenu` for a long press on a canvas. A device without pressure reports 0.5 while pressed, so pressure can't be told from none. iPhones since the XR and 11 lack 3D Touch, and Android reports pressure inconsistently. The platform facts are inferences from platform knowledge and weren't checked here.

The owner then asked that marking be one flow: "you should just go straight to selecting a point, which you can then extend into a shape". Until then a tap placed the mark, a second tap moved it, and an outline was a separate optional step. Asked what a second tap should do, they chose that a tap always adds a point and a drag moves one, and added: "We should probably offer some guidance in the side panel".

The owner also asked: "how do users select when there are overlapping shapes?" They were offered picking by the edge, the more specific winning, a chooser for the rest, a hover hint on a computer, a wider reach for a finger and the Explore list for the keyboard, and replied: "that all sounds very sensible, lets record and go ahead with that". Fitting this to the code showed a gap: "the smaller of two alike wins" doesn't say when two are alike enough for the chooser.

## Decision

1. Marking is one flow. The first tap places a point, which alone is a finding at a spot. Further taps make it a line, and a tap on the first point closes it. A tap always adds a point, and a drag moves one. Placing a point under the cross stays as a button for the keyboard and for precision, not as the way marking begins.
2. The mark panel carries guidance in plain text that says what a tap will do now, and changes as the marking grows.
3. Every way of choosing a point's kind has a visible control in the drawing bar or the selected-point bar. On a computer Shift-click does the same.
4. On a phone a long press on a point's handle switches its kind. Handles sit above the map, so the gesture never reaches it. The tool uses neither a long press on the bare map nor pressure.
5. While drawing, double-tap and box zoom are off so they don't act on taps meant for the tool, and taps belong to the tool, not to other findings.
6. An area is picked by its edge, never its inside, so a point or record inside a large area stays reachable. A finger gets a wider reach than a mouse.
7. Markers beat lines and lines beat area edges. Among candidates of one kind, the smaller wins only when it is under half the other's length or extent. Otherwise the chooser opens.
8. The chooser lists the candidates and highlights each as its entry is hovered or focused. It's a popover on a computer and a sheet on a phone that never covers the spot tapped. On a computer the pointer shows what a click would open.
9. Findings still win over records, obscured squares behave as before, and the Explore list stays the keyboard route to every finding in view. The controls and reaches are in the plan's sections "The drawing tool" and "Picking one of overlapping shapes".

## Alternatives considered

- **A long press on the map adds the other kind** — rejected because it already opens "open elsewhere", differs on iOS Safari, and makes every tap wait past 100 ms.
- **A firmer press adds the other kind** — rejected because pressure can't be told from none on most phones.
- **Shift-click with no phone equivalent** — rejected because the owner asked for phones, and every gesture needs a control.
- **Picking an area anywhere inside it** — rejected because whatever lies inside would be out of reach.
- **"The smaller wins" with no threshold** — rejected because between two crossing roads a silent choice is a guess.
- **A chooser for every overlap** — not taken, because the owner chose that the clearly more specific wins.

## Consequences

- Mixing kinds on a phone takes a tap on the bar or a long press after placing, slower than Shift-click.
- People who zoom by double-tapping must pinch while drawing. That a double-tap would otherwise add two points is an inference still to be confirmed by a test.
- Stylus users don't get pressure, though their devices could report it.
- A road through a field system wins over the field system's edge, which stays reachable by its anchor marker (Decision 0028), by zooming in and by the Explore list.
- A finger and a mouse at the same spot can open different things.

## Walk-back options

- **If stylus users ask for pressure** — accept it for pens alone, where the value is reliable.
- **If a browser turns a long press on a handle into its own menu** — drop the gesture there and keep the controls.
- **If the chooser opens too often** — narrow the finger's reach or lower the threshold, and measure.
- **If people miss an area they tapped inside** — offer such areas in the hover hint and the chooser without letting them beat anything at their edge.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "The drawing tool" and "Picking one of overlapping shapes".
- `docs/UI.md` — the 100 ms rule, and the rule that a phone sheet never covers the place being looked at.
- Decision 0028 — the corner and smooth points, and the anchor marker every shape finding keeps.
