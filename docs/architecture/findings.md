# Findings

*Reference: the current design as it stands in the code. The why lives in the decision records linked from each section; the not-yet-built work is under [Implementation status](#implementation-status). Present tense means "true today". If a claim here is stale, the code moved and this doc didn't.*

A finding is something a member has marked on the map as a possible earthwork: a place, a feature class, a level of protection and a step on the confidence ladder. This doc covers where a finding is and what shape it has. The rest of findings, from the ladder to evidence and discussion, is still described in [the build contract](../ARCHITECTURE.md) ("Findings", "Location sensitivity", "Second looks"). A finding is `open` or `protected` ([Decision 0032](decisions/0032-findings-are-open-or-protected-and-the-restricted-level-is-dropped.md)).

## Shapes

A finding is a spot, a line or a closed shape. A spot is its anchor point alone. A line or a shape is a path of tapped points, and the server draws the stored geometry from the path with one named curve ([Decision 0028](decisions/0028-a-finding-s-shape-is-its-tapped-points-under-one-fixed-curve-within-size-caps-around-an-anchor-that-stays-put.md)). The backend's code is `services/shapes.py` (the path, the curve, the limits, the anchor), `services/shape_edits.py` (applying a change, and the map's shapes) and `services/looked_at.py` (what second looks were given on). The frontend's is `src/features/mark/`.

### The path

A path is JSON:

```json
{
  "closed": false,
  "curve": "catmull-rom-centripetal-1",
  "points": [
    {"lon": -1.234567, "lat": 51.234567, "kind": "corner"},
    {"lon": -1.23, "lat": 51.24, "kind": "smooth"}
  ]
}
```

- `kind` is `corner`, which the interface calls straight, or `smooth`, which it calls curved.
- An open path has 2 points or more and a closed one 3 or more. A closed path doesn't repeat its first point.
- A request may leave `curve` out, and the server writes it. Any other name is 422 `unknown_curve`.
- Two neighbouring points, and for a closed path the last and the first, must be at least `1e-6` degrees apart in the curve's projected plane, or the request is 422 `points_too_close`.
- Tapped points are stored as sent, rounded to 7 decimal places.

An outline saved before paths existed is read as an all-corner path when it is one `LineString` or one `Polygon` without holes (`shapes.path_from_outline`). An outline of several parts, or with holes, has no path. It is served with `path: null`, and both the drawing tool and the finder's part of the finding page say it can be replaced but not changed point by point.

### The curve, `catmull-rom-centripetal-1`

The server's geometry is the stored truth. The browser's preview (`src/features/mark/curve.ts`) follows the same definition. Both suites check their output against the shared vectors in [`curve-vectors.json`](curve-vectors.json) to 1e-7 degrees (`backend/tests/services/test_shapes.py`, `frontend/src/features/mark/curve.test.ts`).

1. **Segments.** An open path of `n` points has segments `P[i] → P[i+1]` for `i = 0 … n−2`. A closed path also has `P[n−1] → P[0]`, and its indices wrap.
2. **Straight segments.** A segment whose ends are both corners emits its end point alone.
3. **Neighbours.** Otherwise call the ends `A` and `B`. `prev` is the point before `A` when `A` is smooth and that point exists, and `next` the point after `B` when `B` is smooth and it exists. A corner end, or an open path's end, gets a phantom made in the projected plane: `prev' = 2A' − B'` or `next' = 2B' − A'`.
4. **Projection.** Each segment has its own scale `k = cos(radians((A.lat + B.lat) / 2))`. A point maps to `(lon · k, lat)` and back by `lon = x / k`. Only a segment's own ends set `k`, so extending a path changes no segment more than one away from the new point.
5. **Knots.** `t0 = 0`, `t1 = t0 + d(prev', A')^0.5`, `t2 = t1 + d(A', B')^0.5`, `t3 = t2 + d(B', next')^0.5`, where `d` is the Euclidean distance in the projected plane.
6. **Samples.** With `L = d(A', B')`, a segment has `N = min(16, max(2, ceil(L / 0.0003)))` steps, about one every 33 m. It emits the curve at `t1 + (t2 − t1) · j / N` for `j = 1 … N−1`, then `B` itself.
7. **Evaluation**, the Barry–Goldman form, with `P0 … P3 = prev', A', B', next'`:
   - `A1 = ((t1 − t)·P0 + (t − t0)·P1) / (t1 − t0)`, `A2 = ((t2 − t)·P1 + (t − t1)·P2) / (t2 − t1)`, `A3 = ((t3 − t)·P2 + (t − t2)·P3) / (t3 − t2)`
   - `B1 = ((t2 − t)·A1 + (t − t0)·A2) / (t2 − t0)`, `B2 = ((t3 − t)·A2 + (t − t1)·A3) / (t3 − t1)`
   - `C = ((t2 − t)·B1 + (t − t1)·B2) / (t2 − t1)`
8. **Output.** The geometry starts at `P[0]` and appends each segment's points in order. An open path is a `LineString`. A closed one ends back on `P[0]` and is a one-ring `Polygon`. Every coordinate is rounded to 7 decimal places.

### Limits

The limits are constants in `services/shapes.py` and `services/looked_at.py`. `GET /meta` serves them as `shapes`. The frontend reads them there and checks a path before it is sent (`pathProblem` in `src/features/mark/path.ts`).

| Limit | Value | Constant | Refused with |
|-------|-------|----------|--------------|
| Points in a path | 5,000 | `PATH_MAX_POINTS` | 422 `path_too_many_points` |
| Vertices in the derived shape, counted before it is drawn | 50,000 | `SHAPE_MAX_VERTICES` | 422 `shape_too_complex` |
| A closed shape across: the larger of its east–west width at its middle latitude and its north–south height | 25 km | `SHAPE_MAX_ACROSS_M` | 422 `shape_too_big` |
| A line's geodesic length | 600 km | `LINE_MAX_LENGTH_M` | 422 `line_too_long` |
| A shape's distance from an anchor the finder placed | 1,000 m | `SHAPE_MAX_GAP_M` | 422 `outline_too_far` |
| A closed shape's ring crossing itself | none allowed | | 422 `shape_crosses_itself` |
| Every point in the British Isles | | | 422 `outside_british_isles` |

A line has no limit across. The schema's general cap on client shapes, 2,000 positions and 200 parts (`geometry_too_complex`), applies to an `outline` sent in place of a path.

At the API, the request model parses every point of a path before `shapes.read_path` counts them. What bounds that work is the 1 MB limit on a request body (`security.BODY_MAX_BYTES`), which is refused with 413 `request_too_large` before it is read.

### The anchor

Every finding keeps one point, its anchor, in `findings.location`. Everything that places a finding by one point uses it: `location_public`, `grid_ref`, `nation`, the suggested title, the activity square, the obscured square, search and the suggested records.

- **One point.** The interface sends one point as `location` with no `path`, and the anchor is that point.
- **A path and no point.** The interface sends two points or more as a `path` with no `location`, and the server places the anchor (`shapes.derived_anchor`). For a line it is the point half way along, measured on the ellipsoid. For an area it is the centroid when that lies inside, and `point_on_surface` otherwise. `location_derived` is set.
- **A path and a point.** The API still takes both, and the shape must come within 1,000 m of the point (`outline_too_far`).
- **When the shape changes.** An anchor the finder placed never moves by itself: the new shape must come within 1,000 m of it. A derived anchor stays where it is while the new shape passes within 25 m of it (`ANCHOR_KEEP_M`), so extending a line at its ends leaves it alone. Otherwise it moves to the point of the new shape nearest where it was. Removing the shape leaves the anchor where it is. When the anchor moves, `grid_ref`, `nation`, `location_public` and the activity rows follow.

### What is stored

On `findings` (`models/findings.py`):

| Column | Holds |
|--------|-------|
| `path` jsonb | The path. Null for a spot, and for an old outline until it is next saved |
| `outline` Geometry, GIST index, and a second over shaped findings alone (`shape_kind` not null), which the map's box query uses | The derived shape |
| `outline_mid` Geometry | `outline` simplified at 0.00005° (about 3 to 5 m), for map zooms 13 to 15 and the finding page |
| `outline_low` Geometry, GIST index | `outline` simplified at 0.0005° (about 35 to 55 m), for map zooms 9 to 12 |
| `shape_kind` text | `line` or `area`, null without a shape |
| `shape_length_m` real | A line's geodesic length, or an area's perimeter |
| `shape_revision` int | 0 for a finding as made, raised by one on every change to the shape |
| `location_derived` bool | True when the server chose the anchor |
| `looked_at` Geometry | The ground second looks were given on |
| `added_since_looked_m` real | How much of the shape lies further than 250 m from `looked_at` |
| `added_view` jsonb | A centre and zoom framing that part |

`observations.shape_revision` holds the finding's `shape_revision` when the answer was given. Each change to the shape writes a `finding_shape_changes` row: `finding_id`, `user_id` (who made the change), `revision`, `kind` (`drawn`, `extended`, `reshaped`, `closed`, `opened` or `removed`), `points_before`, `points_after`, `length_before_m`, `length_after_m`, `added_length_m` and `added_view` for an extension, `path_before`, and `created_at`. It is unique on finding and revision. A finding made with its shape has no row until the shape first changes.

A new database gets these from `create_all`. An existing one gets them from `models/extras.sql`, which adds each set of columns only when it is missing and builds the two GIST indexes with `IF NOT EXISTS`. `python -m fieldclub.services.shapes backfill` fills the simplified copies, the kind and the length of outlines saved before paths, and seeds `looked_at` for findings answered before it existed. A second run changes nothing.

### Changing a shape

Only the finder changes, extends or removes a shape. `PATCH /findings/{public_id}` checks `findings.check_finder` and answers anyone else 403 `not_finder` ([Decision 0029](decisions/0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md)). The interface offers "Change the shape" on the finding page to whoever the server's `actions.edit` allows, and opens the drawing tool at `/mark/finding/:publicId` with the saved path (`ChangeShapePanel.tsx`).

- `path` replaces the whole path, and `path: null` removes the shape. Either needs `path_revision`, equal to the finding's `shape_revision`. Missing is 422 `path_revision_required`, and different is 409 `shape_changed`, after which the interface shows the finding as it now is and says it was changed elsewhere.
- The interface sends the revision the change began on. When the finding is fetched again with a newer shape while it is open, the tool takes the newer shape up if nothing has been changed there. Otherwise it keeps the change and its undo, turns Save off, says the shape was changed elsewhere, and offers to show it as it now is.
- A path deleted down to one point is sent as `path: null` with that point as `location`, and the finding becomes a spot there. An old shape the tool can't read as a path, of several parts or with holes, opens as the finding's point, and the interface sends nothing for it until a new shape of two points or more is drawn, so Save never removes it.
- `outline` is still read, as an all-corner path. Any other geometry is 422 `outline_not_a_path`, and `outline` with `path` is 422 `outline_and_path`.
- `services/shape_edits.change_shape` holds the new shape to the limits and the British Isles, places the anchor, checks the ground looked at, writes the change row and raises the revision, all under the finding's row lock.
- The change is classed for the timeline (`shapes.classify_change`). It is `extended` when the old open path appears whole and in order inside a longer new open path. Otherwise it is `drawn` (no shape before), `removed`, `closed`, `opened` or `reshaped`.
- An extension, or a reshape of an open line that leaves it an open line at least 200 m longer, records the activity kind `shape_extended`, which tells the finding's followers. A closed shape never records it. The length before an old outline's first change is measured from its geometry when the backfill hasn't stored it (`shape_edits.stored_length`). The feed lists it only to someone who sees the finding exactly.

### Second looks and the ground they cover

A change of shape leaves the tier, every answer and its weight as they were (Decision 0029). What it changes is the ground that has been looked at, and what lies beyond it.

- **Each answer** records the `shape_revision` it was given on. `PUT /findings/{public_id}/observation` takes `shape_revision`, and one that differs from the finding's is 409 `shape_changed`, decided under the finding's lock, with nothing stored. Without it, the answer is taken as given on the shape as it is. A review card and a help-wanted task give the revision only to someone who sees the finding exactly. An answer kept in the browser as a draft carries the revision it was begun on, and one begun on a shape that has since changed is removed and not offered, on the finding's page and in the review queue (`answerDrafts.ts`). A draft kept before answers named a revision counts as given on revision 0.
- **`looked_at`** grows with each second look (`looked_at.grow`). What is added is the finding's shape then, an area as its edge, or its point when it has no shape, simplified to 5 m. It never shrinks, and is kept under 5,000 vertices by simplifying it further, up to 62.5 m.
- **The rule.** While `looked_at` is set, an edit must keep every looked-at point, and at least three-quarters (`LOOKED_AT_MIN_KEPT = 0.75`) of the length of the looked-at lines, within 250 m (`LOOKED_AT_MAX_MOVE_M`) of the new shape, or of the new point when there would be no shape. An area counts as all of its inside. Otherwise the edit is 422 `looked_at_moved`, which says how much would be left. Distances are measured on the national grid under what was looked at. A finding answered before `looked_at` existed is seeded from its stored shape first (`looked_at.seed`). A finding with no second look standing and no `looked_at` changes freely.
- **What was added.** After every change of shape and every second look, `added_since_looked_m` is the length of the shape, or of an area's edge, lying further than 250 m from `looked_at`, and `added_view` frames it (`looked_at.refresh_added`). Above 200 m (`confidence.NEW_PART_LOOK_M`) the finding gains the next step `look_at_new_part`, which never moves the tier. The step goes when a second look covers the new part or the part is cut away.
- **On the page.** The finding page says "N added since the last second look" with "Show the new part on the map", and lists the newest 50 changes in the timeline (`findings.SHAPE_CHANGES_SHOWN`), an extension with its length and "Show what was added" (`features/finding/shapeChanges.tsx`). While the finder changes a shape, `looked_at` is drawn as a faint wide line under the path, and the panel says how much of it has to stay.

### What each reader is sent

One function decides each reader's view of a shape, `sensitivity.visible_shape`, with `sees_exact` as the rule ([Decision 0005](decisions/0005-sensitive-findings-are-generalised-by-viewer.md), Decision 0032). An open finding is exact for everyone. A protected one is exact for every signed-in member, and a 1 km square for a signed-out visitor.

| Where | A reader who sees the finding exactly | A signed-out reader of a protected finding |
|-------|----------------------------------------|---------------------------------------------|
| `GET /findings/{public_id}` `location` | `outline` (the `outline_mid` copy), `path`, and `shape` with `kind`, `length_m`, `revision`, `extent`, the newest 50 changes oldest first, each with its date and an extension's length and view, `added_since_looked_m` and `added_view`. `shape.looked_at` goes only to someone who may change the finding | The square. `outline`, `path` and `extent` are null, and `shape` holds only a `{"kind": "changed", "on": …}` entry for each of the newest 50 changes. The finder's saved view loses its zoom, as every hidden finding's does |
| `GET /findings`, `/users/{handle}/findings`, investigation items, activity, mentions | No outline. `location.shape_kind` says `line` or `area` | No outline, and `shape_kind` null |
| `GET /review/tasks` | No outline. `place.shape_kind` says `line` or `area`, and a task gives the finding's `shape_revision`. A `look_at_new_part` task is offered, with its place and zoom framing the finding's `added_view` | The task's place is the square, with no outline, no `shape_kind`, no `shape_revision` and the finder's view without its zoom. No `look_at_new_part` task is offered |
| `GET /review/next` | A card holds the place, the finder's view and `shape_revision`. A `look_at_new_part` card's place and zoom frame the finding's `added_view` | No card: the queue offers only findings the reader sees exactly |
| `GET /records/{record_id}/findings` | The finding's public id, title, class, tier and state, with no position or shape | Left out: the list holds only findings the reader sees exactly |
| `GET /geo/search` by public id | The anchor, the saved zoom or 17, and for a line or area a `bbox` framing all of it | The square's centre at zoom 14, `obscured`, and the square as the `bbox` |
| `GET /events/stream` | The same for every reader: an event's id and kind, and the public ids of its finding, investigation and actor, only for events a signed-out visitor's feed lists | The same. `shape_extended` on a protected finding isn't announced, since that feed doesn't list it |
| `GET /findings?format=geojson&zoom=` | `properties.shape`: `outline_low` below zoom 13, `outline_mid` to 15, `outline` from 16, each cut to the box widened by 500 m (`ST_ClipByBox2D`), so a shape may arrive as a `MultiLineString` or `MultiPolygon`. The `bbox` matches the shape as well as the anchor | No `shape`. The `bbox` matches the square's centre alone |
| Downloads | The anchor as the geometry, with `shape_kind`, `shape_length_m` and the whole derived shape as the `outline` property. For a protected finding this goes only to the finder and trusted people | The square, with no `outline`. A member who isn't trusted downloads a protected finding the same way |
| `finding_shape_changes` | Never served whole. `path_before` isn't sent to anyone | |

Investigations hold back what is drawn within 1.5 km of a finding the reader doesn't see exactly, measured to its point or anywhere along its line or area (`sensitivity.hidden_near`, `PositionGuard.near`, [Decision 0030](decisions/0030-the-privacy-guard-measures-to-a-protected-finding-s-whole-shape-and-open-shapes-near-one-aren-t-generalised.md)). A finding a moderator has hidden takes no part in that rule: `hidden_near` and `near_hidden_clause` leave out any finding with `hidden_at` set. An investigation that holds or has held a hidden finding still holds back what is written beside it. An investigation's area that comes that near is shown as the whole 1 km squares it covers (`PositionGuard.area`). An open finding's shape is shown by its own level, whatever protected findings it passes near.

### Drawing findings on the map

`map/findingsData.ts` turns each feature's `shape` into a line or area feature with its kind and its size (a line's length, an area's extent), beside the anchor marker every finding keeps. `map/overlayLayers.ts` draws them under the markers, in the tier colour:

- A line is 2.5 px wide on a casing 1.5 px wider on each side in `--bg`, with round joins and caps. A known finding's line is 1.5 px.
- An area is its edge, 2 px on the same casing, over a fill at 4% opacity, so the terrain inside stays readable. A known finding's edge is 1.25 px.
- A ruled-out finding's line or edge is 1.5 px in `--state-ruled-out`, shown only with the ruled-out switch.
- An obscured finding is its dashed square and never a line.

The overlay asks for nothing below zoom 9, sends the map's zoom with the box, and hides with the rest of the findings during a blind second look.

### Picking one of overlapping findings

`map/findingHits.ts` decides what a click or tap opens ([Decision 0031](decisions/0031-a-point-s-kind-is-switched-by-a-control-or-a-long-press-on-its-handle-and-overlapping-findings-are-picked-by-their-edges.md)).

1. Candidates are finding markers, lines and areas' edges within a box round the tap: 16 px for a finger, 6 px for a mouse or a pen. The kind of pointer is the click event's `pointerType`. Where a browser doesn't give one, it is the kind of the last pointer to go down on the page. An area's inside is never a candidate.
2. Markers beat lines and lines beat area edges. Among the best kind present, the smaller wins only when it is under half the next one's size. Two markers in reach, or two lines or areas alike in size, open the chooser.
3. The chooser (`features/explore/FindingChooser.tsx`, on `ui/Chooser.tsx`) says "N findings here" and lists each with its title, tier and class, in that order, at most 8 and then "Show all in Explore". On a computer it is a popover beside the pointer and on a phone a short sheet, placed so it never covers the tap. Hovering or focusing an entry highlights its shape. The arrow keys, Home and End move through it, Enter opens, and Escape closes it and puts focus back on the map.
4. On a computer the pointer, checked once a frame, highlights what a click would open, or says "N findings here" where it would open the chooser.
5. Findings win over records. Obscured squares aren't candidates: a tap inside one opens its finding, or brings Explore to a square holding several.
6. Explore's list is the keyboard route to every finding in view, and focusing or hovering an entry highlights its shape.
7. While the marking panel is open, taps belong to the drawing tool and other findings don't take them.

## Constraints

- A finding has one part. A path of several parts, or an area with holes, can't be drawn, and an old outline of either kind can only be replaced.
- Smooth points take their curve from their neighbours. There are no handles to drag.
- Only the finder changes a shape, so a finding whose finder has left can't be changed.
- The anchor's square is the only place a signed-out reader of a protected finding is given. Suggested records start from the anchor, not from the whole line.
- Where members have drawn investigation areas along a protected line, the squares those areas are shown as tell a signed-out reader roughly where the line runs, to within about 2 km (Decision 0030, point 4).
- Every change of shape keeps the path before it, and nothing limits how many a finding may have beyond the hourly limit on writes. The page serves the newest 50. The rows of a finding changed over and over stay in `finding_shape_changes` until someone removes them.

## Implementation status

**Implemented:**

| Part | Where |
|---|---|
| The path, the curve, the limits and the anchor | `backend/src/fieldclub/services/shapes.py` |
| Applying a change, and the map's shapes | `backend/src/fieldclub/services/shape_edits.py` |
| The ground looked at, and what was added | `backend/src/fieldclub/services/looked_at.py` |
| What each reader is sent | `backend/src/fieldclub/services/sensitivity.py` |
| The drawing tool and "Change the shape" | `frontend/src/features/mark/` |
| Drawing and picking on the map | `frontend/src/map/findingsData.ts`, `overlayLayers.ts`, `findingHits.ts`, `frontend/src/features/explore/` |

**Deferred:**

| Part | Gap | Tracking |
|---|---|---|
| Other people's changes as suggestions, a marking handed on, and removing an orphaned marking | Planned, not built | [Plan: lines and shapes, phase 2](../plans/lines-phase-2.md) |
| Undoing a saved change | `path_before` is kept but nothing offers it | Not planned. [Plan: lines and shapes, phase 2](../plans/lines-phase-2.md) leaves it out |

## Decisions behind this

- [Decision 0005 — Sensitive findings are generalised by viewer](decisions/0005-sensitive-findings-are-generalised-by-viewer.md)
- [Decision 0028 — A finding's shape is its tapped points under one fixed curve, within size caps, around an anchor that stays put](decisions/0028-a-finding-s-shape-is-its-tapped-points-under-one-fixed-curve-within-size-caps-around-an-anchor-that-stays-put.md)
- [Decision 0029 — Only the finder changes a shape, a change keeps the second looks, and most of what was looked at stays](decisions/0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md)
- [Decision 0030 — The privacy guard measures to a protected finding's whole shape, and open shapes near one aren't generalised](decisions/0030-the-privacy-guard-measures-to-a-protected-finding-s-whole-shape-and-open-shapes-near-one-aren-t-generalised.md)
- [Decision 0031 — A point's kind is switched by a control or a long press on its handle, and overlapping findings are picked by their edges](decisions/0031-a-point-s-kind-is-switched-by-a-control-or-a-long-press-on-its-handle-and-overlapping-findings-are-picked-by-their-edges.md)
- [Decision 0032 — Findings are open or protected, and the restricted level is dropped](decisions/0032-findings-are-open-or-protected-and-the-restricted-level-is-dropped.md)
- [Decision 0035 — A version reads a stored class it has no name for as not sure](decisions/0035-a-version-reads-a-stored-class-it-has-no-name-for-as-not-sure.md)
