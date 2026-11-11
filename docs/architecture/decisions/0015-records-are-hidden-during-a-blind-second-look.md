# Decision 0015 — Records are hidden during a blind second look

**Status:** Proposed.

**Current architecture:** [ARCHITECTURE.md, "Frontend"](../../ARCHITECTURE.md#frontend).

**TL;DR.** In the context of a blind second look, facing heritage records that can say what is at the spot, we chose to hold the records overlay off the map from the moment the queue opens until the card is answered, to keep the answer the reviewer's own, accepting that the reviewer can't check the records while answering.

## Context

The frontend holds the findings overlay back while `/review` is open (Decision 0008), so no marker or title at the spot gives the finder's claim away. When the second-look queue and the heritage records were joined on one map, the records stayed on: the area doc said "Heritage records stay on the map while a card is up."

A reviewer of the records work asked whether record markers should be hidden then too. A record at the spot can answer the question the card asks. A scheduled monument's square over a ring ditch says there is a barrow there before the reviewer has looked at the terrain, and the live sources' records can do the same.

## Decision

1. While `/review` is open and the current card hasn't been answered, the heritage records overlay, which draws the stored records, their counts and the live sources' records, is held off the map.
2. It is held through a list in the map store (`held`) that `overlayShown` reads, so the layers are hidden, no live source is asked, and the credits drop what isn't drawn. The person's own switch for the overlay, and the address that records it, are left as they were.
3. Once the answer's reveal is shown, or the queue is left, the records come back.

## Alternatives considered

- **Leave the records on** — rejected because a record at the spot answers the card's question, which is what Decision 0008 keeps the reviewer from seeing.
- **Turn the person's records switch off** — rejected because it would change their saved choice and the map's address, and leaving the queue wouldn't put it back.
- **Hide only the records near the card's place** — rejected because the reviewer pans and zooms freely, and a filter by distance would still show the records the reviewer pans to.

## Consequences

- A reviewer answers from the terrain alone, as the queue intends.
- A reviewer who wants the records to compare must answer first. The reveal brings them back.
- The map store gains a general way to hold an overlay off the map for a reason, which other features can use.

## Walk-back options

- **If reviewers say they need records while answering** — show them after a first answer of "not sure", or behind a deliberate switch, and say so in the card.

## Links

- Decision 0008 — second looks are blind.
