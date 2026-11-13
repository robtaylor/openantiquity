# Decision 0034 — The drawing guidance is a list on the map, and a line is bent by dots on it, not by curve handles

**Status:** Proposed.

**Current architecture:** [UI.md, "The drawing tool"](../../UI.md#the-drawing-tool).

**TL;DR.** In the context of a drawing tool that had just gone live, facing an owner who drew a ring and couldn't find how to switch a point's kind though the panel said so, and who asked to see and adjust curve handles, we chose to put the tool's guidance on the map as a list with icons in the search box's place and to bend a line by dragging a dot on it, so that the gestures can be found without reading prose and a curve can be adjusted without a second kind of curve, accepting that search is one press further away while drawing and that a curve is shaped only by its points.

## Context

When this was written the tool's guidance was a block of plain text at the top of the mark panel (Decision 0031, point 2): two sentences that changed with the marking's state and one line for the device in hand. On a phone the sheet that held it rested at its peek stop while points were added, so the guidance was out of sight then, and nothing else said that a long press switches a point's kind.

The tool went live on 2026-11-13. That day the owner drew a round enclosure with curved points and got a corner where it closed, because the first point had been placed before "Curved" was chosen. A point's kind could be switched, and he hadn't found how. He wrote: "I think we could do with some instructions to aid discoverability for click/press interactions", and then: "maybe when you're editing we could hide the search bar, and overlay instructions there", and "a scannable list ideally with icons would be good".

In the same message he asked: "I think it would also be able to see and adjust the curve handles, what do you think?" The curve was `catmull-rom-centripetal-1` (Decision 0028). It passes through every tapped point, and a curved point takes its bend from its two neighbours, so there were no handles to show. A curve was adjusted by inserting a point where it strayed and dragging it, and inserting needed Alt-click on the line or "Insert a point after" in the selected-point bar. Offered dots on the line in place of handles, he replied: "oh, that is a nice idea re handles. agreeed."

## Decision

1. While the drawing tool is open, the search box isn't shown and a card, "How to draw", sits in its place, on a computer and on a phone. It lists the gestures that apply to the marking as it stands and to the device in hand, each as an icon, the gesture and what it does. The mark panel carries no guidance block. This replaces point 2 of Decision 0031.
2. The card's header has a button that swaps the card for the search box, which gives way to the card again when the search is over, and a button that folds the card down to its header. The browser remembers the fold.
3. Whatever frames a shape counts the card as it counted the search box. The card itself never moves the map.
4. A segment long enough on screen has a dot half way along it, on the curve as drawn. Dragging the dot inserts a point there and moves it, as one step for undo. A tap or click on it inserts the point and selects it. The dots are a pointer's shortcut and not tab stops: "Insert a point after" stays the keyboard's way, as Decision 0031's third point requires of every gesture.
5. The tool has no curve handles. The stored path and the curve are as they were.

## Alternatives considered

- **Rewriting the panel's prose as a list, still in the panel** — rejected because on a phone the panel is out of sight while points are added, which is when the gestures are needed.
- **Bézier handles on each curved point** — rejected because they need a second curve definition for the server and the browser to agree on, two more stored positions for each point and limits against loops, because each curved point would gain two more small targets on a phone, and because "the line goes through your points" needs no explaining where handles do.
- **Hints at the pointer on a computer, as tooltips and a cursor for Alt** — not built. They help only a mouse, and the card serves every device.

## Consequences

- The gestures are in sight on a phone while points are added.
- Search is one press further away while the tool is open.
- The card covers part of the map until it is folded, most of all on a phone.
- A curve is adjusted by adding points, so a path that follows a feature closely holds more points than one drawn with handles would.
- Inserting a point needs neither a modifier key nor a selected point.
- The other points of Decision 0031 stand.

## Walk-back options

- **If the card gets in the way of drawing** — start it folded, or fold it once the first line is finished.
- **If people miss the search box while drawing** — keep the search box and put the card below it.
- **If tracing real features needs finer curves than points give** — add a second named curve with handles beside the first. The stored path names its curve (Decision 0028), so paths drawn before keep theirs.

## Links

- [UI.md, "The drawing tool"](../../UI.md#the-drawing-tool) — the card's rows and the dots' sizes.
- Decision 0031 — marking is one flow, and how a point's kind is switched. This record replaces its second point.
- Decision 0028 — the path and its one fixed curve.
