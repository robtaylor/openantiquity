# Decision 0002 — Accounts are required to save

**Status:** Proposed.

**TL;DR.** In the context of a public map where anyone can mark a possible site, facing a shared dataset that anonymous marks would clutter, we chose to let people explore and mark freely but require a provider sign-in to save, so that every stored contribution has an accountable owner, accepting that some people will leave at the sign-in step.

## Context

Nothing was built when this was written. The backend foundation was in progress and had been briefed to create guest accounts.

The first design gave every visitor a guest account the moment they contributed. The account was tied to the browser, and a guest's opinion counted for a quarter of a member's. The aim was the lowest possible barrier to a first contribution.

The project owner rejected this on 2026-11-10. Anonymous contributions would have filled the map with marks nobody stood behind, and regular users would have had to wade through them. Guests also complicated the confidence rules, and a browser-bound account lost its history when browser data was cleared.

## Decision

1. Reading is open to everyone. Every write needs a signed-in account. There is no guest role.
2. A signed-out visitor can still mark a finding, answer a second look and scan a square. The result is a draft in the browser's `localStorage` and is never sent to the server.
3. Pressing save opens the sign-in sheet. After sign-in the frontend submits the drafts as they were.
4. Sign-in uses providers only, with no passwords: Google, Apple, Microsoft and Facebook, plus OpenStreetMap, plus an emailed one-time link. A provider is offered only when its credentials are configured.
5. Providers run as a server-side authorisation-code flow, and the session is our own cookie.

## Alternatives considered

- **Guest accounts at reduced weight** was the first design, rejected by the owner for the reasons in Context.
- **A sign-up wall before any use** was rejected because the first five minutes decide whether someone comes back, and nobody could have tried marking before committing.
- **Email and password** was rejected because it adds reset flows and breach liability, and the providers already cover nearly everyone likely to use the tool.
- **A hosted identity service** such as Firebase Authentication was rejected because it puts a client SDK and a third-party sign-in domain in front of every user and makes local tests depend on an emulator. The server-side flow is a few hundred lines and can be tested offline.

## Consequences

- Every stored contribution has an accountable owner, and moderation can act on accounts.
- Role weights drop to three values: member, trusted and expert.
- Some people will leave at the sign-in step. Drafts reduce that loss, because by the time someone is asked to join they've already done the work and can see what they'd be saving.
- Each environment needs provider credentials. Sign in with Apple needs a paid Apple Developer account. Local development and end-to-end tests need a development-only login.

## Walk-back options

- **If too few people complete sign-in at the save step**, add providers or passkeys. Don't bring back anonymous writes.
- **If maintaining four provider integrations costs more than expected**, move to a hosted identity service behind the same session cookie. Nothing outside the auth module would change.

## Links

- Decision 0003 uses the role weights this leaves.
