# Decision 0022 — Signed-out drafts belong to the tab that made them

**Status:** Proposed. Its fourth point is replaced by Decision 0024.

**Current architecture:** [Frontend in the build contract](../../ARCHITECTURE.md#frontend).

<!--
Status words and their meaning: see README.md § Status legend.

This record is immutable once accepted. Only the Status line and the
Current architecture link change. When the code moves, edit the area doc.
When the decision changes, write a new record and archive this one:
  uv run docs/scripts/doctool.py archive docs/architecture/decisions/NNNN-<name>.md

Write the body in past tense, as the state at decision time. While this is
Proposed, open the Context with one line on what the code does today.
-->

**TL;DR.** In the context of a browser that several people can share, facing signed-out drafts that were taken over and sent by whoever signed in there next, we chose to tie a signed-out draft to the tab that made it and to adopt it only after a sign-in that started and finished in that tab, so that a draft is only ever saved to the account of the person who made it, accepting that work done in another tab, or before an emailed link opened elsewhere, has to be claimed by hand.

## Context

When this was written the drafts store kept one signed-out "epoch" for the whole browser, in `localStorage` with the drafts. It changed only when someone signed in. Every time the account layer mounted with a signed-in person, `useDraftAutoSave` took over every signed-out draft of the current epoch and saved it without asking. The map, "Your marks" in the Explore panel and `/mark/:draftId` showed every finding draft in the browser whoever had made it, and the drafts bar treated every draft as the viewer's own while nobody was signed in.

The security review on 2026-11-11 proved three paths. Someone who marked a finding, or answered a second look and asked to see how it compared, on a shared computer and left without signing in had that work published by the next person to sign in there, under that person's name and licence. Their second look was sent as the next person's final answer, which spent that person's blind look on the finding and showed them everyone's answers (Decision 0008). The next person didn't even have to sign in: opening the site with a session already in the browser was enough. The same happened after login by forwarded link: a victim who confirmed an attacker's emailed link had their drafts saved into the attacker's account. And other people's drafts, exact positions included, were drawn and listed as the viewer's own.

Decision 0002 promised that someone could try marking before joining and that "after sign-in the frontend submits the drafts as they were", through a provider's round trip that reloads the page. Any rule had to keep that working in the same tab. The backend stage of the review added `asked_here` to the emailed link's answer, false when the link was opened in a browser that didn't ask for it.

## Decision

1. A signed-out draft is owned by a visit: a random value in the tab's `sessionStorage`. A reload and a provider's round trip keep it, and a new tab, window or browser doesn't. A visit ends whenever a signed-in person leaves the tab: a sign-out, a ban, the session running out, or another account.
2. Only the viewer's own drafts are drawn, listed, opened or saved as theirs: the signed-in account's, or, for someone signed out, this visit's made in the last 24 hours. Everything else in the browser is shown in the drafts bar by its kind alone, without what it says or where, to be discarded or, by someone signed in, claimed with "Save as mine".
3. Signed-out drafts become an account's only after a sign-in that started from the sign-in sheet in this tab and finished in this tab within 30 minutes, the way it started: a provider's sign-in coming back as a page load, an emailed link opened in this tab, or the development sign-in. A sign-in that arrives from another tab, a page that loads already signed in, and an emailed link that this browser didn't ask for (`asked_here` false) adopt nothing.
4. An adopted second look is held until the person says to send it, on its card or in the drafts bar, because an answer is final. Adopted findings and squares are saved without asking.
5. A link opened in a browser that didn't ask for it signs in only after the person types the link's address. The masked address is never shown, because a stranger's can be made to look like the person's own.

## Alternatives considered

- **Keeping the browser-wide epoch and starting a new one on sign-out** was rejected because work left by someone who never signed in would still be taken by the next person to sign in.
- **An age limit on adoption alone** was rejected because a shared computer is often used by the next person within minutes.
- **Carrying the visit through the emailed link's `next`** was considered so that a link opened in a new tab could adopt the drafts of the tab that asked. It was rejected as more machinery for little gain: the link proves only which browser asked for it, not who made the drafts in that tab, and the cost of the simpler rule is one press of "Save as mine".
- **Asking before saving every adopted draft** was rejected for findings and squares because Decision 0002's round trip would then end in a question every time, for work the person did a minute before in the same tab.

## Consequences

- A draft is saved only to the account of the person who made it in that tab, or of someone who said it was theirs.
- Someone who drafts in one tab and signs in from another, or opens an emailed link from their mail in a new tab, finds their drafts under "left in this browser by an earlier visit" and has to press "Save as mine".
- A second look made before signing in takes one more press after signing in.
- Two people at the same open tab are still one visit to the app: whoever sits down at a tab someone left open sees that person's drafts as their own. Nothing short of an account can tell them apart.
- Drafts stored by an earlier build under the browser-wide epoch belong to nobody until someone claims them.

## Walk-back options

- **If people lose drafts because they sign in from another tab**, offer the "Save as mine" question as soon as such drafts appear after a sign-in, rather than waiting for the drafts bar to be opened.
- **If the extra press on a second look puts people off answering**, send an adopted second look without asking when it was given within a few minutes of the sign-in starting, and keep the hold for older ones.

## Links

- Decision 0002 — accounts are required to save, and drafts carry work through sign-in.
- Decision 0008 — second looks are blind, and an answer is final.
