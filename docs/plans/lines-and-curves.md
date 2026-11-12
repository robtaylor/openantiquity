# Plan — Lines and curves for marking findings: draw a finding as a straight or curved line or shape, and extend it later

**Status:** Proposed.

## Goal

A finder can mark a finding as a line or a closed shape made of straight and smooth points, the way Illustrator's pen and curvature tools work, on a computer and on a phone. A line can be as long as a Roman road, and the finder can add to either end later. A protected or restricted finding's shape never reaches anyone who sees it only as its 1 km square. This plan builds on Decisions 0005, 0008, 0019, 0021, 0022, 0023 and 0024, and needs the new records listed under "Decisions to write".

## Prerequisites

- The owner's answers in "Decided by the owner" below.
- A local PostGIS from `infra/docker-compose.yml` for the backend suite.
- Nothing deployed holds an outline that this plan can't read. Every outline the interface has ever sent is a `LineString` or a single-ring `Polygon` (`frontend/src/features/mark/outline.ts`, `outlineGeometry`).

## What exists (2026-11-12)

Each claim here was checked by reading the code on `feat/lines-and-curves`.

- **Marking.** `MarkForm.tsx` has an optional Outline step after the point is placed (`OutlineTool`). Taps add corners, "Add a corner at the cross" adds one at the map's centre for keyboard and precise phone use, a tap within 14 px of the first corner closes the shape (`MarkLayer.tsx`, `CLOSE_TOLERANCE_PX`), and "Finish as a line" ends it open. Segments are straight. The preview is SVG, re-projected point by point on every render.
- **Storage.** `findings.outline` is any geometry, with no spatial index (`any_geometry(spatial_index=False)`). `OUTLINE_TYPES` allows `Polygon`, `MultiPolygon`, `LineString` and `MultiLineString`. `check_outline` refuses an outline more than `OUTLINE_MAX_SPAN_DEG = 0.05` across (`outline_too_big`) or more than `OUTLINE_MAX_GAP_DEG = 0.01` from the point (`outline_too_far`). It doesn't check that a polygon is valid. `schemas/shapes.py` caps any client shape at 2,000 positions and 200 parts (`geometry_too_complex`).
- **The point.** `location` is required and is the finding's anchor for `location_public`, `grid_ref`, `nation`, the suggested title, the activity square and every `bbox` match.
- **Editing.** `PATCH /findings/{public_id}` is the only edit route, and `findings.check_finder` lets only the finder use it. It can replace `location` and `outline`. An edit leaves every second look standing and the tier where it was. Only a change of class reassesses. A move is recorded nowhere except that `activity.relocate` moves the finding's activity rows to its new square. Nothing limits how far a finding with answers can be moved, beyond staying in the British Isles. The interface's edit dialog (`features/finding/Tools.tsx`) changes title, description, class and period only.
- **Where a saved outline is drawn.** Nowhere. No frontend code reads `location.outline` from a response. The map's GeoJSON carries points only (`schemas/findings.py`, `finding_feature`, `with_outline=False`).
- **Where geometry leaves the API.** `location_out` builds every position and calls `sensitivity.visible_location`, which drops the outline when the viewer doesn't see the finding exactly. It is called with the outline for: `FindingSummary` (`GET /findings`, `GET /users/{handle}/findings`, investigation items), `FindingDetail`, `ActivityFinding` (the activity feed), `MentionedFinding` (`GET /mentions/recent`) and help-wanted tasks (`GET /review/tasks`). Review cards use the place alone. Downloads add the exact outline as an `outline` property for those who download exactly (`services/exports.py`). Search and suggested records use the visible point.
- **Near a protected finding.** `sensitivity.hidden_near` and `PositionGuard.near` measure distance from `Finding.location` only (Decision 0023).
- **Hit testing.** `findingPointAt` (`map/findingHits.ts`) asks MapLibre for rendered finding points at the exact tap position, with no tolerance, and Explore opens the first. Findings win over records, an obscured square is an outline only, and a square holding several obscured findings brings Explore to it (`features/explore/ExploreLayer.tsx`). While marking, taps belong to the mark tool.
- **Long press.** A right click, or a long press where the browser fires `contextmenu`, already opens "open elsewhere" for the spot (`features/records/useRecordsOnMap.ts`).
- **Drafts.** A finding draft is the `POST /findings` body with `outline` as GeoJSON (`findingDrafts.ts`), owned by the tab (Decisions 0022, 0024).
- **Schema changes.** There's no migration history. `create_schema` runs `create_all` and `models/extras.sql`, which already adds a column to an existing table with `ALTER TABLE … ADD COLUMN IF NOT EXISTS` (`records.search`). A deploy runs it through `fieldclub-release`.

## Decided by the owner

- Smooth curves or straight lines through tapped points, closed by joining the ends, like Illustrator.
- A marking can be extended later. Only the person who marked a finding may change or extend it. Joining different people's lines is left out.
- Extending a line keeps the finding's step on the ladder. Second looks already given stand, the extension is recorded on the finding, and the page says how much has been added since anyone looked and invites fresh looks at the new part.
- Closed shapes are refused above 25 km across. Lines may run long, with a cap above the longest real feature.
- On a phone the interaction is designed for touch first. Shift-click is fine on a computer, and every gesture has a visible control that does the same.
- Overlapping findings are picked by their edges, and the more specific wins: markers, then lines, then area edges, then the smaller of two alike. A chooser settles what remains: a popover on a computer, a sheet on a phone, highlighting each shape as its entry is hovered or focused. A computer's pointer shows what a click would select, a finger gets a wider reach, and the Explore list is the keyboard route.
- A reshape that moves earlier points is treated as an extension is: second looks stand and the change is recorded and shown, without the invitation to look at a new part.
- An open line that passes near somebody else's protected finding is not generalised.
- Points can be moved, never a whole shape. Small tweaks stay possible once a finding has second looks, shortening a line among them, while most of what was looked at stays where it was. The owner agreed the figures: three-quarters of it, within 250 m.
- Later, as a second phase with a plan of its own: other people's changes to a marking handled as suggestions its keeper accepts or declines, a marking that can be handed on, and a way for admins to remove orphaned markings that cause trouble. The owner agreed that "found by" is the credit and never changes, and that "kept by" is who may change a marking and accept suggestions, and is what passes on. See "Left out of the first version".
- Marking is one flow that starts with a tap. A tap always adds a point and a drag moves one, and the side panel carries guidance that changes as the marking grows.
- The build goes ahead once the coordinator has checked this plan.

## Design

### The data model

The path is the source of truth. The server derives the stored geometry from it with one fixed curve, so the finder can reopen it, move a point or extend it, and the curve can be re-derived if its definition ever changes.

The browser-flattens alternative was weighed and rejected. If the browser sent only flattened geometry, the smooth and corner points would be lost and the path couldn't be reopened. If it sent both, the server would still have to derive the geometry to check that the two agree, which is the same work with one more way to be wrong.

New and changed columns on `findings`:

| Column | Type | Meaning |
|--------|------|---------|
| `path` | jsonb, null | The tapped points and whether the shape is closed (see "The path"). Null for a point-only finding, and for an old outline until it is next edited |
| `outline` | Geometry, now with a GIST index | The full derived shape, a `LineString` or `Polygon`. Unchanged for old findings |
| `outline_mid` | Geometry, null | `outline` simplified at 0.00005° (about 3 to 5 m), for zooms 13 to 15 and for the finding page |
| `outline_low` | Geometry, null | `outline` simplified at 0.0005° (about 35 to 55 m), for zooms 9 to 12 |
| `shape_kind` | text, null | `line` or `area`, or null without a shape |
| `shape_length_m` | real, null | Geodesic length of a line, or perimeter of an area |
| `shape_revision` | int, default 0 | Raised by one on every change to the shape |
| `looked_at` | Geometry, null | The ground second looks were given on: the union of the finding's shape, or point, at each second look. See "Once looked at, most of it stays" |
| `added_since_looked_m` | real, null | How much of the shape lies further than 250 m from `looked_at`. See "Extending, and what it does to second looks" |
| `added_view` | jsonb, null | A centre and zoom that frame that part |
| `location_derived` | bool, default false | True when the server chose `location` from the shape |

`observations.shape_revision` (int, null) records the finding's `shape_revision` when the answer was given, as `tier_at_answer` does for the tier.

New table `finding_shape_changes`: `finding_id*`, `user_id*`, `revision*`, `kind*` (`drawn`, `extended`, `reshaped`, `closed`, `opened`, `removed`), `points_before*`, `points_after*`, `length_before_m`, `length_after_m`, `added_length_m`, `added_view` jsonb (a centre and zoom framing the added part, for an extension), `path_before` jsonb, `created_at`. Unique on finding and revision. Rows are never served whole: see "Sensitivity".

Migration: the columns go in through `create_all` for new databases and `ALTER TABLE findings ADD COLUMN IF NOT EXISTS …` in `models/extras.sql` for existing ones, with the GIST indexes on `outline` and `outline_low` as `CREATE INDEX IF NOT EXISTS`.

The schema is built on the live database at every deploy, while the old version still serves, so `create_schema` is careful with locks. Each `ALTER TABLE` in `extras.sql` is skipped when its columns are there already (`fieldclub_has_columns`), because it takes an ACCESS EXCLUSIVE lock even when it changes nothing. The transaction sets `lock_timeout` to `SCHEMA_LOCK_TIMEOUT_MS = 5000`, so a deploy that can't get a lock fails and changes nothing, and the old version goes on serving. Every vocabulary check (`models.common.enum_check`, such as the activity kinds that gain `shape_extended`) is made again when its stored values differ from its enumeration's now. The new check is added `NOT VALID` and validated in a second transaction, so the table isn't scanned under the strongest lock. Nothing is backfilled. An old outline gets its `path`, simplifications and kind when it is next saved, and `services/shapes` derives a path from it on read (see "Drafts and old data"). The simplified columns are filled for old outlines by an idempotent `fieldclub-ingest`-style command, `python -m fieldclub.services.shapes backfill`, run once by hand after the deploy. Each of its updates repeats the test it read the row by, with the revision read, so an edit committed meanwhile is left as it is, and an empty outline is logged and passed over.

### The path

```json
{
  "closed": false,
  "curve": "catmull-rom-centripetal-1",
  "points": [
    {"lon": -1.234567, "lat": 51.234567, "kind": "corner"},
    {"lon": -1.230000, "lat": 51.240000, "kind": "smooth"}
  ]
}
```

- `kind` is `corner` or `smooth`. A segment between two corners is straight.
- `curve` names the definition below. A request may leave it out and the server writes it. A request naming another value is refused with 422 `unknown_curve`.
- An open path has 2 points or more, a closed one 3 or more. A closed path doesn't repeat its first point.
- Two consecutive points, and for a closed path the last and the first, are at least 1e-6 degrees apart in the projected plane below (about 7 to 11 cm). Closer is 422 `points_too_close`, because the curve divides by that distance.

### The curve, `catmull-rom-centripetal-1`

Two people implementing this must get the same shape. The server's output is the stored truth. The browser's preview only has to look the same, so the shared test vectors compare to 1e-7 degrees and don't need byte equality.

1. **Segments.** An open path of `n` points has segments `P[i] → P[i+1]` for `i = 0 … n−2`. A closed path also has `P[n−1] → P[0]`, and indices wrap.
2. **Straight segments.** When both ends of a segment are corners, the segment emits its end point alone.
3. **Neighbours.** Otherwise call the ends `A` and `B`. `prev` is the point before `A` when `A` is smooth and that point exists. `next` is the point after `B` when `B` is smooth and that point exists. In a closed path both always exist. A corner end, or an open path's end, has no real neighbour: it gets a phantom, made in the projected plane as `prev' = 2A' − B'` or `next' = 2B' − A'`. So a corner behaves like the end of a curve on each side, and the curve leaves it heading straight for the next point.
4. **Projection.** Each segment has its own scale `k = cos(radians((A.lat + B.lat) / 2))`. A point maps to `(x, y) = (lon · k, lat)` and back by `lon = x / k`. Only the segment's own ends set `k`, so extending a path never changes a segment more than one away from the new point.
5. **Knots.** `t0 = 0`, `t1 = t0 + d(prev', A')^0.5`, `t2 = t1 + d(A', B')^0.5`, `t3 = t2 + d(B', next')^0.5`, where `d` is the Euclidean distance in the projected plane.
6. **Samples.** `L = d(A', B')`. The segment has `N = min(16, max(2, ceil(L / 0.0003)))` steps, about one every 33 m. For `j = 1 … N−1` it emits `C(t1 + (t2 − t1) · j / N)`, then `B` itself.
7. **Evaluation**, the Barry–Goldman form, with `P0 … P3 = prev', A', B', next'`:
   - `A1 = ((t1 − t)·P0 + (t − t0)·P1) / (t1 − t0)`, `A2 = ((t2 − t)·P1 + (t − t1)·P2) / (t2 − t1)`, `A3 = ((t3 − t)·P2 + (t − t2)·P3) / (t3 − t2)`
   - `B1 = ((t2 − t)·A1 + (t − t0)·A2) / (t2 − t0)`, `B2 = ((t3 − t)·A2 + (t − t1)·A3) / (t3 − t1)`
   - `C = ((t2 − t)·B1 + (t − t1)·B2) / (t2 − t1)`
8. **Output.** The geometry starts with `P[0]` and appends each segment's points in order. An open path is a `LineString`. A closed one ends back on `P[0]` and is a one-ring `Polygon`. Each derived coordinate is rounded to 7 decimal places. Tapped points are stored as sent, rounded the same way.

The definition lives once in prose in the area doc, and once as data: `docs/architecture/curve-vectors.json`, a list of paths with their expected geometry, read by a pytest test and a Vitest test. The vectors cover a straight path, a single smooth point, mixed kinds, a closed all-smooth path, a closed path with one corner, a hairpin, unequal spacing, a path near 61° N and one at 49.9° N, and a path extended at each end, where every segment more than one from the new point must be unchanged.

### Limits, and why there are any

The owner asked why a size limit is needed. Without one, these break or can be abused:

- **Map views.** Every map view sends a `bbox`, and a shape matches every box it crosses. A finding covering a county would be fetched and drawn in every view of that county, and would take one of the 1,000 places a GeoJSON page holds (`GEOJSON_MAX_LIMIT`).
- **"What's here" queries.** Explore, the nearby lists and the record matching treat a finding as being where its shape is. An area of 2,000 km² is "here" everywhere inside it, so every list in that area leads with it.
- **The privacy guard.** Decision 0023 holds back every investigation view and profile within 1.5 km of a finding the reader doesn't see exactly. Measured from the whole shape, a restricted scribble across a county would hold back every view there. That is a denial of service on other people's investigations.
- **Cost.** Every derived vertex is stored, simplified and sent. 50,000 vertices is about 800 KB of WKB per finding.
- **What a second look means.** A reviewer answers "can you see a feature here" from one view. A 100 km enclosure can't be seen in any view, so an answer about it means nothing.

The caps are set as loose as those reasons allow:

| Limit | Value | Code | Sized against |
|-------|-------|------|---------------|
| Closed shape across | 25 km, the larger of its east–west width at its middle latitude and its north–south height, in metres | `shape_too_big` | The owner's figure. It takes the largest single earthworks, such as Stanwick's oppidum ramparts at about 2.5 km and the Salisbury Plain field systems at several kilometres, with a wide margin. Inference: the feature sizes are from general knowledge, not measured here |
| Line length | 600 km, geodesic, of the derived line | `line_too_long` | Watling Street from Dover to Wroxeter, about 440 km, the Fosse Way at about 370 km, and Ermine Street at about 320 km. 600 km leaves room for a drawn line that wanders a little and for a road followed into its continuation. Inference: road lengths are from general knowledge |
| Tapped points | 5,000 per path, counted before the points are read | `path_too_many_points` | Watling Street with a point at every bend and every 100 m along curves. 5,000 points is about 300 KB of JSON, inside the 1 MB body limit |
| Derived vertices | 50,000 | `shape_too_complex` | 5,000 points of which most are smooth, at the sampling above. The message suggests using corners on the long straight stretches |
| Shape to placed point | 1,000 m, when the finder placed the point | `outline_too_far` | The current 0.01°, expressed in metres so it means the same at every latitude |
| Closed shape validity | Its ring mustn't cross itself | `shape_crosses_itself` | GEOS gives wrong answers on invalid polygons, and today nothing refuses one |

Lines have no "across" limit, so a 600 km road is fine. A length cap doesn't stop someone scribbling 600 km back and forth inside one parish. That is left to moderation, which can hide the finding, and to the rate limits on creating and editing findings.

`OUTLINE_MAX_SPAN_DEG` and `OUTLINE_MAX_GAP_DEG` are replaced by `SHAPE_MAX_ACROSS_M = 25_000`, `LINE_MAX_LENGTH_M = 600_000` and `SHAPE_MAX_GAP_M = 1_000`, in `services/shapes.py` beside `PATH_MAX_POINTS = 5_000` and `SHAPE_MAX_VERTICES = 50_000`. The frontend mirrors them from `/meta`, not as constants of its own, so they can't drift.

### The point a line finding keeps

A finding keeps its required point, now called its anchor in the docs. Everything that places a finding by one point goes on using it: `location_public`, `grid_ref`, `nation`, the suggested title, the activity square, the obscured square, search and suggested records.

- **When the finder places it.** A finding of one point is where the finder tapped. The API still takes a placed point with a shape, which must come within 1,000 m of it, for findings made before this tool. The new tool never sends both.
- **When the line comes first.** A `POST /findings` with a `path` and no `location` gets an anchor from the server: for a line, the point half way along the derived line, its length measured on the ellipsoid, so a straight line of two points is anchored at its middle and not at an end; for an area, its centroid when that lies inside, otherwise shapely's `point_on_surface`. `location_derived` is set.
- **When the shape changes.** A derived anchor stays where it is while the new shape passes within 25 m of it. Extending a line at its ends never moves it, because the middle of the line doesn't change. When an edit moves the line away from it, the anchor moves to the point on the new shape nearest to where it was, not to the new middle. A placed anchor never moves by itself: the edit is refused with `outline_too_far` and the finder moves the point.

Re-deriving the middle on every extension was the first idea and was rejected. Each new middle can fall in a new 1 km square, so someone who sees a restricted line only as a square would see a trail of squares along it, one per extension. Keeping the anchor where it was shows them one square for the finding's whole life, as a point finding does.

When the anchor moves, `grid_ref`, `nation`, `location_public`, a suggested title and the activity rows follow, as they do today when the finder moves a point.

### The API contract

All under `/api/v1`. Mutating requests carry `X-OpenAntiquity-Client: web` as every route does.

**`POST /findings`** adds `path: Path | null`. `location` becomes optional when a `path` is given.

- `outline` is still accepted for a release, and a `LineString` or one-ring `Polygon` becomes an all-corner path, so the derived shape equals what was sent. Any other type is 422 `outline_not_a_path`. Sending both `outline` and `path` is 422 `outline_and_path`.
- Without `path` and without `location`: 400 `location_required`, the status and code `PATCH` already uses. One code has one status.
- The limits above apply, then `outside_british_isles` for any point outside `BRITISH_ISLES`.

**`PATCH /findings/{public_id}`** adds `path: Path | null` and `path_revision: int`.

- `path` replaces the whole path. `path: null` removes the shape, recorded as `removed`.
- `path_revision` is required whenever `path` is sent, and must equal the finding's `shape_revision`. Otherwise 409 `shape_changed`, so an edit in one tab can't silently undo an extension made in another. Missing is 422 `path_revision_required`.
- Only the finder: 403 `not_finder`, as today.
- The server classifies the change. It is `extended` when the old points appear unchanged and in order as one run inside the new path, the new path adds points only before or after that run, and `closed` is unchanged. Otherwise it is `reshaped`, `closed`, `opened`, `drawn` (no shape before) or `removed`.

**`PUT /findings/{public_id}/observation`** adds `shape_revision: int | null`, the revision of the shape the answer was given on. A review card (`GET /review/next`) and a help-wanted task (`GET /review/tasks`) carry the finding's `shape_revision`, and the finding page has it as `location.shape.revision`.

- When it is sent and differs from the finding's, the answer is 409 `shape_changed`, the code `PATCH` uses, and nothing is stored. The client shows the finding again. Otherwise an answer would be credited to a shape the reviewer never saw, and `looked_at` would grow by ground nobody looked at.
- Left out, the answer is taken as given on the shape as it is now, so a tab opened before the deploy still works.
- The comparison is made under the finding's row lock, which serialises answers and edits.
- A task gives `shape_revision` only to a viewer who sees the finding exactly, the only people who can answer. A viewer who sees only the square already gets one `changes` entry for every change, so the number would tell them nothing new.

**`FindingDetail.location`** gains, for a viewer who sees the finding exactly:

```json
{
  "outline": {"type": "LineString", "coordinates": [[-1.2345678, 51.2345678]]},
  "path": {"closed": false, "curve": "catmull-rom-centripetal-1", "points": []},
  "shape": {
    "kind": "line",
    "length_m": 12400.0,
    "revision": 3,
    "extent": [-1.30, 51.20, -1.10, 51.30],
    "changes": [
      {"kind": "extended", "on": "2026-11-20", "added_length_m": 4200.0, "added_view": {"lon": -1.12, "lat": 51.28, "zoom": 15}}
    ],
    "added_since_looked_m": 4200.0,
    "added_view": {"lon": -1.12, "lat": 51.28, "zoom": 13},
    "looked_at": {"type": "LineString", "coordinates": [[-1.2345678, 51.2345678]]}
  }
}
```

- `outline` in the detail is `outline_mid`, so a 600 km road doesn't cost a phone a megabyte. The full shape is in downloads and is re-derived from `path` by the editor.
- `added_since_looked_m` is the length of the shape lying further than `LOOKED_AT_MAX_MOVE_M` from `looked_at`: for a line its length there, for an area the length of its edge there. It is null when `looked_at` is null or nothing lies beyond. `added_view` is a centre and zoom that frame that part. Both are worked out when the shape changes and when a second look is given, and stored on the finding.
- `looked_at` is the ground second looks were given on, as GeoJSON, which the editor draws under the path. It goes only to someone who may change the finding (`actions.edit`), and is null before any second look.
- For a viewer who sees only the square, `outline`, `path` and `extent` are null, and `shape` is `{"kind": null, "changes": [{"kind": "changed", "on": "2026-11-20"}]}`: they learn that the shape changed and when, and nothing of its size, kind or place.

**Summaries** (`FindingSummary`, `ActivityFinding`, `MentionedFinding`, help-wanted tasks) no longer carry an outline: `location.outline` is always null there, and `location.shape_kind` says `line` or `area` to a viewer who sees the finding exactly and null otherwise. No frontend code reads a summary's outline today, so nothing breaks, and a 200-finding page of long lines would otherwise be tens of megabytes.

**`GET /findings?format=geojson`** gains `zoom` (integer 9 to 22, default 14). Each feature's properties gain `shape: GeoJSONGeometry | null`, given only to a viewer who sees the finding exactly: `outline_low` below zoom 13, `outline_mid` from 13 to 15 and `outline` from 16, each clipped with `ST_ClipByBox2D` to the requested box widened by 500 m. The `bbox` matches a finding's shape as well as its point, but only for viewers who see it exactly. For anyone else it matches `location_public` alone, as now, because a match by shape would tell them the line passes through the box.

**`/meta`** gains `shapes: {path_max_points, shape_max_vertices, shape_max_across_m, line_max_length_m, shape_max_gap_m, curve}`.

**Downloads** keep the point as the geometry and the exact shape as the `outline` property for those who download exactly, as now, with the full derived shape and `shape_kind` and `shape_length_m` as columns. A line stays a property, not the feature's geometry, so a Historic Environment Record import sees the same shape of file as before.

### Extending, and what it does to second looks

The owner decided this. In the code:

- An answer stores `shape_revision` when it is given, and is refused when it names an older one (see "The API contract"). The ladder, its weights and Decision 0019's rule are untouched, because nothing reassesses on a shape change.
- Every change writes a `finding_shape_changes` row, with `path_before` kept for moderators and for a later undo.
- An extension's change row records `added_length_m` and `added_view`, the centre and zoom of the vertices it added, for the timeline.
- What has been added since the last second look is measured from the ground, not from the kind of each change. It is the part of the shape further than 250 m from `looked_at` (`added_since_looked_m`, framed by the finding's `added_view`). So a change that nudges an end point and adds 20 km is a reshape on the timeline and still counts, an area grown round what was looked at counts, and an extension later cut away no longer does. The classifier and each change's `kind` only label the timeline.
- The finding page says, to everyone who sees it exactly, "4.2 km added since the last second look" with a button that opens the map at the finding's `added_view`, and lists each change on the timeline.
- A change that leaves `added_since_looked_m` above 200 m adds a next step, `look_at_new_part`, to the finding's `open_steps`. It appears in help wanted and in the review queue with the finding's `added_view` as its view, and it never moves the tier. It clears when a second look is given, because that look's shape joins `looked_at`, or when the part beyond is cut away. An answer taken back leaves `looked_at` as it was, so it brings back no invitation.
- An edit that stays within what was looked at invites nobody, and no change of shape moves the tier, the score or any answer's weight.
- A reshape that moves points the reviewers looked at, while staying within 250 m of them, is recorded the same way, with "The shape was changed on 20 November" and no invitation, as the owner decided.
- An extension records the activity kind `shape_extended`, placed at the finding's square like every other activity row, and notifies the finding's followers. Answerers aren't notified separately: the finder follows their own finding by default, and anyone who answered can follow it.

People who can see answers (Decision 0010) also see which answers came before each change. Nobody else is told how many answers there were. "Added since the last second look" tells a viewer who hasn't answered that some answer came before that date. The score already moves when answers come in, so the existence of an answer isn't new to them, but the date is a little more. This is recorded in the decision so a later reader knows it was weighed.

What would change if the owner later chose otherwise: if answers given before an extension stopped counting, the stored `shape_revision` lets a reassessment drop them, with no new data needed. That choice would let a finder wipe unwelcome "can't see it" answers by adding a metre to a line, which is why it isn't recommended.

### Once looked at, most of it stays

The owner's answer to how far a finding with second looks may move: "you can only move points, not the whole shape". They then added that people "should be able to make small tweaks to points, e.g. shortening lines". Moving every point in turn is a move of the whole shape by another route, and a line can be extended to somewhere new and its first part then deleted. So the server holds a finding to the ground its second looks were given on, and leaves room for tweaks and for shortening (Decision 0029).

- **No whole-shape move.** The tool moves, adds and deletes single points. The API takes a path, and a change of `location` alone never carries a shape with it.
- **`findings.looked_at`**, a geometry, null until the first second look. When a second look is given, the finding's shape then, or its point when it has no shape, is added to it with a union. An area is added as its edge. It only grows. What is added is simplified to `LOOKED_AT_SIMPLIFY_M = 5` m, far inside the 250 m rule, and the whole is kept under `LOOKED_AT_MAX_VERTICES = 5000` by simplifying it at twice the tolerance, and again, up to 62.5 m, so it stays small enough to send to the finder and buffer on each edit.
- **Second looks from before `looked_at`.** A finding answered before the deploy that brought `looked_at`, or on a machine still running the old version during it, has it null. When such a finding has a second look that stands, the edit check first seeds `looked_at` from the finding's shape as stored before the edit, or its point when it has no shape, and then applies the rule (`looked_at.seed`). `python -m fieldclub.services.shapes backfill` seeds every such finding the same way, each under its row lock, and changes nothing on a second run.
- **The check.** While `looked_at` is set, an edit must keep most of it close. "Close" is within `LOOKED_AT_MAX_MOVE_M = 250` of the finding's new shape, or of its new point when it would have no shape. Every point in `looked_at` must stay close, and at least `LOOKED_AT_MIN_KEPT = 0.75` of the length of its lines must stay close. Otherwise the edit is refused with 422 `looked_at_moved`. The message says how much of what others looked at would be left, that three-quarters has to stay, and that withdrawing the finding and marking it again starts afresh.
- **What it allows.** Extending anywhere. Moving a point, while the shape still passes within 250 m of what was looked at. Shortening a line by up to a quarter of what was looked at, in one edit or over several, because `looked_at` doesn't shrink. Moving a point-only finding up to 250 m.
- **What it refuses.** Removing or dragging away more than a quarter of what others looked at, removing the shape, and moving a point-only finding further than 250 m.
- `/meta`'s `shapes` gains `looked_at_max_move_m` and `looked_at_min_kept`. The tool shows the refusal beside the path, with the looked-at part drawn as a faint under-line while a finding with second looks is being changed. That under-line is shape, so it goes only to someone who sees the finding exactly and may change it.

### Sensitivity: every place a shape leaves

The rule stays Decision 0005's: a viewer who doesn't see a finding exactly gets nothing of its shape. A path is shape. Each place:

| Where | What it does with a path or shape |
|-------|-----------------------------------|
| `GET /findings/{id}` | `outline`, `path`, `extent` and sizes to exact viewers only. Square-only viewers get the change dates alone |
| `GET /findings` page, `/users/{handle}/findings`, investigation items, `GET /records/{id}/findings` | No outline for anyone. `shape_kind` to exact viewers only |
| `GET /findings?format=geojson` | `shape` to exact viewers only. `bbox` matches the shape for exact viewers only |
| Activity feed and event stream | No outline. Activity rows keep the square. Inference: the event stream sends ids, not positions; WS-A step 7 confirms it |
| `GET /mentions/recent`, `GET /review/tasks`, `GET /review/next` | No outline. A review card keeps the place and view only (Decision 0008), and a `look_at_new_part` card uses `added_view`, which is itself shape, so it goes only to people the queue already offers exact findings to |
| Search (`/geo/search`) | The `bbox` frames the shape's extent for an exact viewer, and the square otherwise |
| Suggested records | Unchanged: from the anchor for an exact viewer, from the square otherwise |
| Downloads | The `outline` property only when `downloads_exact` |
| `finding_shape_changes` | Never served whole. `path_before` goes to moderators only |
| Drafts | Kept in the browser, owned by the tab, as now |

**Near a protected finding.** Decision 0023 judges a drawing by its distance from the finding. For a line that must mean its whole shape: a height profile 1.4 km from a restricted road's middle is beside the road even when the anchor is 30 km away. `hidden_near` tests `ST_DWithin` against `location` or `outline`, using the new index, and `PositionGuard.near` measures to the exact shape. More views along protected lines are held back as a result. The default level for `road`, `trackway` and `linear` is open, so this touches few findings.

**An open line passing a protected finding.** An open road drawn past somebody else's protected barrow shows the road, not the barrow. Nothing in the line says the barrow is there unless the line was drawn to point at it, and a member could already do that today with an open point finding on the barrow, which nothing refuses. Generalising every open line near a protected finding would hide most Roman roads from signed-out visitors, since barrows line them. The plan doesn't generalise them, and records this as an accepted limit with a walk-back, as the owner decided.

**The leak test.** `tests/test_routes.py` names a leak test for every route. Each test in `tests/findings/test_leaks.py` gains a line finding and an area finding at every level, and checks that the path, the outline, the extent, `shape_kind`, the length and `added_view` never reach a viewer who sees the square, and that a `bbox` placed on the line's far end doesn't return a restricted line to them.

### Drawing findings on the map

- Exact line findings are a line layer coloured by tier with the same dark 1.5 px casing as the markers, `line-join: round`. Areas are their edge alone in the tier colour, with the faintest fill, so the terrain inside stays readable, as record outlines are drawn. Known findings are drawn dashed-free but thinner, and ruled-out ones in `--state-ruled-out` behind the ruled-out switch, as the markers are.
- Every finding keeps its tier marker at its anchor, so a line has one marker that names its tier and can be tapped.
- An obscured finding is still its dashed square, never a line.
- Cost at low zoom: the server sends `outline_low` below zoom 13 and clips every shape to the box. A straight Roman road at 35 to 55 m tolerance is a few hundred vertices however long it is. The findings overlay starts at zoom 9 (`FINDINGS_MIN_ZOOM`), so nothing is sent for a whole-country view.
- A blind second look hides the overlay (`hiddenFindings.ts`), and the new layers belong to the same overlay, so they hide with it.

### Picking one of overlapping shapes

Points inside enclosures, crossing roads and roads through field systems will overlap. The owner has decided the rules. The details below fit them to `findingHits.ts` and `ExploreLayer.tsx`, and say where they refine them.

1. **Edges, not insides.** An area is picked by its edge, never its inside, so a point or record inside a large area stays reachable.
2. **Reach.** Candidates are finding markers, lines and area edges within reach of the tap: 6 px for a mouse or pen, 16 px for a finger, chosen from `PointerEvent.pointerType` and queried as a box round the tap. Today's query is at the exact tap position, so a marker under the pointer is always in reach and today's behaviour is kept.
3. **The more specific wins.** Markers beat lines, lines beat area edges. Among candidates of the same kind the smaller wins: the shorter line, or the area with the smaller extent.
4. **A chooser settles what remains.** Refinement: "the smaller of two alike" only decides when one is clearly smaller, under half the other's length or extent. Two roads crossing, or two markers within a finger's reach, are alike, and a silent choice between them would be a guess. So those open the chooser. This keeps the owner's rule and gives "more than one candidate remains" a definite test.
5. **What the winner hides.** A road drawn through a field system wins over the field system's edge. The field system stays reachable by its anchor marker, which every shape finding keeps, by zooming in, and by the Explore list. On a computer, the hover hint names what else is within reach.
6. **The chooser** says "3 findings here" and lists each with its tier badge, class and title, in the order above. Hovering or focusing an entry highlights that shape on the map. It's a popover beside the pointer on a computer and a short sheet on a phone, which never covers the spot tapped (UI.md). It holds at most 8 entries and then "Show all in Explore". Arrow keys move through it, Enter opens, Escape closes it and returns focus to the map.
7. **Hover on a computer.** As the pointer moves, a frame-throttled query highlights what a click would open, or shows "3 findings here" when a click would open the chooser. This follows the records layer's cursor change in `useRecordsOnMap.ts`.
8. **Records.** Findings still win over records. When no finding is in reach, records behave as today.
9. **Obscured squares** are unchanged: a square is an outline, and one holding several findings brings Explore to it. They aren't candidates.
10. **Keyboard.** The Explore list stays the keyboard route to every finding in view, kept in step with the map. Focusing a list entry highlights its shape.
11. **While drawing.** Taps belong to the drawing tool, as they do while marking now (`useFindingClicks` stands down while `marking`). Other findings stay drawn but don't take taps, and a hint says so. Picking one of your own path's points uses the point handles, which are DOM buttons above the map canvas, so no shape under them can take the tap. Where several of your own points are within a finger's reach, the nearest handle wins, and the selected-point bar's "Previous point" and "Next point" reach the rest.

### The drawing tool

One tool marks a finding, whether it is a spot, a line or a shape. It replaces both the placing of a point under the cross and the outline step. It works on a computer by pointer and keyboard, and on a phone by touch, with the same visible controls on both.

**One flow.** The owner asked that marking "just go straight to selecting a point, which you can then extend into a shape". The first tap places a point, and that alone is a finding at a spot. Each further tap adds a point, so it becomes a line, and a tap on the first point closes it into a shape. A tap always adds a point and never moves one: a point is moved by dragging its handle. Today a second tap moves the mark, and that goes.

**The drawing bar**, a `ChipGroup` and buttons in the mark panel, shown above the sheet's peek stop on a phone:

- "Next point: Straight | Curved", the kind a tap adds. It stays as set.
- "Add a point at the cross", for keyboard, switch and precise phone use, as now.
- "Undo" and "Redo", over a stack of 100 path states.
- "Close the shape", enabled at 3 points on an open path, and "Finish".
- A status line, `role="status"`: "12 points, 4.3 km. Tap the map to add the next one at the north end."

**Adding points.** A click or tap on the map adds a point of the chosen kind at the active end. On a computer, Shift-click adds the other kind, so straight and curved points can be mixed without touching the bar. A tap on the first point, within 14 px, closes the shape. Enter finishes, Escape stops drawing and keeps the path.

**Selecting a point.** Each point has a handle: a 12 px dot inside a 44 px target, a `button` like today's `PointHandle`. Tapping or clicking a handle selects it and shows the selected-point bar:

- "Point 12 of 340, curved, SU 1234 5678"
- "Make it straight" or "Make it curved"
- "Delete point"
- "Insert a point after", midway along the next segment
- "Continue from this end", on either end of an open path, which makes it the active end and moves the map to it
- "Previous point" and "Next point"

A drag on a handle moves the point. The arrow keys nudge the selected point, with Shift for bigger steps, as they move the mark now. `[` and `]` step to the previous and next point, Delete removes it. Shift-click on a handle switches its kind. On a computer, Alt-click on a segment inserts a point there, as Illustrator's pen does.

**Handles in tab order.** The path is one tab stop, a roving `tabindex` over its handles, so 2,000 points don't mean 2,000 presses of Tab.

**Phone gestures.** The owner suggested long press or pressure for the shift-click actions. Each was weighed:

- **Long press on the bare map is not used.** It already opens "open elsewhere" where the browser fires `contextmenu` (`useRecordsOnMap.ts`), and it would make every tap wait about half a second before the tool knew which kind of point to add, which breaks UI.md's rule of feedback within 100 ms. iOS Safari doesn't fire `contextmenu` for a long press on a canvas and shows its own callouts elsewhere, so the gesture would behave differently by platform. Inference: the iOS behaviour is from platform knowledge, not checked here.
- **Long press on a handle switches the point's kind.** Handles are DOM buttons, so this doesn't touch the map's gestures. After 500 ms without moving more than 8 px, the kind switches and the dot changes shape at once, a square for a corner and a circle for a curve. A short vibration confirms it where `navigator.vibrate` exists. Handles carry `touch-action: none`, `user-select: none` and `-webkit-touch-callout: none`, and refuse `contextmenu`, so no browser menu or text selection appears. "Make it straight" or "Make it curved" in the selected-point bar does the same, so nobody needs to know the gesture.
- **Pressure is not used.** The Pointer Events standard has a device without pressure report 0.5 while a button is down, so a pressure value can't be told apart from "no pressure". iPhones since the XR and 11 have no 3D Touch hardware, and Android devices report pressure inconsistently. Only a stylus such as the Apple Pencil gives a reliable value. Inference: the hardware claims are from platform knowledge and weren't checked in this repository.
- **Map gestures keep their meaning.** One finger drags the map and two fingers pinch and rotate. MapLibre fires a click only when a touch didn't move, so a drag never adds a point. The tool turns off double-tap and double-click zoom and Shift-drag box zoom while drawing, since both would otherwise act on taps meant for the tool. Inference: that a double-tap fires two clicks before zooming has to be confirmed by a test in WS-B.
- **Mistakes are cheap.** A finger adds points by accident, so Undo is the first button on the bar.

**Long lines.**

- The path line is drawn with a MapLibre GeoJSON source, not SVG, once it is longer than 200 points.
- Handles are drawn only for points in view, and only while 150 or fewer are in view. With more, the ends and the selected point keep their handles and a hint says "Zoom in to change points".
- "Continue from this end" moves the map to that end, so extending Watling Street from where you stopped is one press.

**Starting.** "Mark a finding" starts the tool with nothing placed, and the map takes taps at once. There is no choice between a spot and a shape to make first. "Add a point at the cross" stays on the bar as the way to place a point by keyboard or switch, and for a precise point on a phone, but it is no longer how marking begins. After a class from the linear group is chosen (`linear`, `trackway`, `road`), a finding of one point is prompted to carry on into a line, and that stays optional.

**What is sent.** One point is sent as `location` with no `path`. Two or more are sent as a `path` with no `location`, and the server chooses the anchor. The interface no longer sends a placed point together with a shape, though the API still takes both for findings made before.

**Guidance in the panel.** The owner asked for guidance in the side panel. A short block at the top of the mark panel says what a tap will do now and what else is possible, and changes as the marking grows:

- Nothing placed: tap the map where the feature is; one tap marks a spot.
- One point: this is a spot; tap again to draw a line from it, or drag the point to move it.
- An open line: tap to carry it on, or tap the first point to close it into a shape; drag a point to move it, and select one to change or delete it.
- A closed shape: drag a point to move it, and select one to change or delete it.

Each state adds one line for the device in hand: Shift-click for the other kind of point on a computer, a long press on a point to switch its kind on a phone, and the keys when the map has keyboard focus. The block is plain text in the panel, not a tooltip or a one-time tour, so it is there every time and is read by a screen reader. The status line below it still gives the count and the length.

**Changing a saved finding.** The finding page's tools gain "Change the shape" for the finder (the existing `actions.edit`), which opens the same tool at `/mark/finding/:publicId` with the saved path and its `path_revision`. Saving sends `PATCH` with the whole path. A 409 `shape_changed` reloads the finding and says the shape was changed elsewhere.

### Drafts and old data

- A draft's data gains `path` and drops `outline`. `parseFindingDraft` reads an old draft with an `outline` and no `path` by turning a `LineString` or one-ring `Polygon` into an all-corner path. Anything else is dropped from the draft, keeping the rest.
- `createBody` sends `path`, and `location` only when the finder placed one.
- A saved finding with an `outline` and no `path` is served with a `path` derived the same way on the server (`services/shapes.path_from_outline`), all corners, `shape_revision` 0, so it opens in the tool. An old `MultiLineString`, `MultiPolygon` or polygon with holes, which only a hand-made request could have sent, is served with `path: null` and the finding page says the shape can be replaced but not changed.

## Workstreams

The contract above is what the workstreams build against. WS-A comes first, because WS-B needs the generated client. WS-B can start the curve module and the drawing tool against the shared vectors and stand-in answers while WS-A finishes.

### WS-A — Backend

**Status:** In progress. Steps 1 to 4 landed on 2026-11-12 (`96e2ca4` to `7a712e8`): the curve and its shared vectors, the schema, create and edit, and the routes. Steps 5 to 8 are next.

**Steps, in order, each test first:**

1. **The curve.** `services/shapes.py`: `Path`, `derive(path) -> LineString | Polygon`, `path_from_outline`, `classify_change(old, new)`, the limits. Write `docs/architecture/curve-vectors.json` and `tests/services/test_shapes.py` first: every vector, each limit at its edge and one past it, `points_too_close`, a self-crossing ring, and the extension property that no segment more than one from a new point changes.
2. **The schema.** Columns, indexes, `finding_shape_changes`, `observations.shape_revision`, the `extras.sql` lines. Test that `create_schema` runs twice on a database made before the change and adds the columns.
3. **Create and edit.** `services/findings.create_finding` and `update_finding` take a `path`, derive and simplify, choose or keep the anchor, check the gap, raise `shape_revision` and write the change row. `check_outline` becomes `shapes.check_shape`. Tests on real PostGIS: line-first creation sets a derived anchor at half the length; an extension keeps the anchor, the square and `grid_ref`; a reshape that moves the line moves the anchor to the nearest point; a placed anchor refuses with `outline_too_far`; a stale `path_revision` is 409; only the finder may edit.
4. **Schemas and routes.** `schemas/findings.py` (`Path`, the new `Location` fields, `ShapeOut`), the routers kept thin. `GET /findings?format=geojson&zoom=` with clipped shapes and the bbox rule per viewer. `/meta` shapes. Tests through `TestClient` for every error code in the contract.
5. **Second looks and the ladder.** `observations.shape_revision` on answer, `added_since_looked_m`, the `look_at_new_part` next step, `shape_extended` activity and the follower notification. Tests: an extension leaves tier, score and every answer's weight as they were; the step appears above 200 m and clears with a later answer; a viewer who hasn't answered gets no count of answers.
   Then **once looked at, most of it stays**: `findings.looked_at` grows on each second look, and `update_finding` refuses `looked_at_moved`. Tests: an extension far beyond the looked-at part is allowed; shortening the looked-at part by a fifth is allowed and by a half is refused; two shortenings of a fifth each are refused at the second, because `looked_at` doesn't shrink; deleting the looked-at part after extending elsewhere is refused; a chain of small moves can't carry a line more than 250 m from what was looked at; a point-only finding moves 200 m and is refused at 300 m; a finding with no second looks changes freely; `looked_at` never reaches a viewer who sees only the square.
6. **Sensitivity.** `visible_location` and `location_out` carry the new fields; summaries drop outlines; `hidden_near` and `PositionGuard.near` measure to the shape. Extend `tests/findings/test_leaks.py` and the investigation guard tests with line and area findings at every level, including a profile beside a restricted road far from its anchor.
7. **Everything else that carries a finding.** Activity, mentions, tasks, review cards, search, exports, the event stream. One test per route in `tests/test_routes.py`'s table.
8. **Backfill.** `python -m fieldclub.services.shapes backfill`, idempotent, filling `outline_mid`, `outline_low`, `shape_kind` and `shape_length_m` for old outlines. Test that it runs twice and changes nothing the second time.

**Exit criteria:**

- `uv run pytest`, `uv run ruff check . && uv run ruff format --check .` and `uv run pyright` pass.
- Every route in `tests/test_routes.py` names a leak test that includes a line finding.
- A 5,000-point, 600 km path saves in under a second on the development machine, and its GeoJSON at zoom 9 is under 50 KB.

### WS-B — Frontend

**Status:** Not started. Depends on WS-A step 4 for `pnpm gen:api`. Steps 1 and 2 can start at once.

**Steps, in order, each test first:**

1. **The curve.** `src/features/mark/curve.ts`, a port of `derive`, tested in Vitest against `docs/architecture/curve-vectors.json`.
2. **The path model.** `src/features/mark/path.ts` replaces `outline.ts`: immutable operations to add at either end, insert, move, delete, switch kind, close, open, undo and redo, and the limits read from `/meta`. Vitest for each operation, the closing tolerance, and reading an old `outline` into a path.
3. **Generated client.** `pnpm gen:api` once WS-A step 4 lands. Fix every type the change breaks.
4. **The drawing tool.** `MarkLayer.tsx` and `MarkForm.tsx`: the drawing bar, handles with the roving tab stop, drag, long press on a handle, Shift-click, Alt-click, the selected-point bar, the MapLibre preview source, handle thinning, and double-tap and box zoom turned off while drawing. Tests in `MarkPanel.test.tsx` for keyboard-only drawing of a mixed path, closing, continuing from the start, and a long press switching a point's kind; that a second tap adds a point and leaves the first where it was, and a drag moves a point; that one point is sent as `location` alone and two as a `path` with no `location`; and that the guidance block changes with each state and names the right gesture for the device.
5. **Drafts.** `findingDrafts.ts` carries `path`. Tests that an old draft with an outline opens as an all-corner path and saves.
6. **Changing a saved finding.** "Change the shape" in `Tools.tsx`, `/mark/finding/:publicId`, the 409 reload. The finding page's "added since the last second look" line, the timeline entries and the button to `added_view`.
7. **Drawing findings.** Line and area layers in `overlayLayers.ts`, `findingsData.ts` building them from `properties.shape`, `zoom` sent with the box. Tests in `findingsData.test.ts` that an obscured finding never yields a line.
8. **Picking.** `findingHits.ts` gains the reach box by pointer type, the candidate order and the "clearly smaller" test. A chooser component in `src/ui/` built on `Dialog` and `Sheet`, with hover highlighting. Tests for the one-candidate, many-candidate and record cases, and for focus returning to the map.

**Exit criteria:**

- `pnpm test && pnpm typecheck && pnpm lint` and `pnpm build` pass.
- Every new control has a visible focus ring and is reachable by keyboard, and every gesture has a control that does the same.

### WS-C — End-to-end checks and documents

**Status:** Not started. Depends on WS-A and WS-B.

**Steps:**

1. `frontend/e2e/lines.spec.ts`, against a real backend: draw a mixed line by mouse with Shift-click, save it signed in, reopen it, continue from the far end, and see "added since the last second look" after a second account's answer. Draw a closed shape on the phone project with taps, a long press on a handle and the bar's buttons, and save it as a draft, sign in, send it.
2. `e2e/accessibility.spec.ts`: draw and finish a line with the keyboard alone, and, on the phone project, check that the drawing bar and the chooser never cover the point tapped and that Tab never lands on anything hidden.
3. A leak run: a restricted line seen signed out and as a member shows only its square on the map, the page, the activity feed and a download.
4. The overlap cases: a point inside an area opens the point, a tap inside an area away from its edge opens nothing of it, a road through a field system opens the road, a tap where two roads cross shows the chooser with both, a finger's tap opens the chooser where a mouse's click at the same spot opens one finding, and Explore's list reaches all of them by keyboard.
5. Documents: the findings area doc gains "Shapes" with the curve definition and the limits, `docs/ARCHITECTURE.md` gains the columns, routes and codes, `docs/UI.md` gains the drawing tool, the line and area styles and the chooser, `docs/DESIGN.md`'s "Findings" says a finding can be a line or a shape and extended later, `CHANGELOG.md` `[Unreleased]` leads with what it means for you, and the decision records below. `uv run docs/scripts/doctool.py lint` passes.

**Exit criteria:**

- `pnpm e2e` passes on the desktop and phone projects.
- Every present-tense sentence added to the docs is true of the merged code.

## Decisions to write

They were written on 2026-11-12 as four records, Proposed, and are checked against the code when it lands.

- **Decision 0028 — A finding's shape is its tapped points under one fixed curve, within size caps, around an anchor that stays put.** The path model and `catmull-rom-centripetal-1`, the 25 km, 600 km, 5,000-point and 50,000-vertex caps and what each guards, and the anchor that doesn't trail squares along a restricted line.
- **Decision 0029 — Only the finder changes a shape, a change keeps the second looks, and most of what was looked at stays.** The owner's choices on who changes a shape and what extensions and reshapes keep, the accepted leak of a date, and the `looked_at` rule of 250 m and three-quarters.
- **Decision 0030 — The privacy guard measures to a protected finding's whole shape, and open shapes near one aren't generalised.** Replaces the first point of Decision 0023, and records the accepted limit for open lines.
- **Decision 0031 — A point's kind is switched by a control or a long press on its handle, and overlapping findings are picked by their edges.** Why neither pressure nor a long press on the map is used, the reach for mouse and finger, and the "clearly smaller" test that opens the chooser.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| A protected or restricted shape reaches someone who sees the square | High | One function picks the fields, summaries carry no outline at all, and every route's leak test includes a line finding |
| The two curve implementations drift | Medium | The server's geometry is stored and served, so a drift only changes the preview. Shared vectors run in both suites |
| A long line holds back many investigation views near it when protected | Medium | Linear classes default to open. Moderators can hide a scribble. The walk-back is to judge views against `outline_low` only |
| A dense scribble inside the length cap | Medium | Rate limits, the report button and moderators' hide. Watch for it and add a density rule if it happens |
| Thousands of handles slow a phone | Medium | Handles only in view and at most 150, preview line in MapLibre, not SVG |
| A finder moves a finding with answers to ground nobody looked at | Medium | `looked_at`, the 250 m reach and the three-quarters that must stay (Decision 0029) |
| An answer about a road's first stretch counts for the whole road | Low | The owner accepted this. `look_at_new_part` asks for looks at what was added |
| A double tap adds two points before zooming | Low | Double-tap zoom is off while drawing, and a test checks it |

## Left out of the first version

- Joining or merging different people's lines into one finding, or one person's two findings. Nothing here makes it harder: a path is a list of points, and the change table can record a join later.
- Other people's changes as suggestions. The owner proposed on 2026-11-12 that someone else's change to a marking be a suggestion its owner accepts or declines, that ownership can be handed on, and that admins can remove orphaned markings that cause trouble. It needs its own plan, and the owner confirmed it as a second phase that mustn't change how this one is built. Three habits in this build keep it cheap: who may change a finding is asked in one place, `findings.check_finder`, and the interface asks the server's `actions.edit`, never who the author is; applying a change of shape is a service function of its own that is told who made the change, apart from the check of who may; and the path editor in the browser doesn't know how its result is saved. `finding_shape_changes.user_id` already says who made a change, so an accepted suggestion can credit its author. Today a deleted account's findings stay published and nobody can change them, and a moderator can already hide a finding.
- Bézier handles that the finder drags. Smooth points take their curve from their neighbours alone.
- Snapping to terrain, to records or to other findings.
- Several parts in one finding, and holes in an area.
- Suggested records along the whole of a line. Suggestions still start from the anchor.
- A line as a download's feature geometry. It stays a property.
- Undoing a saved change from the finding page. `path_before` is kept, so it can be added.
- Pressure as an input.

## Open questions for the owner

None. The three that were open were answered on 2026-11-12 and are under "Decided by the owner": a reshape is treated as an extension is, an open line near somebody else's protected finding isn't generalised, and what was looked at stays where it was.

## References

- `../architecture/decisions/0005-sensitive-findings-are-generalised-by-viewer.md`
- `../architecture/decisions/0008-second-looks-are-blind.md`
- `../architecture/decisions/0019-answers-and-votes-keep-the-weight-they-were-given-with.md`
- `../architecture/decisions/0021-what-is-written-and-drawn-beside-a-protected-finding-is-generalised-for-each-reader.md`
- `../architecture/decisions/0022-signed-out-drafts-belong-to-the-tab-that-made-them.md`
- `../architecture/decisions/0023-what-is-drawn-near-a-protected-finding-is-judged-by-distance-and-shown-as-whole-squares.md`
- `../architecture/decisions/0024-drafts-taken-over-at-sign-in-wait-to-be-sent.md`
- `../ARCHITECTURE.md` — Findings, API and Location sensitivity
- `../UI.md` — layout, markers and behaviour rules the tool and the chooser follow
- `v1-england.md` — the plan this follows on from
