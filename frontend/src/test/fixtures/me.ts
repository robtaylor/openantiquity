import type { Me } from "../../features/account/api.js";

/**
 * A signed-in person as `GET /auth/me` returns them: through the welcome step
 * unless `overrides` say otherwise. For example `meFixture({ needs_welcome:
 * true, age_band: null, terms_accepted_at: null })` is someone who has just
 * signed in for the first time.
 */
export function meFixture(overrides: Partial<Me> = {}): Me {
  return {
    handle: "QuietBarrow42",
    display_name: "Ada Lovelace",
    role: "member",
    avatar_url: null,
    email: "ada@example.org",
    email_verified: true,
    reputation: 0,
    bio: null,
    settings: {},
    created_at: "2026-11-01T10:00:00Z",
    age_band: "18_plus",
    terms_accepted_at: "2026-11-01T10:05:00Z",
    needs_welcome: false,
    ...overrides,
  };
}

/** Someone signed in for the first time, who still owes the welcome step. */
export function newcomerFixture(overrides: Partial<Me> = {}): Me {
  return meFixture({
    needs_welcome: true,
    age_band: null,
    terms_accepted_at: null,
    display_name: "QuietBarrow42",
    ...overrides,
  });
}
