# Plan — Kinds under each class: a second level for what a finding looks like

**Status:** Proposed.

## Goal

Someone marking a finding first says what it looks like, as now, and can then say which kind: a bell barrow or a bowl barrow under "Round barrow", a house or a barn under "Building or ruin". The kind is optional and never needed to save. It is shown on the finding, can be filtered on, and helps match a finding to the heritage records that describe the same kind of thing. This builds on the classes of Decision 0005 and the reading rule the building class brought in.

## Prerequisites

- The "Building or ruin" class is live, with every reader able to meet a stored class it has no name for. Done on 2026-11-13.
- The owner's answers to "Open questions for the owner".

## What exists (2026-11-14)

- **One level.** `FeatureClass` in `backend/src/fieldclub/vocab.py` has 22 flat values. `findings.feature_class` is text with a check built from the enumeration, and `community_class` holds what second looks made of it.
- **What a class decides.** The default protection of a new finding (`PROTECTED_CLASSES`), the words of a suggested title, the patterns that match a finding to heritage records (`services/records.py`), the filters on the map and lists, and the finder's class in the assessment (`services/confidence.py`).
- **Pairs that are parent and child already.** "Round barrow or mound" and "Long barrow"; "Road" and "Trackway or hollow way"; "Moat" and "Motte or castle earthwork". They are separate classes today, each with its own protection and matching.
- **The record offices' vocabulary.** Historic England publishes the FISH Thesaurus of Monument Types, the vocabulary the national and county records use for a monument's type. Read on 2026-11-13 from its published listing: it sorts terms into classes by function (Domestic, Civil, Defence, Religious ritual and funerary, Agriculture and subsistence, Monument by form, and eleven more), and gives each term broader and narrower terms. "Barrow" has "Long barrow" and "Round barrow" beneath it, and "Round barrow" has "Bell barrow" and "Disc barrow" among its own. In it "Civil" means public buildings such as a meeting hall, and a house is "Domestic".
- **The terms, collated.** On 2026-11-14 version 29 of the thesaurus was set against the 22 classes: 456 candidate terms, each with its identifier and scope note, and a judgement of whether one-metre LIDAR could tell it from its neighbours. [Monument type terms for each feature class](../sources/monument-type-kinds.md) has the table, where the classes and the thesaurus part, and what differs in Scotland and Wales. The work-list beside it holds every candidate.
- **Its licence.** heritagedata.org gives the thesaurus the Open Government Licence v3.0 with a credit to Historic England, and an older file of it gives CC BY 3.0. Both allow the terms and their scope notes to be stored and shown with a credit. The pages that offer the download name no licence and say it is free to use.

## Decided by the owner

- A class for buildings is wanted now: "we also need to add 'civil construction' for 'what it looks like' - e.g. old houses." It is being added as "Building or ruin", ahead of this plan.
- The list should become a hierarchy: "I'm thinking 'what it looks like' may end up being more of a hierarchical structure, 'building' -> 'civil', 'Barrow'->'Long Barrow', 'Bell Barrow', 'Bowl Barrow'... etc".
- Kinds use the terms archaeology already has. On 2026-11-14, of this plan's questions: "we should err on the side of standard archeological terms". The terms for each class were collated from the Thesaurus of Monument Types the same day, and "Proposed kinds" below is drawn from them for him to choose from.

## Design

Proposed. Nothing here is built.

### Two levels, and the class stays

A finding keeps its class. A second, optional field, `feature_kind`, names a kind of that class. The class is what can be told from the LIDAR at a glance, and it goes on deciding protection, titles, filters and the assessment, so nothing that reads a class today changes. A kind is valid only under its own class, and changing the class clears a kind that doesn't belong to the new one.

Replacing the class with a tree was weighed and set aside. Every finding, filter and rule keyed by class would have to move at once, and a version from before the change couldn't read any finding saved after it. A field beside the class is one that an earlier version can leave alone.

Two levels and no more. The thesaurus goes deeper, and someone reading LIDAR rarely can.

### The list of kinds

Kinds live in `vocab.py` beside the classes, each with an id, a label, the class it belongs to, and the identifier of the thesaurus term it stands for. `/meta` serves each class with its kinds. Which classes carry kinds in the first release is an open question, and a kind can be added afterwards when someone needs it.

A kind's label is the standard term, as the thesaurus has it, in ordinary capitals: "Bell barrow", "Farmhouse". Where the thesaurus has no term for something often seen in LIDAR, or two terms that can't be told apart from above, the plan for that class says so and the owner chooses. Each kind's hint says in plain words what tells it from its neighbours on the ground.

### Proposed kinds

Proposed on 2026-11-14 for the owner to accept, prune or add to. Nothing here is decided. There are 95 kinds over 18 classes, and four classes have none.

The list was drawn up by four rules:

- **A preferred term of the English thesaurus, version 29.** Each was checked against its tables. The label is the term in ordinary capitals.
- **One that LIDAR could tell from its neighbours.** By the judgement recorded in the collation, which wasn't tested against data. A few that it could tell only sometimes are in because they are the usual name for something often met: Causewayed enclosure, Shrunken village, Drove road, Park pale, Wood bank, Fishpond, Mill pond, Lime kiln, Practice trench, Stone circle and Prospect mound.
- **A term may sit under a class the thesaurus doesn't file it under.** The classes group what looks alike from above, and the thesaurus groups by what a thing was for. Such a term is marked †. A kind keeps its own thesaurus identifier wherever it sits, so matching to records isn't affected.
- **A term belongs to one class.** Water meadow is under Field system and not also under Pond, and Bell pit under Pit or quarry and not also under Industrial.

| Class | Proposed kinds | Note |
|---|---|---|
| Enclosure | Banjo enclosure, Causewayed enclosure, Curvilinear enclosure, Rectilinear enclosure, Ring enclosure | The thesaurus has three near-alike terms for a straight-sided plan: rectangular, rectilinear and subrectangular. One is offered. |
| Hillfort | Univallate hillfort, Bivallate hillfort, Multivallate hillfort, Multiple enclosure fort, Promontory fort† |  |
| Round barrow or mound | Bowl barrow, Bell barrow, Disc barrow, Saucer barrow, Pond barrow†, Ring barrow† | A pond barrow and a ring barrow are filed beside the round barrow, under Barrow. |
| Long barrow | Oval barrow, Bank barrow† |  |
| Hut circle | None | The thesaurus gives Hut circle no narrower terms. |
| Settlement earthworks | Deserted settlement, Shrunken village†, Linear settlement, Scooped settlement, Hut circle settlement, Toft† |  |
| Building or ruin | House†, Farmhouse†, Farmstead†, Longhouse†, Barn†, Field barn†, Chapel†, Church†, Watermill†, Windmill† | Terms of what a building was for. An old map or a visit usually settles it, and LIDAR alone seldom does. See the open questions. |
| Field system | Celtic field system, Coaxial field system, Aggregate field system, Strip lynchet†, Cultivation terrace†, Cairnfield†, Water meadow |  |
| Ridge and furrow | Broad ridge and furrow, Narrow ridge and furrow, Cord rig†, Lazy beds†, Plough headland† |  |
| Linear bank or ditch | Cross dyke†, Multiple ditch system, Boundary bank†, Boundary ditch†, Park pale†, Wood bank† |  |
| Trackway or hollow way | Hollow way†, Causeway†, Drove road† | The thesaurus files Hollow way beside Trackway, under Road. |
| Road | None | A Roman road is Road with a period, and the thesaurus keeps period apart from type. Most of Road's narrower terms need documents to tell apart, and Hollow way and Drove road are offered under Trackway. |
| Moat | None | The English thesaurus gives Moat no narrower terms. |
| Motte or castle earthwork | Motte, Motte and bailey†, Ringwork†, Ringwork and bailey† | All four are filed under Castle. |
| Platform | House platform, Hut platform, Charcoal burning platform† |  |
| Pond or water management | Dewpond, Decoy pond, Fishpond, Mill pond, Leat†, Dam† |  |
| Pit or quarry | Quarry†, Bell pit†, Shaft mound†, Spoil heap† |  |
| Industrial | Hush†, Streamwork†, Peat cutting†, Tramway†, Inclined plane†, Lime kiln† |  |
| Military | Temporary camp†, Fortlet†, Sconce†, Practice trench†, Anti tank ditch†, Anti aircraft battery†, Firing range†, Bomb crater† | A Roman marching camp is a Temporary camp in the thesaurus. |
| Ritual monument | Henge, Cursus, Stone circle, Avenue (landscape feature)†, Hill figure | The barrows keep their own classes. |
| Garden earthworks | Terraced garden, Sunken garden, Ha ha†, Prospect mound† |  |
| Not sure | None | Someone who isn't sure of the class isn't asked for a kind. |

What the proposal can't give. The thesaurus has no term for a ruin, so a ruined building has a kind only by what it was. "Roman road", "Agger" and "Moated site" aren't preferred terms in the English thesaurus. The barrow kinds are English: the Scottish and Welsh thesauri give Round barrow no narrower terms, so a kind chosen for a barrow there matches nothing finer than Round barrow in their records.

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

`findings.feature_kind`, the kinds in `vocab.py` and `/meta`, create and edit taking a kind and refusing one that isn't under the class, every place a finding is served carrying it, and the rule for a kind this version can't name. A `sources` row for the thesaurus with its licence and the credit to Historic England, shown wherever the app credits its sources.

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
| A kind from the English thesaurus matches nothing in Scottish and Welsh records | Low | The kind is still shown and filtered on everywhere. Matching falls back to the class, as it does today |
| A hint we write for a kind is wrong about what tells it apart | Medium | Each hint is written from the thesaurus's scope note, and the owner reads the hints before they go live |

## Left out

- More than two levels.
- A second look that asks for the kind.
- A kind that changes a finding's protection.
- Bringing in the whole thesaurus, or showing its scope notes. The licence allows it. The scope notes are written for a cataloguer, and a hint for someone reading LIDAR says what to look for.
- A period for a finding, such as Roman or medieval. The thesaurus keeps period apart from type, which is why "Roman road" isn't a kind.
- Merging today's paired classes, such as the two barrow classes, into one class with kinds. It could follow, and needs its own look at protection and at findings already saved.

## Open questions for the owner

1. **Are the proposed kinds the right ones?** The table under "Proposed kinds" is the proposal. Strike any kind or class, or name one that is missing. The full list of candidates for each class is in [the collation](../sources/monument-type-kinds.md). Recommended: as tabled.
2. **All the classes at once, or a few first?** Each kind needs a hint written for it, 95 in all. Recommended: all 18 classes in one release. Kinds are optional and the longest list is ten, so the cost is the hints, and they can be written from the scope notes in one pass for you to read.
3. **May a kind sit under a class the thesaurus files it beside?** Pond barrow under "Round barrow or mound", Hollow way under "Trackway or hollow way", Motte and bailey under "Motte or castle earthwork". Recommended: yes. The label and the identifier are still the thesaurus's own.
4. **Do buildings get kinds by what they were for?** The thesaurus has no other kind of term for a building, so the proposal is House, Farmhouse, Farmstead, Longhouse, Barn, Field barn, Chapel, Church, Watermill and Windmill. LIDAR alone seldom shows which, and an old map's label or a visit usually does. Recommended: yes, with a hint that says so. The other choice is no kinds for buildings.
5. **Should a second look ask for the kind?** Recommended: not at first.

Answered since the plan was written: the thesaurus's terms may be kept. Its licence is in "What exists".

## References

- [Findings](../architecture/findings.md) — where a finding's class is used.
- [Decision 0005](../architecture/decisions/0005-sensitive-findings-are-generalised-by-viewer.md) — classes that are protected by default.
- [Decision 0033](../architecture/decisions/0033-a-version-passes-over-stored-values-a-later-one-added.md) — what a version does with a stored value it has no name for.
- [Monument type terms for each feature class](../sources/monument-type-kinds.md) — the collated terms, the licence as read, and where the classes and the thesaurus part.
- [FISH terminologies](https://heritage-standards.org.uk/terminology/) — where the Thesaurus of Monument Types is offered.
