# Decision 0009 — Contributors are 16 or over and there is no private messaging

**Status:** Proposed.

**TL;DR.** In the context of a UK service where members post content and may visit remote sites, facing duties towards under-18s under the Online Safety Act and new under-16 rules due in 2027, we chose a minimum contributor age of 16 with an age band recorded at sign-up, and no private channel between members of any kind, to include older teenagers while keeping the service low-risk, accepting the children's risk assessment and safety duties that come with knowingly admitting 16 and 17 year olds.

## Context

Nothing was built when this was written.

The legal research on 2026-11-10 established four things. Under the Online Safety Act a child was anyone under 18, and every service in scope had to assess whether children could access it. Ofcom's guidance said an age limit in the terms of service didn't count as keeping children out. Only highly effective age assurance did. Rules announced on 15 June 2026 would bar under-16s from social media from spring 2027, give 16 and 17 year olds default-off features, and restrict strangers contacting children on other services. Whether a citizen-science map counted as social media hadn't been defined. The UK data-protection consent age was 13, with a new power to raise it as far as 16.

The research recommended limiting contributor accounts to adults. The project owner chose 16 instead on 2026-11-10, after weighing the risks. The Young Archaeologists' Club takes members up to 16, so 16 and 17 year olds are the group with nowhere to go before adult societies. The owner also ruled that Field Club should never have private messaging.

The product design at that point allowed private investigations with invited collaborators and shared notes. That was a private channel between members under another name.

## Decision

1. Reading is open to everyone. Contributing needs an account, and an account holder must be 16 or over.
2. Sign-up asks for an age band, 16 to 17 or 18 and over, and stores it. The minimum age is a setting.
3. An account in the 16 to 17 band shows only its handle, never a name or picture taken from the sign-in provider. Its field-visit guidance adds advice to go with an adult.
4. There is no private messaging. Every exchange between members is public and attached to a finding or an investigation.
5. A private investigation has exactly one member. Adding a collaborator requires making it public or unlisted, and moderators can read unlisted investigations.
6. An uploaded photo isn't shown to other people until a moderator or trusted member has approved it.
7. The minimum age is reviewed when the under-16 regulations are published.

## Alternatives considered

- **18 and over**, as the research recommended, was rejected by the owner because it shuts out 16 and 17 year olds for a smaller gain than it appears to offer. A self-declared 18 would not have removed the children's access assessment either.
- **13 and over**, the data-protection consent age, was rejected because the 2027 rules draw their line at 16 and because the tool encourages visits to sites.
- **Age verification at sign-up** was rejected as disproportionate before the regulations say whether Field Club is in their scope. A self-declared band is recorded so that default-off features can be applied later.
- **Private messaging with safeguards** was rejected outright. It's the feature that most raises assessed risk, and nothing in the product needs it, because discussion of a finding belongs on the finding.
- **Private investigations shared between collaborators** were rejected for the reason in Context.

## Consequences

- Older teenagers can take part.
- A children's risk assessment is required, and the children's safety duties apply.
- The age band lets later rules for 16 and 17 year olds be applied without asking everyone again.
- People can't collaborate on work they want to keep private. Arranging a joint site visit has to happen in public comments or somewhere else entirely.
- A self-declared age can be false.

## Walk-back options

- **If the regulations class Field Club as social media** and require age assurance at 16, add an assurance provider at sign-up or raise the minimum-age setting to 18.
- **If public comments are used to arrange meetings with 16 and 17 year olds**, restrict who can comment on findings made by accounts in that band.

## Links

- Decision 0002 makes every contributor an account, which is where the age band lives.
