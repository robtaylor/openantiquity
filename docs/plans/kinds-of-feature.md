# Plan — Kinds under each class: a second level for what a finding looks like

**Status:** Proposed.

## Goal

Someone marking a finding first says what it looks like, as now, and can then say which kind: a bell barrow or a bowl barrow under "Round barrow", a house or a barn under "Building or ruin". The kind is optional and never needed to save. It is shown on the finding, can be filtered on, and helps match a finding to the heritage records that describe the same kind of thing. This builds on the classes of Decision 0005 and the reading rule the building class brought in.

## Prerequisites

- The "Building or ruin" class is live, with every reader able to meet a stored class it has no name for.
- The owner's answers to "Open questions for the owner".

## What exists (2026-11-13)

- **One level.** `FeatureClass` in `backend/src/fieldclub/vocab.py` has 21 flat values, soon 22 with `building`. `findings.feature_class` is text with a check built from the enumeration, and `community_class` holds what second looks made of it.
- **What a class decides.** The default protection of a new finding (`PROTECTED_CLASSES`), the words of a suggested title, the patterns that match a finding to heritage records (`services/records.py`), the filters on the map and lists, and the finder's class in the assessment (`services/confidence.py`).
- **Pairs that are parent and child already.** "Round barrow or mound" and "Long barrow"; "Road" and "Trackway or hollow way"; "Moat" and "Motte or castle earthwork". They are separate classes today, each with its own protection and matching.
- **The record offices' vocabulary.** Historic England publishes the FISH Thesaurus of Monument Types, the vocabulary the national and county records use for a monument's type. Read on 2026-11-13 from its published listing: it sorts terms into classes by function (Domestic, Civil, Defence, Religious ritual and funerary, Agriculture and subsistence, Monument by form, and eleven more), and gives each term broader and narrower terms. "Barrow" has "Long barrow" and "Round barrow" beneath it, and "Round barrow" has "Bell barrow" and "Disc barrow" among its own. In it "Civil" means public buildings such as a meeting hall, and a house is "Domestic". The page that offers it says it is free to use and names no licence.

## Decided by the owner

- A class for buildings is wanted now: "we also need to add 'civil construction' for 'what it looks like' - e.g. old houses." It is being added as "Building or ruin", ahead of this plan.
- The list should become a hierarchy: "I'm thinking 'what it looks like' may end up being more of a hierarchical structure, 'building' -> 'civil', 'Barrow'->'Long Barrow', 'Bell Barrow', 'Bowl Barrow'... etc".
- Kinds use the terms archaeology already has. On 2026-11-14, of this plan's questions: "we should err on the side of standard archeological terms". The terms for each class are being collated from the Thesaurus of Monument Types for him to choose from.

## Design

Proposed. Nothing here is built.

### Two levels, and the class stays

A finding keeps its class. A second, optional field, `feature_kind`, names a kind of that class. The class is what can be told from the LIDAR at a glance, and it goes on deciding protection, titles, filters and the assessment, so nothing that reads a class today changes. A kind is valid only under its own class, and changing the class clears a kind that doesn't belong to the new one.

Replacing the class with a tree was weighed and set aside. Every finding, filter and rule keyed by class would have to move at once, and a version from before the change couldn't read any finding saved after it. A field beside the class is one that an earlier version can leave alone.

Two levels and no more. The thesaurus goes deeper, and someone reading LIDAR rarely can.

### The list of kinds

Kinds live in `vocab.py` beside the classes, each with an id, a label in plain words, the class it belongs to, and the thesaurus term or terms it stands for. `/meta` serves each class with its kinds. A kind is added when someone needs it, starting with the classes the owner named.

A kind's label is the standard term, as the thesaurus has it, in ordinary capitals: "Bell barrow", "Farmhouse". Where the thesaurus has no term for something often seen in LIDAR, or two terms that can't be told apart from above, the plan for that class says so and the owner chooses. Each kind's hint says in plain words what tells it from its neighbours on the ground.

### Marking, and reading

- Choosing a class that has kinds brings up a second row, "Which kind?", with a chip for each and "Not sure which" chosen to begin with. Nothing is asked for a class with no kinds.
- The finding's page says the kind after the class: "Round barrow or mound, bell barrow".
- The map's and the lists' filters gain the kind under its class.
- A second look goes on asking for the class alone. Asking a second person for the kind is left for later, once kinds are in use.

### Matching to records

A heritage record's type usually is a thesaurus term. A kind that names its term lets the suggested records for a finding prefer records of that term over records that only share its class.

### Stored values and versions

A kind is a stored vocabulary, so a version must be able to meet a kind it has no name for. It reads one as no kind at all, and never writes over it unless the person chooses another, the same rule the building class brings in for classes.

## Workstreams

### WS1 — The field and the API

**Status:** Not started.

`findings.feature_kind`, the kinds in `vocab.py` and `/meta`, create and edit taking a kind and refusing one that isn't under the class, every place a finding is served carrying it, and the rule for a kind this version can't name.

**Exit criteria:** the backend suite passes, and a test stores a kind from a later version and shows every reader answers.

### WS2 — The interface

**Status:** Not started. Needs WS1.

The second row in the marking form and the edit form, the kind on the finding's page and in lists, and the filter.

**Exit criteria:** the frontend suites pass on both sizes, and the chooser fits a phone with the longest list of kinds.

### WS3 — Matching by kind

**Status:** Not started. Needs WS1.

Suggested records prefer a record whose type is the kind's term.

**Exit criteria:** a test shows a bell barrow finding ranked against a record of a bell barrow above one of a round barrow.

### WS4 — End-to-end checks and documents

**Status:** Not started.

A real-browser test of marking with a kind, the findings area doc, `DESIGN.md`, the changelog, and the decision record.

## Phase exit criteria

- [ ] A finding can be given a kind under its class, and saved without one.
- [ ] The kind is shown, filtered on and used in matching.
- [ ] Every finding and filter from before works unchanged.
- [ ] All workstreams shipped or deferred to a successor plan.

## Decisions to write

- **A finding's class has an optional kind beneath it, stored beside the class.** Two levels, why the class stays what the rules are keyed by, where the kinds' names and their terms come from, and what a version does with a kind it can't name.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| The lists grow until choosing is a chore | Medium | Kinds are optional, "Not sure which" is the default, and a kind is added only when asked for |
| Kinds invite confidence LIDAR can't give | Medium | The hint for a kind says what tells it apart on the ground, and second looks keep to the class |
| The thesaurus's terms can't be stored under its licence | Medium | Only the term's name is kept, for matching. See the open question |

## Left out

- More than two levels.
- A second look that asks for the kind.
- A kind that changes a finding's protection.
- Bringing in the whole thesaurus, or its scope notes.
- Merging today's paired classes, such as the two barrow classes, into one class with kinds. It could follow, and needs its own look at protection and at findings already saved.

## Open questions for the owner

1. **Which classes get kinds first, and which kinds?** To be chosen from the collated terms. Recommended to start with "Round barrow or mound" and "Building or ruin", then others as you meet the need.
2. **Is a building's kind what it was for, or what it is?** Answered in part on 2026-11-14: the standard terms. The thesaurus sorts buildings by what they were for (a house is "Domestic", a public building "Civil"), so a building's kinds will be terms of function such as "Farmhouse" or "Chapel", which LIDAR seldom shows by itself. Whether to offer those, or only the kinds that can be told apart from above, is still to choose once the terms are laid out.
3. **May we keep the thesaurus's term names?** Its publisher says it is free to use and names no licence. Every outside dataset here needs a `sources` row with its licence. Recommended: ask Historic England's data standards team to confirm the terms, and until they answer keep only the names of the few terms the kinds point to.
4. **Should a second look ask for the kind?** Recommended: not at first.

## References

- [Findings](../architecture/findings.md) — where a finding's class is used.
- [Decision 0005](../architecture/decisions/0005-sensitive-findings-are-generalised-by-viewer.md) — classes that are protected by default.
- [Decision 0033](../architecture/decisions/0033-a-version-passes-over-stored-values-a-later-one-added.md) — what a version does with a stored value it has no name for.
- [FISH terminologies](https://heritage-standards.org.uk/terminology/) — where the Thesaurus of Monument Types is offered.
