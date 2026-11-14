# Findings

*Reference: the current design as it stands in the code. The why lives in the decision records linked from each section; the not-yet-built work is under [Implementation status](#implementation-status). Present tense means "true today". If a claim here is stale, the code moved and this doc didn't.*

A finding is something a member has marked on the map as a possible earthwork: a place, a feature class, a level of protection and a step on the confidence ladder. This doc covers where a finding is and what shape it has. The rest of findings, from the ladder to evidence and discussion, is still described in [the build contract](../ARCHITECTURE.md) ("Findings", "Location sensitivity", "Second looks"). A finding is `open` or `protected` ([Decision 0032](decisions/0032-findings-are-open-or-protected-and-the-restricted-level-is-dropped.md)).

## Shapes

A finding is a spot, a line or a closed shape. A spot is its anchor point alone. A line or a shape is a path of tapped points, and the server draws the stored geometry from the path with one named curve ([Decision 0028](decisions/0028-a-finding-s-shape-is-its-tapped-points-under-one-fixed-curve-within-size-caps-around-an-anchor-that-stays-put.md)). The backend's code is `services/shapes.py` (the path, the curve, the limits, the anchor), `services/shape_edits.py` (applying a change, and the map's shapes), `services/looked_at.py` (what second looks were given on), `services/keeping.py` (who keeps a marking, handing it on, and an admin's removal) and `services/suggestions.py` (other people's proposed changes). The frontend's is `src/features/mark/`.

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
- **When the shape changes.** An anchor the finder placed never moves by itself: the new shape must come within 1,000 m of it. A derived anchor stays where it is while the new shape passes within 25 m of it (`ANCHOR_KEEP_M`), so extending a line at its ends leaves it alone. Otherwise it moves to the point of the new shape nearest where it was. Removing the shape leaves the anchor where it is. When the anchor moves, `grid_ref`, `nation`, `location_public` and the activity rows follow, and so does a title that is still the suggested one, whatever moved the anchor: an edit, an accepted suggestion or an admin's removal (`findings.apply_shape_change`). A title someone wrote stays.

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
| `keeper_id` | Who keeps the marking and may change it. Null while the finder keeps it, so nothing is backfilled |
| `keeping_offered_to`, `keeping_offered_at` | The one standing offer of the keeping, and when it was made |

`observations.shape_revision` holds the finding's `shape_revision` when the answer was given. Each change to the shape writes a `finding_shape_changes` row: `finding_id`, `user_id` (who made the change), `revision`, `kind` (`drawn`, `extended`, `reshaped`, `closed`, `opened` or `removed`), `points_before`, `points_after`, `length_before_m`, `length_after_m`, `added_length_m` and `added_view` for an extension, `path_before`, and `created_at`. It is unique on finding and revision. A finding made with its shape has no row until the shape first changes.

Each suggestion is a `shape_suggestions` row: `finding_id`, `user_id` (who suggested it), `base_revision` (the shape's revision it was made on), `path` and `outline_mid` (the whole proposed path, and its derived shape simplified as `outline_mid` is), `kind` and `length_m` (`classify_change` against the shape it was made on, and its length), `state` (`pending`, `accepted`, `declined` or `withdrawn`), `decided_by`, `decided_at` and `applied_revision` (the revision accepting it made, which names its `finding_shape_changes` row). A partial unique index, `uq_shape_suggestions_pending`, allows one pending suggestion per person per finding.

A new database gets these from `create_all`. An existing one gets the columns from `models/extras.sql`, which adds each set only when it is missing, under the names `create_all` gives, and builds the indexes with `IF NOT EXISTS`. `create_all` adds `shape_suggestions`, and `db._sync_enum_checks` widens the checks on `activity.kind` and `moderation_actions.action`. `tests/test_db.py` builds a database as `main` made it and proves one schema step brings it to what a new database has, with every keeper null, and that a second step changes nothing. `python -m fieldclub.services.shapes backfill` fills the simplified copies, the kind and the length of outlines saved before paths, and seeds `looked_at` for findings answered before it existed. A second run changes nothing.

### Changing a shape

Only the marking's keeper changes, extends or removes a shape, and edits its title, description, class and period. The keeper is the finder until the marking is handed on (see [Keeping and suggestions](#keeping-and-suggestions)). `PATCH /findings/{public_id}` checks `findings.check_keeper` and answers anyone else 403 `not_keeper`. Withdrawing stays the finder's alone, 403 `not_finder` for anyone else, keeper included ([Decision 0029](decisions/0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md)). The interface offers "Change the shape" on the finding page to whoever the server's `actions.edit` allows, and opens the drawing tool at `/mark/finding/:publicId` with the saved path (`ChangeShapePanel.tsx`). Anyone else at that address is told only the keeper changes the shape, and offered "Suggest a change" where `actions.suggest` allows it.

- `path` replaces the whole path, and `path: null` removes the shape. Either needs `path_revision`, equal to the finding's `shape_revision`. Missing is 422 `path_revision_required`, and different is 409 `shape_changed`.
- The interface sends the revision the change began on. When the finding is fetched again with a newer shape while it is open, the tool takes the newer shape up if nothing has been changed there. Otherwise, and after a 409 `shape_changed`, it keeps the change and its undo, turns Save off, says the shape was changed elsewhere and the change wasn't saved, and asks the map for the findings again so the shape as it now is is drawn (`ChangedUnderYou.tsx`). "Save it over the shape as it is now" names the newer revision (`markStore.rename`) and saves. "Start again from the shape as it is now" asks before it discards the change. "Suggest a change" does the same with its own words.
- A path deleted down to one point is sent as `path: null` with that point as `location`, and the finding becomes a spot there. An old shape the tool can't read as a path, of several parts or with holes, opens as the finding's point, and the interface sends nothing for it until a new shape of two points or more is drawn, so Save never removes it.
- `outline` is still read, as an all-corner path. Any other geometry is 422 `outline_not_a_path`, and `outline` with `path` is 422 `outline_and_path`.
- `services/shape_edits.change_shape` holds the new shape to the limits and the British Isles, places the anchor, checks the ground looked at, writes the change row and raises the revision, all under the finding's row lock. `findings.apply_shape_change` calls it and does what follows: the reassessment when the length beyond `looked_at` moved, `shape_extended`, and `activity.relocate` when the anchor moved. An edit, an accepted suggestion and an admin's removal all go through it.
- The change is classed for the timeline (`shapes.classify_change`). It is `extended` when the old open path appears whole and in order inside a longer new open path. Otherwise it is `drawn` (no shape before), `removed`, `closed`, `opened` or `reshaped`.
- An extension, or a reshape of an open line that leaves it an open line at least 200 m longer, records the activity kind `shape_extended`, which tells the finding's followers. A closed shape never records it. The length before an old outline's first change is measured from its geometry when the backfill hasn't stored it (`shape_edits.stored_length`). The feed lists it only to someone who sees the finding exactly.

### Second looks and the ground they cover

A change of shape leaves the tier, every answer and its weight as they were (Decision 0029). What it changes is the ground that has been looked at, and what lies beyond it.

- **Each answer** records the `shape_revision` it was given on. `PUT /findings/{public_id}/observation` takes `shape_revision`, and one that differs from the finding's is 409 `shape_changed`, decided under the finding's lock, with nothing stored. Without it, the answer is taken as given on the shape as it is. A review card and a help-wanted task give the revision only to someone who sees the finding exactly. An answer kept in the browser as a draft carries the revision it was begun on, and one begun on a shape that has since changed is removed and not offered, on the finding's page and in the review queue (`answerDrafts.ts`). A draft kept before answers named a revision counts as given on revision 0.
- **`looked_at`** grows with each second look (`looked_at.grow`). What is added is the finding's shape then, an area as its edge, or its point when it has no shape, simplified to 5 m. It never shrinks, and is kept under 5,000 vertices by simplifying it further, up to 62.5 m.
- **The rule.** While `looked_at` is set, an edit must keep every looked-at point, and at least three-quarters (`LOOKED_AT_MIN_KEPT = 0.75`) of the length of the looked-at lines, within 250 m (`LOOKED_AT_MAX_MOVE_M`) of the new shape, or of the new point when there would be no shape. An area counts as all of its inside. Otherwise the edit is 422 `looked_at_moved`, which says how much would be left. Distances are measured on the national grid under what was looked at. A finding answered before `looked_at` existed is seeded from its stored shape first (`looked_at.seed`). A finding with no second look standing and no `looked_at` changes freely.
- **What was added.** After every change of shape and every second look, `added_since_looked_m` is the length of the shape, or of an area's edge, lying further than 250 m from `looked_at`, and `added_view` frames it (`looked_at.refresh_added`). Above 200 m (`confidence.NEW_PART_LOOK_M`) the finding gains the next step `look_at_new_part`, which never moves the tier. The step goes when a second look covers the new part or the part is cut away.
- **A keeper's own look.** A keeper who isn't the finder can't give a second look on the marking they keep: `review.check_may_answer` refuses them 422 `own_marking`, and the review queue leaves the marking out. An answer they gave before they took it on stands.
- **On the page.** The finding page says "N added since the last second look" with "Show the new part on the map", and lists the newest 50 changes in the timeline (`findings.SHAPE_CHANGES_SHOWN`), an extension with its length and "Show what was added" (`features/finding/shapeChanges.tsx`). While the keeper changes a shape, `looked_at` is drawn as a faint wide line under the path, and the panel says how much of it has to stay.

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
| `location.shape.suggestions` | The pending suggestions, newest first, each with its path, outline, kind, length, suggester and whether it is behind the shape, to a signed-in member | An empty list, the same whatever waits. A signed-out reader of an open finding gets an empty list too |
| `location.shape.changes[].suggested_by` | Who suggested a change the keeper accepted | Null: a change is `{"kind": "changed", "on": …}` |
| `keeper`, `keeping` | `keeper` to everyone who may open the page. `keeping`, the standing offer, only to the keeper, the person offered and moderators | `keeper` is sent, since a name says nothing of a place. `keeping` is null |
| `finding_shape_changes` | Never served whole. `path_before` goes only to admins, through `GET /mod/findings/{public_id}/shapes` | |

Downloads pass no suggestion. `shape.looked_at` goes only to someone `actions.edit` allows, the keeper, so a suggester never gets it.

Investigations hold back what is drawn within 1.5 km of a finding the reader doesn't see exactly, measured to its point or anywhere along its line or area (`sensitivity.hidden_near`, `PositionGuard.near`, [Decision 0030](decisions/0030-the-privacy-guard-measures-to-a-protected-finding-s-whole-shape-and-open-shapes-near-one-aren-t-generalised.md)). A finding a moderator has hidden takes no part in that rule: `hidden_near` and `near_hidden_clause` leave out any finding with `hidden_at` set. An investigation that holds or has held a hidden finding still holds back what is written beside it. An investigation's area that comes that near is shown as the whole 1 km squares it covers (`PositionGuard.area`). An open finding's shape is shown by its own level, whatever protected findings it passes near.

### Keeping and suggestions

A finding's finder is its credit and never changes. Its keeper, `findings.keeper_of(finding)`, is who may change it: `keeper_id`, or the finder while that is null. Everything else tied to the finder stays with the finder: withdrawing, seeing the finding while a moderator has hidden it, raising its level, exact downloads, and the finder's class in the assessment. A keeper who isn't the finder sees a hidden finding no more than any member does. Every route below finds the finding through `get_finding`, so anyone who can't see a hidden finding gets 404 `finding_not_found` before any other refusal.

**Handing on** is an offer and an acceptance (`services/keeping.py`).

| Route | Who may | Refused with |
|---|---|---|
| `PUT /findings/{public_id}/keeping/offer` `{handle}` | The keeper, and an admin when the marking is orphaned | 403 `not_keeper` for anyone else, whatever the keeper's standing; 409 `finding_hidden` (only those who see a hidden finding get this far); 404 `user_not_found`, with one body, for an unknown, deleted or banned handle; 422 `already_keeper` |
| `DELETE /findings/{public_id}/keeping/offer` | The person offered, the keeper, and an admin on an orphaned marking | 403 `not_offered` |
| `POST /findings/{public_id}/keeping/accept` | The person offered | 403 `not_offered`; 409 `finding_withdrawn`; 409 `finding_hidden` (only those who see a hidden finding get this far) |

One offer stands at a time and a new one replaces it. The person offered gets a `keeping_offered` notification with no actor, so an admin's offer reads as a keeper's, an offer made again to the same person while theirs stands sends nothing, and an offer made while the person offered has an unread notification of an offer of that finding sends nothing either, so taking an offer back and making it again can't pester them. Refusing an offer or taking it up marks that notification read, so a later offer is news. An offer to an account since deleted or banned reads as no offer. Taking it on makes them the keeper, or null when they are the finder, clears the offer, follows the finding for them, and records `keeper_changed`, which tells the followers and names the new keeper and no shape. `FindingDetail` gains `keeper`, and `keeping` (`{offered_to, offered_at}`) for the keeper, the person offered and moderators.

**Orphaned** means the keeper's account is deleted or banned. Deleting an account (`keeping.forget_keeping`) keeps the keeping with the account, clears offers on what it kept and to it, withdraws its pending suggestions, and gives each active admin one `keeper_gone` notification with `details.markings`, the count and nothing else. A ban keeps the keeping with the person, and clears every offer made to them (`findings.clear_offers_to`), as a deletion does, so to the keeper it reads as a refusal and nothing comes back with the ban lifted to say it was a ban. Lifting a ban clears every standing offer on the markings the person keeps (`findings.clear_offers_kept_by`), so an admin's offer made while they were away can't take a marking from them once they are back. `actions.hand_on` checks `check_keeper` and then, for an admin alone, that the marking is orphaned, so a member's refusal never says a keeper is banned.

### Suggestions

Anyone signed in but the keeper may suggest a change to a finding's shape, which the keeper accepts or declines (`services/suggestions.py`).

| Route | Answer | Refused with |
|---|---|---|
| `POST /findings/{public_id}/suggestions` `{path, path_revision}` | 201 `Suggestion` | 409 `finding_withdrawn`, 422 `own_marking` (the keeper), 422 `path_revision_required`, 409 `shape_changed`, the path limits, 422 `suggestion_unchanged`, 409 `too_many_suggestions`, 422 `outline_too_far`, 429 |
| `DELETE /findings/{public_id}/suggestions/{suggestion_id}` | 204 | 404 `suggestion_not_found`, 403 `not_suggester`, 409 `suggestion_decided` |
| `POST /findings/{public_id}/suggestions/{suggestion_id}/accept` `{shape_revision}` | 200 `FindingDetail` | 404 `suggestion_not_found`, 403 `not_keeper`, 409 `finding_withdrawn`, 409 `suggestion_decided`, 409 `shape_changed`, then what the change refuses, `looked_at_moved` (with its figure, since only the keeper accepts) and `outline_too_far` among them |
| `POST /findings/{public_id}/suggestions/{suggestion_id}/decline` | 200 `Suggestion` | 404 `suggestion_not_found`, 403 `not_keeper`, 409 `suggestion_decided` |

- **Making one.** The path names `path_revision`, which must be the shape's revision now. It is held to the limits and the anchor when it is made, and not to `looked_at`: any member may suggest, and even a yes or a no would let shapes sent one after another map the ground second looks covered. Making one never answers `looked_at_moved`. The keeper meets the rule on accepting. A person has one pending suggestion on a finding, and a new one withdraws the old. A finding holds at most `SUGGESTIONS_MAX_PENDING = 20`. Suggesting is limited to 30 an hour per member (`suggestions`). The suggester follows the finding, and the keeper gets `shape_suggested`, except while the keeper still has an unread one from that suggester about that finding, so replacing a suggestion again and again doesn't pester them. Accepting or declining marks that notification read, so the suggester's next suggestion is news.
- **Accepting.** Under the finding's lock, `suggestions.accept` checks the keeper, that the finding isn't withdrawn, that the suggestion is pending, and that `shape_revision` is the shape's revision now. It then calls `apply_shape_change` with the suggester as the one who made the change, held to the limits, the anchor and `looked_at` as they are now. A suggestion made on an older shape is accepted on the revision the keeper saw, and replaces the changes since. One that `looked_at` has outgrown since is refused with `looked_at_moved` and stays pending. The change row credits the suggester, the suggestion records the keeper as `decided_by` and the revision it made, and the suggester gets `suggestion_decided` with `details.accepted`.
- **Declining** sets the state and tells the suggester, with no reason: talk goes in the comments.
- **A banned or deleted suggester.** Their pending suggestions are left out of every list and count (`findings.suggestions_listed_clause`), and accepting, declining or withdrawing one is `suggestion_not_found`. A banned person's come back when the ban is lifted. A deleted account's are withdrawn when it goes, and the clause covers a deletion that crossed one.
- **A decided suggestion**, accepted, declined or withdrawn, is found only by its suggester and the keeper. Anyone else gets `suggestion_not_found`, so nobody learns the id was there.
- **A keeper's own suggestion.** Taking a marking on withdraws the new keeper's pending suggestion on it, and accepting a suggestion of one's own is 422 `own_marking`. Nobody is ever sent `suggestion_decided` for their own decision.

### Keeping and suggestions in the interface

The interface shows only what the API sends and offers only what the finding's `actions` allow. It never works out for itself who keeps a marking, whether it is orphaned, or what a suggester may see.

- **The byline.** The finding page reads "Found by X on date", and adds "Kept by Y" when `keeper` isn't the finder (`FindingHead.tsx`).
- **Suggesting.** Where `actions.suggest` allows, the page's "Its shape" section offers "Suggest a change", and so does the change tool's address to someone `actions.edit` refuses. It opens the drawing tool at `/mark/suggest/:publicId` (`SuggestPanel.tsx`) on the keeper's shape, under the editing key `suggest:<id>:<revision>`, so a suggestion and a change never share a path in the tool (`editingKey.ts`). The tool itself is the one "Change the shape" uses, and both panels take the shape up and ask about what is in the way through `savedShape.ts`. "Send the suggestion" posts the whole path with the revision it began on. Nothing of `looked_at` is drawn or said, and nothing is refused for it.
- **An unfinished suggestion** is held as an unfinished marking is. Close and Escape keep it in hand. While the tool isn't on it, it is drawn dashed with the "not saved" ring at its first point, which takes the tool back to it (`MarkLayer.tsx`). "Mark a finding", "Change the shape" and the suggestion tool for another finding each say what would be discarded and offer "Go back to it" before they take the tool. `unsavedInHand` in `markStore.ts` names it a `suggestion`, and the store forgets it when the person changes. Only Cancel throws it away.
- **Nothing unsent is lost without asking.** Whatever takes the tool asks first over anything unsent it would replace: "Mark a finding" over a change, a suggestion or a draft whose line changed, opening a draft over anything else, and the change and suggestion tools over anything not theirs (`inTheWayOfMarking` in `MarkPanel.tsx`, `inTheWayOf` in `savedShape.ts`). Arriving at either tool settles what "Mark a finding" set aside while it asked. When the server no longer lets the person send what they hold, because the finding was withdrawn or the keeping moved, the tool's page says it wasn't sent and offers to discard it, and to someone who now keeps the marking it offers "Change the shape with your drawing", which carries the drawing over as a change begun on the shape it was drawn on (`HeldHere.tsx`). A person with a suggestion waiting is told before they draw that sending another replaces it.
- **Suggested changes** (`SuggestedChanges.tsx`) lists the pending suggestions the server sends, with who and when, what each would do and "Made on an earlier shape" when it is behind. "Show on the map" draws one as a wide dashed band beneath the finding's own line (`dashedShape.ts`), so where they run together the finding's solid line shows down its middle, and where they part each shows alone. Accept and Decline appear only where `actions.decide_suggestions` allows. Accepting sends the revision on the page, and one made on an earlier shape is asked about first. A refused accept is said beside the suggestion in the server's words. A suggester's own suggestion has "Withdraw it", found by comparing its suggester's handle with the viewer's. When a card the person acted on goes, focus moves to the next card's first control, the one before, or the panel's title (`focusWhenGone.ts`), and answering an offer or taking one back does the same. An accept, a decline, a marking taken on and an admin's offer or removal ask again for the activity feed, and an admin's acts for the admins' list (`refreshLists.ts`). The timeline says "Suggested by X" on an accepted change.
- **Handing on** (`Keeping.tsx`). "Hand it on" is among the keeper's tools where `actions.hand_on` allows and `actions.remove_marking` doesn't. It asks for a handle. Every `user_not_found` is answered with one sentence, whatever the server's message. The standing offer, with "Take back the offer", is shown only where `hand_on` allows. The person offered is asked at the top of the page, with "Take it on" and "No thanks", only where `actions.take_keeping` allows. A moderator, who is sent `keeping`, is shown nothing of it.
- **For admins.** Where `actions.remove_marking` allows, which only ever an admin on an orphaned marking is, the page has a "No keeper" section with "Offer it to someone" and "Remove the marking". Moderation's "No keeper" section, `/mod/markings`, lists `GET /mod/markings/orphaned` and is offered to admins alone. A moderator who types its address is taken to their first section, and the list isn't asked for. The `keeper_gone` notification opens it. "Remove the marking" opens `/mod/markings/:publicId` (`RemoveMarkingPanel.tsx`), which asks for the earlier shapes only where `actions.remove_marking` allows, draws the chosen one the same way beneath the marking, says that the finding, its second looks and its evidence stay, and asks for a reason. Anyone else is told the page is for admins.

### Removing an orphaned marking

An admin takes back an orphaned marking's shape and never deletes the finding. Each route is 403 `admins_only` to anyone who isn't an admin, moderators included.

- `GET /mod/markings/orphaned` lists the findings whose keeper is deleted or banned, newest first, hidden and withdrawn ones included, each with its keeper and `keeper_gone` (`deleted` or `banned`).
- `GET /mod/findings/{public_id}/shapes` lists every change to the shape, newest first, 50 a page, each with its kind, date, who made it, `path_before` and whether that earlier shape can be put back. It is the one route that sends `path_before`.
- `PUT /mod/findings/{public_id}/marking` `{to_revision, shape_revision, reason}` puts the shape back to how it was at `to_revision`, or removes it when that is null. Refusals come in this order: `admins_only`, 409 `not_orphaned`, 409 `shape_changed`, 422 `no_such_revision`. It never answers `outline_too_far`.

The change goes through `apply_shape_change` with `held_to_looked_at=False`, because an earlier shape may lie outside ground looked at since. `looked_at` itself is kept and still measures what lies beyond it, so the finding is reassessed when that changed. The anchor follows `place_anchor` as for any change, with one exception: when the shape put back doesn't come within 1,000 m of a point the finder placed, the server places the point by that shape, as for a point nobody placed, and marks it `location_derived`. So a marking whose point a keeper dragged away can always be put back, after a removal too. The finding's events and a default title follow its square. The finding, its tier, its answers and its evidence stay. The change row names the admin, and the moderation log records `remove_marking` with the reason and `data = {"from_revision": n, "to_revision": m}`, never a shape, because `log_action` writes `data` to the host's log. Putting back the shape it has changes nothing and logs nothing. A removal records no `shape_extended` and reassesses with no actor, and the timeline names nobody for a change, so nothing a non-admin is sent, the page, the feed, the event stream or a notification, names the admin or says an admin acted. The finding still asks for a look at a new part where there is one.

### Drawing findings on the map

`map/findingsData.ts` turns each feature's `shape` into a line or area feature with its kind and its size (a line's length, an area's extent), beside the anchor marker every finding keeps. The marker is a fill in the tier colour inside a light ring and a dark outline (`findings-points` over `findings-points-casing`), as `docs/UI.md` sets out under "Markers". `map/overlayLayers.ts` draws the shapes under the markers, in the tier colour, at every zoom:

- A line is 2.5 px wide on a casing 1.5 px wider on each side in `--bg`, with round joins and caps. A known finding's line is 1.5 px.
- An area is its edge, 2 px on the same casing, over a fill at 4% opacity, so the terrain inside stays readable. A known finding's edge is 1.25 px.
- A ruled-out finding's line or edge is 1.5 px in `--state-ruled-out`, shown only with the ruled-out switch.
- An obscured finding is its dashed square and never a line.

The overlay asks for the findings in view at every zoom, sends the map's zoom with the box, and hides with the rest of the findings during a blind second look. Below zoom 9 it sends 9, the furthest out the server simplifies shapes for. The server answers at most a set number for one box and sets `next_cursor` when more matched. The map draws what came, isn't paged through the rest, and says on the map "Not every finding in view is drawn. Zoom in to see the rest." until an answer is whole again (`FindingsCutShortNotice` in `features/layers/MapNotices.tsx`).

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
- Only the keeper changes a marking. One whose keeper has left can be handed on, or have its shape taken back, only by an admin.
- An earlier version, serving beside this one during a deploy or gone back to, knows nothing of `keeper_id`: it lets the finder edit a marking they handed on, and doesn't let the keeper.
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
| Keeping, handing on, orphaned markings and an admin's removal | `backend/src/fieldclub/services/keeping.py` |
| Suggestions | `backend/src/fieldclub/services/suggestions.py` |
| The drawing tool, "Change the shape" and "Suggest a change" | `frontend/src/features/mark/` |
| The byline, suggested changes and handing on, on the finding page | `frontend/src/features/finding/FindingHead.tsx`, `SuggestedChanges.tsx`, `Keeping.tsx`, `Tools.tsx` |
| The admins' list of markings without a keeper, and a removal | `frontend/src/features/moderation/OrphanedMarkings.tsx`, `RemoveMarkingPanel.tsx` |
| Drawing and picking on the map | `frontend/src/map/findingsData.ts`, `overlayLayers.ts`, `findingHits.ts`, `frontend/src/features/explore/` |

**Deferred:**

| Part | Gap | Tracking |
|---|---|---|
| Undoing a saved change | `path_before` is kept but nothing offers it | Not planned. [Plan: lines and shapes, phase 2](../plans/lines-phase-2.md) leaves it out |

## Decisions behind this

- [Decision 0005 — Sensitive findings are generalised by viewer](decisions/0005-sensitive-findings-are-generalised-by-viewer.md)
- [Decision 0028 — A finding's shape is its tapped points under one fixed curve, within size caps, around an anchor that stays put](decisions/0028-a-finding-s-shape-is-its-tapped-points-under-one-fixed-curve-within-size-caps-around-an-anchor-that-stays-put.md)
- [Decision 0029 — Only the finder changes a shape, a change keeps the second looks, and most of what was looked at stays](decisions/0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md)
- [Decision 0030 — The privacy guard measures to a protected finding's whole shape, and open shapes near one aren't generalised](decisions/0030-the-privacy-guard-measures-to-a-protected-finding-s-whole-shape-and-open-shapes-near-one-aren-t-generalised.md)
- [Decision 0031 — A point's kind is switched by a control or a long press on its handle, and overlapping findings are picked by their edges](decisions/0031-a-point-s-kind-is-switched-by-a-control-or-a-long-press-on-its-handle-and-overlapping-findings-are-picked-by-their-edges.md)
- [Decision 0032 — Findings are open or protected, and the restricted level is dropped](decisions/0032-findings-are-open-or-protected-and-the-restricted-level-is-dropped.md)
- [Decision 0035 — A version reads a stored class it has no name for as not sure](decisions/0035-a-version-reads-a-stored-class-it-has-no-name-for-as-not-sure.md)
