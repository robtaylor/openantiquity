/**
 * The auth endpoints, and the account's query keys. Request and response
 * shapes come from the generated `schema.d.ts`.
 *
 * Nothing here caches or decides anything. `session.ts` owns what the app
 * believes about who is signed in.
 */

import { API_BASE, ApiError, apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";

export type Me = components["schemas"]["Me"];
export type MeUpdate = components["schemas"]["MeUpdate"];
export type Welcome = components["schemas"]["Welcome"];
export type AgeBand = components["schemas"]["AgeBand"];

/** Every query key the account feature uses. */
export const accountKeys = {
  me: ["auth", "me"] as const,
  handleSuggestion: ["auth", "handle-suggestion"] as const,
};

/** `GET /auth/me`: the signed-in person, or null when nobody is. */
export async function fetchMe(signal?: AbortSignal): Promise<Me | null> {
  try {
    // Signed out is an ordinary answer, so it isn't kept for a problem report.
    return await apiFetch<Me>("/auth/me", { signal, expected: [401] });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export function updateMe(changes: MeUpdate): Promise<Me> {
  return apiFetch<Me>("/auth/me", { method: "PATCH", body: changes });
}

export function deleteMe(): Promise<void> {
  return apiFetch<void>("/auth/me", { method: "DELETE" });
}

export function logout(): Promise<void> {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export function completeWelcome(body: Welcome): Promise<Me> {
  return apiFetch<Me>("/auth/welcome", { method: "POST", body });
}

export async function fetchHandleSuggestion(signal?: AbortSignal): Promise<string> {
  const body = await apiFetch<components["schemas"]["HandleSuggestion"]>("/auth/handle-suggestion", { signal });
  return body.handle;
}

/** `POST /auth/email/start`. The answer is the same whether or not the address has an account. */
export async function startEmailLink(email: string, next: string): Promise<void> {
  const body: components["schemas"]["EmailStart"] = { email, next };
  await apiFetch<components["schemas"]["EmailStarted"]>("/auth/email/start", { method: "POST", body });
}

export type EmailSignedIn = components["schemas"]["EmailSignedIn"];

/**
 * `POST /auth/email/verify`. `email` is the address the person typed, sent
 * only for a link opened in a browser that didn't ask for it; the server
 * signs in only when it is the link's own. Nothing fills it in for them.
 */
export function verifyEmailLink(token: string, email: string | null): Promise<EmailSignedIn> {
  const body: components["schemas"]["EmailVerify"] = email === null ? { token } : { token, email };
  return apiFetch<EmailSignedIn>("/auth/email/verify", { method: "POST", body });
}

/** `POST /auth/logout-everywhere`: ends every session of the signed-in person, this one too. */
export function logoutEverywhere(): Promise<void> {
  return apiFetch<void>("/auth/logout-everywhere", { method: "POST" });
}

/** `POST /auth/dev-login`. Exists only on a development or test server. */
export function devLogin(handle: string): Promise<Me> {
  const body: components["schemas"]["DevLogin"] = { handle };
  return apiFetch<Me>("/auth/dev-login", { method: "POST", body });
}

/**
 * Where a provider button goes: the server's start route, which redirects to
 * the provider and, after the callback, back to `next` on this site.
 */
export function providerStartUrl(providerId: string, next: string): string {
  const params = new URLSearchParams({ next });
  return `${API_BASE}/auth/oauth/${encodeURIComponent(providerId)}/start?${params.toString()}`;
}
