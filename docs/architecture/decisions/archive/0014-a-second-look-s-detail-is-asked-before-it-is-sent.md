# Decision 0014 — A second look's detail is asked before it is sent

**Status:** Superseded by Decision 0008 (2026-11-11), before acceptance: the API took the answer alone and its detail after it (point 8).

**Current architecture:** [ARCHITECTURE.md, "Frontend"](../../../ARCHITECTURE.md#frontend).

**TL;DR.** In the context of a second look, facing a conflict between UI.md's one-tap rule and an answer that is final once sent, we chose to ask the optional detail between choosing the answer and sending it, to keep what someone thinks a feature is unprompted, accepting a second press for every answer.

## Context

The second look on a finding's page and in the queue at `/review` shows three answer buttons. Choosing one shows the optional detail, which is what the person thinks the feature is and whether an ordinary explanation could account for it, and a button that sends the answer and the detail together.

`docs/UI.md` says, under "Behaviour", that nothing that contributes data needs more than one tap after the first, that second look answers are single buttons, and that optional detail appears after the answer, never before. A review of the built code on 2026-11-11 pointed out that choose-then-send is two presses.

Two rules in force at the time made one press impossible with the API as it was:

- Decision 0008 makes an answer final. `PUT /findings/{public_id}/observation` refuses a different answer with `answer_final`, and after that only the note can change.
- The class a reviewer gives counts as unprompted only if it is given before the reveal. The reveal comes back in the reply to the answer, so a class sent after it has seen the finder's class.

So if the first press sent the answer, the detail could only follow as a note, and the class would be lost as evidence.

## Decision

1. Choosing an answer doesn't send it. It shows the optional detail and a "Send" button that stays in sight at the foot of the panel.
2. The answer and its detail go in one request, and the reveal follows.
3. In the queue, where the keys 1, 2 and 3 answer, choosing by key moves focus to "Send", so the keyboard answers with a number and Enter.
4. UI.md's one-tap rule has this exception for second looks until the API takes the class as an addendum before the reveal is read.

## Alternatives considered

- **Sending on the first press and taking the detail afterwards** was rejected because the API refuses any change but the note once the answer is in, and a class given after the reveal is prompted.
- **Leaving the detail out** was rejected because a disagreeing class is useful evidence (Decision 0008, "Consequences"), and it is only worth anything when given blind.
- **Asking the detail before the answer** was rejected because UI.md puts optional detail after the answer, and asking it first makes the quick answer slower for everyone.

## Consequences

- Every second look takes two presses, three with a class. That is one more than UI.md asks for.
- The class someone gives is always given before they have seen the finder's.
- The interface rule and the built flow disagree in one place, and this record is where that is written down.

## Walk-back options

- **If the API takes a two-step answer**, so that the answer is sent at once and the class follows as an unprompted addendum that the server accepts until the reveal has been read, send on the first press and show the class question with the reveal held back until it is answered or skipped. Then write a record that supersedes this one.
- **If people abandon second looks between choosing and sending**, measure how often a chosen answer is never sent, and consider sending on the first press without the class.

## Links

- Decision 0008 — second looks are blind, and an answer is final.
- `docs/UI.md`, "Behaviour" — the one-tap rule this is an exception to.
