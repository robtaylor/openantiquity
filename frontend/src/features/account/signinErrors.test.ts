import { describe, expect, it } from "vitest";
import { SIGNIN_ERROR_MESSAGES, signinErrorMessage } from "./signinErrors.js";

/**
 * Every code a provider sign-in can come back with: the ones docs/ARCHITECTURE.md
 * lists, and the others the backend's start and callback routes can raise
 * (`fieldclub.auth.failures`, `BannedError`, and `ConfigError` from a start).
 */
const CONTRACT_CODES = [
  "state_mismatch",
  "invalid_token",
  "provider_error",
  "cancelled",
  "banned",
  "account_deleted",
  "email_unavailable",
  "signin_failed",
  "provider_unavailable",
  "config_error",
];

describe("signinErrorMessage", () => {
  it.each(CONTRACT_CODES)("has its own words for %s", (code) => {
    expect(Object.hasOwn(SIGNIN_ERROR_MESSAGES, code)).toBe(true);
    const message = signinErrorMessage(code);
    expect(message.title.length).toBeGreaterThan(0);
    expect(message.body).toMatch(/\.$/);
  });

  it("gives a general message for a code it doesn't know, without repeating it", () => {
    const message = signinErrorMessage("<script>alert(1)</script>");
    expect(message.title).toBe("Signing in didn't work");
    expect(`${message.title} ${message.body}`).not.toContain("script");
  });

  it("isn't fooled by names every object has", () => {
    expect(signinErrorMessage("constructor").title).toBe("Signing in didn't work");
    expect(signinErrorMessage("__proto__").title).toBe("Signing in didn't work");
  });

  it("doesn't suggest trying again with an account that can't sign in", () => {
    expect(signinErrorMessage("banned").canRetry).toBe(false);
    expect(signinErrorMessage("account_deleted").canRetry).toBe(false);
    expect(signinErrorMessage("cancelled").canRetry).toBe(true);
  });
});
