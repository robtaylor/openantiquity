# Interface rules

The map is the product. Everything else is a thin layer of controls over it. This file fixes the visual language so separate pieces of the frontend look like one thing.

## Layout

The map fills the window at all times. Controls sit on top of it in fixed regions.

| Region | Desktop | Phone (under 720 px) |
|--------|---------|----------------------|
| Mode rail | 56 px column on the left: Explore, Second look, Scan a square, Help wanted, Investigations, Activity, Account | Bottom tab bar, five items, the rest under "More" |
| Search | Top left, beside the rail, 360 px | Full width at the top |
| Panel | Right side, 400 px, scrolls on its own | Bottom sheet with three stops: peek, half, full |
| Layer button | Top right, opens the layer panel | Same |
| Status bar | Bottom edge: grid reference, coordinates, height, zoom, attribution | Grid reference and attribution only |
| Primary action | "Mark a finding", bottom centre, always reachable | Same, above the tab bar |

Only one panel is open at a time. Opening a finding replaces the layer panel. Closing a panel returns to the bare map, except for the layer panel. Closing the layer panel returns to the mode it was opened over, so changing layer during a second look or a scan doesn't end it. The URL always describes what's open, so back and forward work.

## Look

Dark chrome, because greyscale terrain reads best against it and a bright frame washes out faint features. One warm accent, taken from Ordnance Survey antiquity lettering and field notebooks.

```css
:root {
  --bg: #14161a;            /* window and map backdrop */
  --surface: #1d2026;       /* panels */
  --raised: #262a31;        /* cards, inputs */
  --border: #343942;
  --text: #eceae4;
  --text-muted: #a3a39b;
  --accent: #e0a43a;        /* ochre: primary actions, selection */
  --accent-strong: #f2b94f;
  --on-accent: #1a1405;
  --good: #7fb069;
  --warn: #e07a3a;
  --bad: #d9544d;
  --info: #6ba6c9;

  --tier-spotted: #9aa3ad;
  --tier-seen: #6ba6c9;
  --tier-corroborated: #9a8fe0;
  --tier-probable: #e0a43a;
  --tier-ground-checked: #7fb069;
  --tier-confirmed: #f5d76e;
  --state-known: #b9b2a3;
  --state-disputed: #e07a3a;
  --state-ruled-out: #6b6f76;

  --radius: 10px;
  --radius-sm: 6px;
  --shadow: 0 8px 28px rgb(0 0 0 / 0.45);
  --font-ui: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-display: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  --font-mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
```

Headings and finding titles use the display serif. Controls and body text use the UI sans at 15 px. Grid references, coordinates and heights use the mono face. No web fonts are loaded.

Panels are opaque. Controls floating directly on the map use `--surface` at 92% opacity with a 1 px border, so terrain doesn't show through text.

## Markers

Findings are circles coloured by tier, with a dark 1.5 px outline so they hold up against any layer. Size grows slightly with tier. Known findings are hollow rings. Ruled-out findings are small hollow grey rings and are hidden by default. A finding the viewer may not see exactly arrives with `obscured` set and is drawn as a dashed one-kilometre square in its tier colour, never a point. Records are small squares coloured by category, clearly different in shape from findings, with the same dark outline. Several category colours are close in lightness to mid-grey terrain, so the outline, not the fill, is what separates a square from a grey LIDAR view. A category swatch in a panel sits beside its label and carries a 1 px `--text-muted` outline, because some colours fall below 3:1 against `--surface` and `--raised`.

A finding drawn as a line or an area keeps its tier marker at its anchor, and its shape is drawn under the markers in the tier colour on the same dark casing, 1.5 px on each side. A line is 2.5 px wide with round joins and caps. An area is its edge, 2 px wide, over a fill at 4% opacity so the terrain inside stays readable. A known finding's line or edge is thinner, 1.5 px and 1.25 px. A ruled-out finding's shape is a 1.5 px line in `--state-ruled-out`, behind the ruled-out switch like its marker. An obscured finding is still its dashed square, never a line.

Colour never carries meaning alone. Tier is also shown as a label in every list and panel.

## Components

Build these once in `src/ui/` and reuse them: `Button` (primary, secondary, ghost, danger), `IconButton`, `Chip` and `ChipGroup` (single and multiple choice), `Panel` and `Sheet`, `Tabs`, `Field` with label and hint, `Slider`, `Meter` (the confidence meter with tier ticks), `TierBadge`, `Avatar`, `Toast`, `Dialog`, `EmptyState`, `Skeleton`. Icons come from `lucide-react`. Feature classes have their own small plan-view pictograms in `src/ui/featureIcons.tsx`.

## Behaviour

- Every action gives feedback within 100 ms. Saves are optimistic and roll back with a toast on failure.
- Transitions run 150 to 200 ms. A tier change animates the meter and swaps the badge. `prefers-reduced-motion` turns all of it off.
- Nothing that contributes data needs more than one tap after the first. Second look answers are single buttons, and the answer is sent with that one press. Optional detail appears after the answer, never before, and goes with the press that shows how the answer compares (Decision 0008). On a phone the sheet never covers the place the person is asked to look at while they answer.
- Signed-out people can mark, answer and scan. Their work is a draft in the browser, shown with a "not saved yet" badge, and a quiet bar says how many drafts are waiting. Pressing save opens the sign-in sheet over what they were doing. After a sign-in from the same tab the drafts wait, without being re-entered, for one press to send them, since someone else may have used the tab first, and the page returns to the same view (Decision 0024). Drafts made in another tab or by an earlier visitor are shown by kind alone and saved only when the person says they're theirs (Decision 0022).
- The sign-in sheet shows one button per provider in the provider's own style, with "email me a link" underneath. It says in one sentence why an account is needed.
- Empty states say what to do next. Errors say what happened and offer a retry.
- Every control is reachable by keyboard and has a visible focus ring. Map features are also listed in the panel, so nothing depends on pointing at a canvas. Text contrast is at least 4.5 to 1.

## The drawing tool

One tool marks a finding, whether it is a spot, a line or a closed shape, and changes a saved one ("Change the shape"). It works the same by pointer, by touch and by keyboard, and every gesture has a visible control that does the same (Decision 0031).

- **Taps.** "Mark a finding" opens the tool with nothing placed. Each tap or click adds a point at the active end, of the kind chosen in the bar, and a tap on the far end of three points or more closes the shape. A tap never moves a point: a drag on its handle does. On a computer, Shift-click adds the other kind of point, Shift-click on a handle switches its kind, and Alt-click on the line inserts a point there. While the tool is open, double-click and double-tap zoom and Shift-drag box zoom are off, and findings already on the map don't take taps.
- **Handles.** Each point has a handle: a 12 px dot in a 44 px target, square for a straight point and round for a curved one, larger and filled when selected. A long press on a handle by a finger or a pen, 500 ms without moving 8 px, switches its kind, with a short vibration where the device has one. A mouse never long-presses. A drag starts once a finger or a pen has moved 8 px, or a mouse 3 px. Handles take no text selection, no callout and no context menu. The path is one tab stop with a roving tabindex. On a handle the arrow keys move the point 3 px, or 24 px with Shift, `[` and `]` step to the previous and next point, and Delete removes it. Handles are drawn only for points in view and only while 150 or fewer are. Past that the ends and the selected point keep theirs, and the status line says "Zoom in to change points".
- **The drawing bar**, in the panel: Undo, Redo, "Add a point at the cross" (the keyboard's and the switch user's way to add a point), "Next point: Straight | Curved", "Close the shape" and Finish, with a status line (`role="status"`) such as "3 points, 254 m. Click the map to add the next one at the north-east end." Undo and Redo go back through 100 states. While the first point is the only one, it takes the kind chosen for the next, and its handle changes with it: it was placed before its finder could choose, and a ring drawn with curved points then closes smoothly on it.
- **The selected-point bar**, when a handle is selected: its name ("Point 2 of 4, curved, SU 1234 5678"), "Make it straight" or "Make it curved", "Delete point", "Insert a point after", "Continue from this end" on either end of an open path, which moves the map to it, "Previous point", "Next point" and Done.
- **The phone's bar.** While points are being added on a phone, the sheet rests at its peek stop and a floating bar takes the primary action's place above it: one row of 44 px icon buttons and one line of status, so the map above stays free to tap. A selected point gets its own bar the same way. When either bar appears or grows, the map moves up just enough that no point already placed is under it. Once drawing stops, the sheet rises and the full bars are in it.
- **Guidance.** A plain-text block at the top of the panel, "How to mark it", says what a tap does now and what else is possible, and changes as the marking grows from nothing to a spot, a line and a closed shape. Its second line names the gestures of the device in hand, or the keys once the map or a handle has keyboard focus.
- **The preview.** Up to 200 points the path is drawn in SVG over the map, and past that as a map layer.
- **Leaving.** Nothing is kept until it is saved, or kept as a draft. Until then, closing or reloading the page with a line or a shape of two points or more brings up the browser's own "leave this page?".
- **Changing a saved shape.** The tool opens with the saved path framed clear of the search box, the map's buttons, the panel or the sheet, and the bars. Where others have given second looks, that ground is drawn as a faint wide line under the path, and a refusal of the change is shown beside the path.

## Choosing between findings

A tap where several findings meet opens the one that is clearly most specific: markers beat lines, lines beat area edges, and the smaller of two alike wins only when it is under half the other's size. An area is picked by its edge, never its inside. A finger reaches 16 px from the tap and a mouse 6 px. Anything else opens the chooser, which says "2 findings here" and lists each with its title, tier badge and class, at most 8 and then "Show all in Explore". On a computer it is a popover beside the pointer, and on a phone a short sheet at the top or the bottom, whichever leaves the tap in sight. Hovering or focusing an entry highlights its shape on the map. The arrow keys, Home and End move through it, Enter opens one, and Escape closes it and puts focus back on the map. On a computer the pointer highlights what a click would open, or says "2 findings here" where it would open the chooser. Explore's list is the keyboard route to every finding in view.

## Words

British English. Short, plain and warm. Say "seen by others", not "consensus reached". Explain a term the first time it appears, in a hint, in one sentence. Never tell someone they've made a discovery. Say what the evidence shows.
