# Plan — Junior accounts tied to a parent's

**Status:** Proposed.

## Goal

A child of 13 to 15 can take part with an account of their own, made from a link their parent gives them and tied to the parent's account. The parent can see what the child does and can pause or close the account. Nothing else about who may join changes: someone under 16 with no invite is turned away as now.

## Prerequisites

- The readings in WS1, which decide whether this can be built as designed.
- A decision record replacing Decision 0009, accepted before any of it is switched on.

## What exists (2026-11-13)

- **The rule.** Decision 0009 set the youngest contributor at 16, against research that recommended adults only. It weighed 13 and turned it down for two reasons: rules the government had announced for spring 2027 draw their line at 16, and the tool encourages visits to sites.
- **In the code.** Sign-up asks for an age band, 16 to 17 or 18 and over, and keeps only the band. `FIELDCLUB_MIN_AGE` can be 16 to 18 and no lower. The welcome sheet turns away anyone younger and offers to remove the sign-in they just used. An account in the 16 to 17 band shows only its handle, and its field-visit guidance adds advice to go with an adult. Every uploaded photo waits for approval before others see it. There is no private messaging, and a private investigation has one member.
- **Reading needs no account.** Anyone can explore the map, open every finding and record, and try marking, which stays in their browser.
- **The law as the research read it on 2026-11-10** ([the spike](../architecture/decisions/spikes/platform-duties-and-age.md)). Under the Online Safety Act a child is anyone under 18, an age limit in the terms doesn't count as keeping children out, and a children's access assessment and risk assessment are owed whatever the limit. 13 is the age at which a child's own consent can be the lawful basis for an online service, with a power to raise it as far as 16. A ban on accounts for under-16s on social media was announced for spring 2027, and whether a site like this counts was undefined.
- **The 2027 rules, on 2026-11-13.** A search found no sign that the regulations had been laid. The House of Commons Library's briefing expected them in December 2026.
- **What the phone makers offer.** Apple's Declared Age Range API and Google's Play Age Signals API let a parent share a child's age range with an app installed from their stores. Two searches on 2026-11-13 found nothing of the kind for someone signing in to a website. OpenAntiquity is a website, so neither helps.
- **Assessments still owed.** The three Online Safety Act assessments in [Owner actions](owner-actions.md) aren't written yet.

## Decided by the owner

- The aim: "It would be nice if my 13 year old could use the site".
- Not to wait for the regulations: "it's quite likely they'll kick this proposal down the road".
- The shape: "I like your suggestion of child accounts linked to a parent's - Maybe we could do this by giving users a link they can use to invite their children."
- On 2026-11-13 the owner agreed the five recommendations this plan first put as questions, with one change:
  - 13 is the youngest.
  - A parent sees everything the junior account does and keeps, private notebooks included, and both are told so when the account is made.
  - Anyone may comment on a junior's finding, and the comment is held before it is shown. The change: "rather than a mederator doing the approvals, the parent could."
  - One adult holds at most four junior accounts.
  - At 16 either of them can move the account to the 16 to 17 band, which ends the tie.

## Design

Proposed. Nothing here is built.

### The invite

- An account in the 18 and over band makes an invite from its account page. Making one means saying, in words that are kept with the date, that they are the child's parent or guardian and answer for the account.
- The invite is a link holding a random token. It works once, stops working after two days, and can be cancelled. The parent hands it over themselves. The site never sends it to anyone.
- The child opens the link and signs in with a sign-in of their own. The account is made in a third band, 13 to 15, tied to the parent's. No date of birth is kept.
- Sign-up without an invite is as it is today. The third band can't be chosen there.
- An adult can hold at most four junior accounts. Moderators can see every tie.

### What the tie gives a parent

- A page listing their junior accounts and everything each has done and keeps, private notebooks included. Both are told so when the account is made.
- Two controls: pause the account, which stops it contributing, and close it.
- What others write to the child, to approve before anyone sees it (see below).
- No channel between them. Nothing is sent from one to the other through the site, which keeps Decision 0009's rule that there is no private messaging.

### What a junior account is held to

Everything an account of 16 or 17 is held to, and:

- Its profile lists nothing it has done to anyone but itself, its parent and moderators. A list of where someone has been marking can show where they live.
- A comment on its finding, a reply to its comment and a mention of it wait for the parent to approve them before anyone sees them. This is the part of the 2027 rules meant for services like this one: strangers contacting children.
- The parent is told when something is waiting. What the parent turns down stays unseen, and its writer is told it wasn't shown.
- Moderators keep their say. They can approve or remove anything that is waiting or was turned down, which is where a writer's complaint goes. A parent decides what reaches their child, not what the record of a finding may hold.
- The parent's own comments to their child don't wait.
- Second looks and evidence on a junior's finding don't pass through the parent. They carry no message, and a finding's assessment must not depend on its finder's family.
- Its field-visit guidance says to go only with its parent or guardian.
- At 16 either the junior or the parent can move the account to the 16 to 17 band, which ends the tie.

### What the invite proves

It records that an adult vouched for the child, and when. That serves the children's risk assessment and stands as the parent's agreement. It is not age verification: the adult's age and the child's are both as declared.

### When the rules change

If regulations bar under-16s from a service like this, junior accounts are paused that day and what they contributed stays. If they require age checks at 16, the walk-back in Decision 0009 applies to every account. The record that replaces 0009 keeps its review trigger.

## Workstreams

### WS1 — Read before building

**Status:** Not started.

Three things the research of 2026-11-10 didn't cover, each to be read first-hand and recorded in the spike or a new one:

- The Information Commissioner's code for online services likely to be used by children, and what it asks of a service that knowingly admits under-16s.
- Whether a parent's declaration made this way counts as the agreement the law asks for, and what would be needed below 13.
- Which sign-ins a 13 year old may hold. OpenStreetMap's and Google's own terms set ages, and a child's account is no use if neither lets them have one.

**Exit criteria:** each is written down with its source, and the design above is confirmed or changed.

### WS2 — The band, the invite and the tie

**Status:** Not started. Needs WS1.

The 13 to 15 band, the invite and its limits, the tie between the two accounts, pausing and closing, and what happens to a junior account when its parent's is closed or banned.

**Exit criteria:** the backend suite passes, including that no route lets the band be chosen without an invite and that a used, expired or cancelled invite makes nothing.

### WS3 — What a junior account is held to

**Status:** Not started. Needs WS2.

The profile's privacy, the holding of comments, replies and mentions for the parent, the moderators' say over what is held, and the guidance.

**Exit criteria:** tests show a stranger's comment on a junior's finding is seen by nobody but its writer, the parent and moderators until the parent or a moderator approves it, that a second look and evidence are not held, and that the profile lists nothing to anyone else.

### WS4 — The interface

**Status:** Not started. Needs WS2.

Making and cancelling an invite, the child's welcome, the parent's page with what is waiting for them, and the words that say plainly to both what the parent can see.

**Exit criteria:** the frontend suites pass on both sizes, and a real-browser test takes an invite from made to used.

### WS5 — The assessment, the decision and the documents

**Status:** Not started. The owner writes the assessment.

The children's risk assessment written to cover 13 to 15, the decision record that replaces 0009, the terms and the guide.

**Exit criteria:** the assessment is dated and kept, the decision is accepted, and only then is the band switched on.

## Phase exit criteria

- [ ] A parent can make an invite, and a child of 13 to 15 can join with it and no other way.
- [ ] A junior account is held to everything in "What a junior account is held to".
- [ ] The children's risk assessment covers 13 to 15.
- [ ] All workstreams shipped or deferred to a successor plan.

## Decisions to write

- **Contributors of 13 to 15 join by a parent's invite, tied to the parent's account.** It replaces Decision 0009, keeps its rule against private messaging and its review trigger, and says what the tie gives a parent, what a junior account is held to, and what the invite does and doesn't prove.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| An adult who isn't the parent uses an invite to tie themselves to a child | High | The link is handed over in person and never sent by the site, works once and for two days, an adult holds few, moderators see every tie, and the tie opens no private channel |
| The regulations bar under-16s from the site after children have joined | Medium | Junior accounts can be paused in one step, and their contributions stay |
| A stranger uses public comments to reach a child | High | Comments, replies and mentions aimed at a junior account wait for the parent |
| A parent turns down fair disagreement with their child's finding | Medium | Second looks and evidence aren't held, and a moderator can show what a parent turned down |
| A parent doesn't look, and comments wait for ever | Low | The writer is told it is waiting, and a moderator can approve it |
| An adult who isn't the parent approves their own way to the child | High | Everything they write to the child is public, moderators see every tie, and the tie itself is made only by a link handed over in person |
| A child gives a false age to join without an invite | Medium | As today: the band is declared. The assessment says so |

## Left out

- Accounts for children under 13.
- Checking anyone's age by document or by face.
- A parent acting as the child, or writing in the child's name.
- Messages between parent and child through the site.
- Groups: schools, clubs and Young Archaeologists' Club branches. They are a different tie and a later plan.

## Open questions for the owner

None. The five this plan first asked were answered on 2026-11-13 and are under "Decided by the owner". WS1 may raise more.

## References

- [Decision 0009](../architecture/decisions/0009-contributors-are-16-or-over-and-there-is-no-private-messaging.md) — the rule this would replace.
- [Platform duties and age](../architecture/decisions/spikes/platform-duties-and-age.md) — the law as read on 2026-11-10.
- [Owner actions](owner-actions.md) — the Online Safety Act assessments.
- [Proposals to ban social media for children](https://commonslibrary.parliament.uk/research-briefings/cbp-10468/) — the House of Commons Library's briefing.
