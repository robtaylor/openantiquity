# Decision 0029 — Lines may run 600 km and closed shapes stop at 25 km across

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of findings drawn as lines as long as a Roman road and as closed shapes, facing a single span limit in degrees that would refuse any long line, and shapes that without a limit could swamp map views, "what's here" lists and the privacy guard, we chose a 25 km cap across a closed shape, a 600 km cap on a line's length, and caps of 5,000 tapped points and 50,000 derived vertices, all in metres or counts, to take the largest real features with room to spare, accepting that a long scribble inside the length cap is left to moderation.

## Context

When this was written `check_outline` refused an outline more than `OUTLINE_MAX_SPAN_DEG = 0.05` across, as `outline_too_big`, or more than `OUTLINE_MAX_GAP_DEG = 0.01` from the finding's point, as `outline_too_far`. `schemas/shapes.py` capped any shape a client sent at 2,000 positions and 200 parts. A limit in degrees means a different distance at each latitude, and 0.05° refuses any line longer than a few kilometres.

The owner wanted a line long enough for "all of Watling Street", and on 2026-11-12 asked why a size limit was needed at all. They were told what an unlimited shape would break:

- **Map views.** Every map view sends a `bbox`, and a shape matches every box it crosses. A finding covering a county would be fetched and drawn in every view of that county, and would take one of the 1,000 places a GeoJSON page holds (`GEOJSON_MAX_LIMIT`).
- **"What's here" queries.** Explore, the nearby lists and the record matching treat a finding as being where its shape is. An area of 2,000 km² is "here" everywhere inside it, so every list in that area would lead with it.
- **The privacy guard.** Decision 0023 holds back every investigation view and profile within 1.5 km of a finding the reader doesn't see exactly. Measured from the whole shape, a restricted scribble across a county would hold back every view there, which is a denial of service on other people's investigations.
- **Cost.** Every derived vertex is stored, simplified and sent. 50,000 vertices is about 800 KB of WKB for one finding.
- **What a second look means.** A reviewer answers "can you see a feature here" from one view. A 100 km enclosure can't be seen in any view, so an answer about it means nothing.

The owner replied: "Agreed we probably just shouldn't accept closed areas larger than 25km".

The caps were sized against known features. Stanwick's oppidum ramparts run to about 2.5 km and the Salisbury Plain field systems to several kilometres. Watling Street from Dover to Wroxeter is about 440 km, the Fosse Way about 370 km and Ermine Street about 320 km. These figures are inferences from general knowledge and weren't measured for this decision.

## Decision

1. A closed shape is refused above 25 km across, with 422 `shape_too_big`. Across means the larger of its east–west width at its middle latitude and its north–south height, in metres.
2. A line has no limit across. Its derived line is refused above 600 km of geodesic length, with 422 `line_too_long`. That leaves room for a drawn line that wanders a little and for a road followed into its continuation.
3. A path is refused above 5,000 tapped points, counted before the points are read, with 422 `path_too_many_points`. 5,000 points is about 300 KB of JSON, inside the 1 MB body limit, and allows Watling Street with a point at every bend and every 100 m along its curves.
4. A derived shape is refused above 50,000 vertices, with 422 `shape_too_complex`. Its message suggests corners on long straight stretches.
5. A shape must come within 1,000 m of a point the finder placed, or the request is refused with `outline_too_far`. This is the old 0.01° in metres, so it means the same at every latitude.
6. A closed shape's ring mustn't cross itself, or the request is refused with 422 `shape_crosses_itself`, because GEOS gives wrong answers on invalid polygons.
7. Two consecutive points, and the last and first of a closed path, must be at least 1e-6 degrees apart in the curve's projected plane, or the request is refused with 422 `points_too_close`, because the curve divides by that distance.
8. The limits are `SHAPE_MAX_ACROSS_M = 25_000`, `LINE_MAX_LENGTH_M = 600_000`, `SHAPE_MAX_GAP_M = 1_000`, `PATH_MAX_POINTS = 5_000` and `SHAPE_MAX_VERTICES = 50_000`, in `services/shapes.py`. They replace `OUTLINE_MAX_SPAN_DEG` and `OUTLINE_MAX_GAP_DEG`. The frontend reads them from `/meta` and keeps no copy of its own.

## Alternatives considered

- **No size limit** — rejected for the five reasons above. The owner agreed once they were set out.
- **One limit across for lines and closed shapes alike** — rejected because a road is long and narrow. A cap that takes Watling Street would let an enclosure cover a county.
- **Keeping the old limits in degrees** — rejected because 0.05° refuses any long line and a limit in degrees changes with latitude.
- **A density rule against a dense scribble inside the length cap** — not taken in the first version. Nothing showed it was needed, so it waits until it happens.

## Consequences

- The longest Roman roads and the largest single earthworks fit with a wide margin, if the inferred sizes above are right.
- A closed shape stays small enough to be seen in one view and to hold back only views near it.
- A length cap doesn't stop someone scribbling 600 km back and forth inside one parish. That is left to moderation, which can hide the finding, and to the rate limits on creating and editing findings.
- A 600 km line is still large. Its full derived shape can approach 50,000 vertices, so the map and the finding page are sent simplified copies, and only downloads carry it whole.
- Every limit has its own error code, and the interface has to explain each one.

## Walk-back options

- **If a real feature is refused** — raise the constant in `services/shapes.py`. The frontend follows through `/meta`.
- **If dense scribbles appear** — add a rule on vertices per square kilometre of a line's extent, and hide the ones already made.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "Limits, and why there are any".
- Decision 0023 — the 1.5 km privacy guard that an unlimited shape would have turned on other people's investigations.
- Decision 0028 — the path and the curve these limits apply to.
- Decision 0032 — measuring the privacy guard to the whole shape.
