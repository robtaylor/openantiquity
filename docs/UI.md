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

## Words

British English. Short, plain and warm. Say "seen by others", not "consensus reached". Explain a term the first time it appears, in a hint, in one sentence. Never tell someone they've made a discovery. Say what the evidence shows.
