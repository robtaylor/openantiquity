# Decision 0042 — Nothing drawn and not sent is replaced or thrown away without asking

**Status:** Proposed.

**Current architecture:** [UI.md, "The drawing tool"](../../UI.md#the-drawing-tool).

**TL;DR.** In the context of one drawing tool that marks a finding, changes a saved shape and suggests a change to someone else's, facing work lost in live use when something else took the map, we chose one rule for every way into the tool, that whatever would replace a drawing in hand asks first and that a refusal from the server never costs the drawing, accepting more questions put to the person.

## Context

When this was written the tool held one drawing at a time in the browser's memory: a new marking, a change to a saved shape, or a suggested change.

The owner lost work to it in live use more than once. A click on a record while drawing a long road closed the tool. "Mark a finding" jumped to an unfinished marking that a panel had hidden. Each was fixed where it was found: a marking in hand was kept in sight and asked about, and "Change the shape" asked before it discarded something unsaved.

Suggestions added a third kind of drawing and a review of them found the same fault in new places. A refusal because the shape had changed meanwhile replaced the drawing with the keeper's shape. Opening a draft, and "Mark a finding" over an unsaved change, replaced what was in hand. Back and Forward could leave the tool holding a drawing it wouldn't let anyone touch. Fixing each case as it was found hadn't closed the class.

## Decision

1. Whatever would take the map from a drawing in hand asks first: "Mark a finding", opening a draft, "Change the shape", "Suggest a change" and another finding's suggestion. The person goes back to what they had, or discards it and carries on.
2. Closing a panel or pressing Escape never discards a marking or a suggestion. It stays in hand, drawn on the map with a way back to it.
3. A refusal from the server never costs the drawing. When the shape changed while someone drew, the drawing and its undo history stay, the person is told it wasn't sent or saved, the shape as it now is shows beside it, and they choose to send theirs against it or to start again, which asks.
4. A drawing that can no longer be sent, because the finding was withdrawn or the person now keeps the marking, is said to be unsent and can be discarded or, where it fits, carried into a change.
5. The mark store's calls that replace what it holds are made only after the person chose to discard, after a save or a send, or when the person changes.
6. A test sets each kind of drawing against each way into the tool and checks that the person is asked.

## Alternatives considered

- **Go on fixing each case as it is met** — rejected because three rounds of it had left the same fault in new places each time something was added.
- **Hold several drawings at once** — rejected because the map would have to show which one a tap belongs to, and the tool's keyboard and phone controls assume one.
- **Keep drawings in the browser's storage, so nothing is ever lost** — rejected because a drawing of a protected finding would outlast a sign-out on a shared computer. A marking can already be kept as a draft by choice.
- **Refresh the drawing to the new shape on a refusal, as before** — rejected because it threw away minutes of drawing to show a shape the person hadn't asked to see.

## Consequences

- Someone who really does want to drop a drawing is asked once more than before.
- A drawing in hand is lost on a reload or when the browser closes. The browser's own "leave this page?" warns of it.
- A new way into the tool has to ask too, and the test in point 6 names each one.

## Walk-back options

- **If the questions wear on people** — offer "Undo" after a silent discard, which a discarded marking already has, in place of the question.
- **If drawings are still lost to reloads** — keep an open finding's drawing in the tab's own session storage, cleared on sign-out.

## Links

- [Decision 0031](0031-a-point-s-kind-is-switched-by-a-control-or-a-long-press-on-its-handle-and-overlapping-findings-are-picked-by-their-edges.md) — the tool's gestures.
- [Decision 0039](0039-other-people-s-changes-to-a-marking-are-suggestions-its-keeper-accepts-or-declines.md) — suggestions, the third kind of drawing.
