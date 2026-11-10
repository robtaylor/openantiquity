# Decision 0008 — Second looks are blind

**Status:** Proposed.

**TL;DR.** In the context of asking members to check each other's findings, facing the tendency of people to see what they've been told is there, we chose to hide the finder's interpretation and everyone else's answers until a reviewer has given their own, to keep each second look independent, accepting that reviewers get less context and the queue is a little less inviting.

## Context

Nothing was built when this was written.

The confidence ladder counts how many other people can see a feature. That count means something only if each person looked for themselves. A card that says "ring ditch, four people agree" asks for a fifth agreement.

The research pass on 2026-11-10 found two pieces of evidence. The Chilterns LIDAR portal hid other volunteers' records to avoid herding. A 2014 study of collaborative tagging found that showing peers' tags only after a person had committed their own raised accuracy.

The same pass found that agreement among few volunteers is weak evidence. In the one field-checked study of volunteer LIDAR classification, precision was between 0.21 and 0.41 below seven agreeing people.

## Decision

1. The second-look queue shows a finding's place and the view its finder used. It doesn't show the title, the finder's feature class, the description, the tier, or any other person's answer.
2. The reviewer first answers whether they can see a feature there, and may say what they think it is.
3. After they answer, the finding is revealed in full, with how their answer compares.
4. A person who opens a finding's page directly sees its title and claim, because the page is where it's discussed. The other reviewers' individual answers stay hidden from them until they've answered.
5. The route to "probable" without a trusted reviewer needs a summed weight of 7.0 from people who can see it, not 5.0.
6. An answer is final once given. Only its note can change afterwards. An answer can be withdrawn, which stops it counting, but it can't be replaced by a different one.
7. Activity and notifications caused by a second look carry no name, so nobody who hasn't answered can work out who said what.

## Alternatives considered

- **Showing everything** was rejected because it turns a count of observers into a count of people who agreed with a suggestion.
- **Hiding only the vote counts** was rejected because the title and feature class lead the witness as strongly as the count does.
- **Blind everywhere**, including the finding page, was rejected because findings need a public page that can be linked, discussed and cited.
- **Letting people change an answer** was the first design. Review of the built code on 2026-11-10 showed that a reviewer could answer "unsure", read the reveal, and then change the answer to agree with the finder at full weight. Deleting the answer and giving a new one did the same. It was rejected because every answer given after the reveal is a prompted one.

## Consequences

- An agreeing second look is real evidence that the feature is visible without prompting.
- A disagreeing interpretation is useful too. If three reviewers independently say "field boundary" where the finder said "enclosure", that shows up at once.
- The queue can't use a finding's title to draw people in. It has to rely on the picture.
- The reveal after answering is a small reward of its own, and the natural place to show a tier change.
- Someone who answers by mistake can't correct it. They can withdraw the answer and add a note, and their second look no longer counts on that finding.
- A tier change set off by a second look appears in the activity feed with no name against it, which reads less warmly than "Ann's second look moved this to Seen".

## Walk-back options

- **If blind review cuts participation sharply**, show the feature class as a hint after ten seconds on a card, and measure whether agreement rates change.
- **If people skip the queue and answer from finding pages instead**, weight answers given from the page lower than answers given blind.

## Links

- Decision 0003 defines the tiers these answers feed.
