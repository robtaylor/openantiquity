"""Signing in: accounts, sessions, and the hooks for provider and email-link sign-in.

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

Adding a provider or the emailed link
-------------------------------------
Neither is built yet. `GET /auth/oauth/{provider}/start`, `GET` and `POST
/auth/oauth/{provider}/callback`, `POST /auth/email/start` and `POST
/auth/email/verify` belong in `fieldclub.api.auth`. Both ways of signing in end the
same way: find or create the `User`, then start a session.

1. Register the provider in `providers` so `/meta` advertises it once its
   settings are present: `register_provider(SignInProvider.GOOGLE, lambda
   settings: ...)`.
2. Verify the person. Providers run as a server-side authorisation-code flow
   with `state` and PKCE, and store an `auth_identities` row keyed on
   `(provider, subject)` with the email the provider asserted. Email links use
   the `magic_links` table with `tokens.new_token()` and `tokens.hash_token()`.
3. Find the user by identity. Failing that, link to the user who has the same
   email address, but only when the provider says the address is verified.
   An unverified address never links accounts. Failing that too, call
   `accounts.create_user(db, display_name=..., email=..., ...)`.
4. Refuse a user whose `deleted_at` is set. `sessions.create_session` asserts it.
5. Call `sessions.create_session(db, user, ...)`, commit, hand the token to
   `cookies.set_session_cookie(response, token)`, and redirect to the `next`
   path, which must be a relative path on this site.

A callback that a provider reaches with a cross-site POST can't carry the
client header. Pass its path to `ClientHeaderMiddleware(exempt=...)` in
`fieldclub.main` and rely on `state` there.

Rate-limit `POST /auth/email/start` per address with `fieldclub.ratelimit`.
"""
