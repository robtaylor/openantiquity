# Decision 0004 — Field Club is non-commercial

**Status:** Proposed.

**TL;DR.** In the context of indexing every public archaeological dataset in the UK, facing several valuable sources licensed for non-commercial use only, we chose to run Field Club as a non-commercial service and admit those sources, to give contributors the fullest picture of what is already known, accepting that any later monetisation would first require removing them.

## Context

Nothing was built when this was written. No source had been ingested.

The research pass on 2026-11-10 tested about 300 sources. Four of its reports raised the same blocking unknown: whether the service was commercial. The answer decided whether a group of sources could be used at all. They were four Historic Environment Scotland LIDAR collections under the Non-Commercial Government Licence, including the 25 cm Antonine Wall survey, Beresford's Lost Villages and Open Domesday under CC BY-NC-SA, the Lincolnshire HER export, the newer EOX satellite mosaics, and records held under the Archaeology Data Service's default terms.

The project owner confirmed the same day that Field Club will be non-commercial.

## Decision

1. Field Club is a non-commercial service. It carries no advertising, sells no subscriptions or data, and charges nothing for access.
2. A source licensed for non-commercial use may be ingested and shown, provided it also passes that licence's other conditions. Non-commercial status doesn't override a term such as "must not be supplied to a third party".
3. Every source records a reuse class: `open`, `share_alike`, `non_commercial` or `link_only`.
4. A record keeps its source's licence and attribution wherever it's shown or exported. Bulk exports state the licence per record, so someone reusing an export can tell which records they may use commercially.
5. User contributions stay under an open licence that permits commercial reuse. The non-commercial limit applies to what Field Club ingests, not to what its contributors give.

## Alternatives considered

- **Ingest only sources that permit commercial reuse** and deep-link the rest. This was the default before the owner's answer, because it kept every option open. It was rejected because it left out the best available LIDAR for the Antonine Wall and the only national dataset of deserted medieval villages, for the sake of an option the owner doesn't want.
- **Decide source by source later** was rejected because four research strands were already blocked on the same question, and each connector author would have had to ask it again.

## Consequences

- More of what is already known appears on the map, which makes "is this already recorded?" easier to answer.
- Field Club can't later add advertising, paid tiers or data sales without first removing every `non_commercial` source. The reuse class makes that one query.
- Grants and donations need a check against each non-commercial licence's wording before they're accepted, because licences define "commercial" differently.
- Exports are less simple to reuse, because they mix licences.

## Walk-back options

- **If Field Club needs income** beyond grants and donations, disable the `non_commercial` sources, delete their rows, and write a decision that supersedes this one. Findings linked to those records keep the link as a plain reference.
- **If a publisher objects** to how its data is shown, set that source to `link_only`. The record pages become deep links and nothing else changes.

## Links

- Decision 0002 covers accounts, which is where the contribution licence is agreed.
