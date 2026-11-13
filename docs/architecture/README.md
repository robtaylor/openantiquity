# Architecture

The current design of OpenAntiquity, by area. Each area is a **reference** doc: what the code does today, present tense, no rationale and no dead history. The *why* behind each choice lives in the [decision records](decisions/README.md), linked from the section it explains. The *not-yet-built* work lives in each doc's Implementation status section and in [plans](../plans/).

If you're an agent or a new reader, start here: this page maps every area to its current-state doc and the decisions behind it.

| Area | Reference | Decisions |
|------|-----------|-----------|
| Findings: where a finding is, its line or shape, who may change it, what each reader is sent, and how findings are drawn and picked | [findings.md](findings.md) | [0005](decisions/0005-sensitive-findings-are-generalised-by-viewer.md), [0028](decisions/0028-a-finding-s-shape-is-its-tapped-points-under-one-fixed-curve-within-size-caps-around-an-anchor-that-stays-put.md), [0029](decisions/0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md), [0030](decisions/0030-the-privacy-guard-measures-to-a-protected-finding-s-whole-shape-and-open-shapes-near-one-aren-t-generalised.md), [0031](decisions/0031-a-point-s-kind-is-switched-by-a-control-or-a-long-press-on-its-handle-and-overlapping-findings-are-picked-by-their-edges.md), [0034](decisions/0034-the-drawing-guidance-is-a-list-on-the-map-and-a-line-is-bent-by-dots-on-it-not-by-curve-handles.md), [0032](decisions/0032-findings-are-open-or-protected-and-the-restricted-level-is-dropped.md), [0035](decisions/0035-a-version-reads-a-stored-class-it-has-no-name-for-as-not-sure.md) |

Each area gets its doc when its code lands. The parts not yet drained into an area doc are in [the build contract](../ARCHITECTURE.md), and every decision is in the [decision index](decisions/README.md).
