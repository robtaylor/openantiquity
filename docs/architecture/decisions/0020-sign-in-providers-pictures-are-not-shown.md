# Decision 0020 — Sign-in providers' pictures are not shown

**Status:** Proposed.

**Current architecture:** [Accounts in the build contract](../../ARCHITECTURE.md#accounts).

**TL;DR.** In the context of a site whose privacy notice says it doesn't track people, facing every visitor's browser fetching members' profile pictures from Google's and Facebook's servers, we chose to show no picture from a sign-in provider at all, so that no page makes a request to a provider for someone who only reads it, accepting bylines with initials where a face was.

## Context

When this was written the callback stored the picture address a provider gave, Google's OpenID `picture` claim and Facebook's Graph picture, and every `PublicUser`, profile and moderation view carried it as `avatar_url`. The frontend drew it as an `<img>` wherever a person appeared: a finding's byline, comments, answers, investigation members, the moderation and photo queues and profiles. Apple, Microsoft and OpenStreetMap gave no picture. An account in the 16 to 17 band, or with no band yet, showed none (Decision 0009), and `PATCH /auth/me` could clear it.

The security review on 2026-11-11 pointed out that anyone opening a finding page, signed in or not, had their browser contact the provider's image servers, which saw their address, browser and the time. The set of pictures on a page was close to unique to that finding. The draft privacy notice listed map tiles and record publishers as the other services a browser talks to, and said providers were involved only at sign-in. Facebook's picture addresses are signed and expire, so stored ones would also have broken after a while.

The review offered two fixes: copy each picture once to our own storage and serve it from there, or show no provider picture.

## Decision

1. Nothing a provider says about a picture is read or stored. The Facebook profile call asks for `id`, `name` and `email` only.
2. No response carries a picture: `avatar_url` left `PublicUser`, `Me`, profiles and the moderation views, and `PATCH /auth/me` no longer takes it.
3. The column `users.avatar_url` stays until the first migration, is never written, and is emptied at each sign-in, so an address kept from before goes.
4. The page's `Content-Security-Policy` names no provider's image host, so a picture loaded from one by mistake fails where it can be seen.

## Alternatives considered

- **A copy of each picture served from our own storage** was rejected for now as the larger change for the same promise. It needs a fetch from an allow-list of provider hosts with the guards of `safe_fetch`, the photo pipeline's re-encoding, a new route and its tests, and clearing on every path that clears a picture today, for a picture that adds little to a handle.
- **Naming the providers' image servers in the privacy notice** was rejected as the only fix because the notice would then describe tracking by third parties that the site could simply not cause.

## Consequences

- A visitor's browser talks to no sign-in provider unless the visitor signs in.
- Decision 0009's rule that 16 and 17 year olds show no provider picture holds for everyone, so it can't be got wrong for them.
- People are shown by name or handle and an initial. Some members will miss their face.
- The interface draws initials only, and the privacy notice must say that no provider picture is shown or fetched.

## Walk-back options

- **If members ask for pictures**, copy a provider's picture to our own storage at sign-in, as the alternative above describes, offered as something each adult member chooses, and never for the 16 to 17 band.

## Links

- Decision 0009 — the 16 to 17 band shows no provider name or picture.
- Decision 0002 — sign-in is by provider.
