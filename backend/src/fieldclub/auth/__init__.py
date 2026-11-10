"""Signing in: accounts, sessions, provider sign-in and the emailed link.

Every write needs a session, and every session belongs to a real account.
There are no guest accounts (Decision 0002).

How the pieces fit:

- `tokens` makes opaque random tokens and hashes them. Only hashes are stored.
- `sessions` creates, resolves and revokes browser sessions.
- `cookies` puts a session token in the `fieldclub_session` cookie and takes it out.
- `handles` generates handles and holds the rules for handles and display names.
- `accounts` creates an account at first sign-in, finds or makes the test
  users behind `POST /auth/dev-login`, and deletes an account.
- `profile` changes a user's own details.
- `onboarding` records the welcome sheet (age band and contributor terms) and
  decides who may contribute (Decision 0009).
- `deps` holds the FastAPI dependencies: `current_user_optional`,
  `current_user`, `current_contributor` and `require_role`.
- `csrf` is the middleware that requires `X-FieldClub-Client: web` on every
  request that changes data.
- `providers` lists the sign-in methods that are switched on, for `/meta`.
- `flow` carries one provider sign-in's state, nonce and PKCE verifier in a
  signed, short-lived cookie bound to the browser that started it.
- `oidc` is the one OpenID Connect client: discovery, cached and rotating
  key sets, and identity-token checks.
- `oauth` holds the provider adapters (Google, Microsoft, Apple,
  OpenStreetMap, Facebook) and their quirks.
- `signin` finds, links or creates the account behind a sign-in and starts
  its session. Every way of signing in ends there.
- `email_link` and `mailer` are the emailed one-time link.
- `redirects` keeps `next` to a relative path on this site.
- `failures` names the short codes a failed sign-in reports.

The routes are in `fieldclub.api.auth`. Provider callbacks always answer
with a redirect to the app, carrying `?signin_error=<code>` on failure.
Apple's callback arrives as a cross-site POST without the client header, so
`fieldclub.main` exempts exactly that path, for POST only, and the flow's
`state` protects it instead.
"""
