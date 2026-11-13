# Decision 0035 — A version reads a stored class it has no name for as not sure

**Status:** Proposed.

**Current architecture:** [ARCHITECTURE.md, "Conventions"](../../ARCHITECTURE.md#conventions).

**TL;DR.** In the context of a live site where two versions serve side by side during a deploy and a rollback leaves the later version's rows behind, facing a version that answered 500 wherever it met a feature class a later version had stored, we chose to have every version read such a class as `unknown`, the class the interface calls "Not sure", and never write "Not sure" over it unless someone chooses another class, so that a new class can be added in a deploy of its own, accepting that an earlier version shows and assesses such a finding as unclassified until it is back on a version that knows the class.

## Context

When this was written the code read a stored feature class strictly. A finding's `feature_class`, its `community_class` and a second look's `feature_class` went through `FeatureClass(...)` in about a dozen places: the finding's page, the list and the map's GeoJSON, the feed, the mentions, the review queue and the reveal, the downloads, the suggested records, a record's linked findings, the default level of protection and the confidence engine. A stored assessment named classes too, in its class support, its leading class, its community class and each second look.

A deploy ran `fieldclub-release` once and then replaced the web machines one at a time, so for some minutes the earlier version served beside the later one. Going back to an earlier image left every row the later one had written. Decision 0033 had met the same problem for activity kinds and next steps, and said in its third point that a new value in any other stored vocabulary needed a deploy of its own first.

The schema step that `fieldclub-release` ran made a vocabulary's check again whenever the values stored in it differed from the enumeration's. So an earlier image gone back to would have made the class checks again without the later version's class. The narrower check was committed before the rows were checked against it. With a finding of the new class stored, that check failed and so did the release, and the narrower check stayed, refusing every save of the new class and every change to a row that held it. An independent review of this change found that on 2026-11-13, before either part was deployed.

On 2026-11-13 the owner asked for a class for buildings and ruins. Had it been deployed over the version then live, a single finding saved with it would have made that version answer 500 on the public map, the list, the feed and the finding's own page.

## Decision

1. One function, `vocab.stored_class`, says what a stored class is to this version: itself, or `unknown` for one it has no name for. Every reader of a stored class goes through it, and none calls `FeatureClass(...)` on a stored value. Every response field that carries a class has the type `ShownClass`, which reads through the same function, so a row handed to a response model as it is stored can't be read strictly either. Two tests hold the code to this: one fails on any `FeatureClass(...)` call outside the reader and the two places that take a class a person sent, and one gives every response model's class field a class from a later version.
2. A stored assessment reads a class it has no name for as `unknown`, and leaves out the support given to it, because "Not sure" is never given support.
3. An edit or a note on a second look is compared with the class this version showed, not the one stored. "Not sure" sent back for a class this version can't name changes nothing, and any other class is saved.
4. A class this version can't name has the default level of `unknown` when one is needed, and never changes a level a finding already has.
5. The interface shows a class id its `/meta` doesn't list as "Not sure" with its icon, so a page left open across a deploy doesn't break either.
6. The schema step never takes a value out of a vocabulary's check unless this version names it as dropped (`_DROPPED_VALUES` in `db.py`). A check that admits a value this version has no name for is left as it is, and keeps that value when it is made again for a value of this version's own. This holds for every stored vocabulary, not only classes.
7. This is deployed by itself, ahead of the first version that adds a class.

## Alternatives considered

- **Passing over a finding of an unknown class, as an unknown activity kind is passed over** — rejected because a finding can't be left out of its own page, and a finding missing from the map and the lists while its finder could still open it by link would look lost.
- **Raising `ASSESSMENT_VERSION`** — rejected because it covers only the stored assessment, and the finding's own columns would still answer 500.
- **Showing the stored id as it is** — rejected because the response models are typed by the class enumeration, and the interface would show an id like `building` that no list explains.
- **Adding the class in one deploy and accepting the 500s** — rejected because one finding took down the public map and the feed for every reader, signed in or not.

## Consequences

- A class can be added in a deploy of its own once every machine reads unknown classes. Going back from it is safe as far as the first version that holds this decision, and no further.
- An earlier version shows such a finding as "Not sure", and its downloads give it the monument type `SITE`. A filter on "Not sure" lists it.
- When an earlier version reassesses such a finding it counts the class as "Not sure", which gives it no class support, and stores `community_class` as that assessment says. A finding that had reached a tier on the strength of that class can drop a tier, and its followers are told. The later version puts the support, the community's class and the tier back the next time it assesses the finding, and the followers are told again.
- On an earlier version nobody can choose "Not sure" for such a finding: it is what that version already shows, so sending it changes nothing.
- While machines are swapped, a page loaded from the later version can send the new class to a machine on the earlier one, which refuses it as not valid. Saving again once the swap is over works.
- A value taken out of a vocabulary stays in its check until a version names it as dropped.
- A finding's title that is still the suggested one doesn't follow a move made on an earlier version, because that version can't tell the title was suggested.
- The class itself is never written over: only a person choosing another class replaces it.

## Walk-back options

- **If classes start to be added often** — keep this as it is, and add each in two deploys as now.
- **If a later class needs to be told apart on an earlier version** — send the stored id beside the class this version reads, as a field of its own.

## Links

- Decision 0033 — a version passes over stored values a later one added, for activity kinds and next steps.
- Decision 0018 — hosting on Fly, where the release command and the rolling swap come from.
