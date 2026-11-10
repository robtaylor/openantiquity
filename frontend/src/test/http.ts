/** A JSON response, as `fetch` would resolve with. */
export function json(body: unknown, status = 200, statusText = ""): Response {
  return new Response(JSON.stringify(body), { status, statusText, headers: { "Content-Type": "application/json" } });
}

/** The path of a request, such as "/api/v1/meta", without its query. */
export function requestPath(input: unknown): string {
  const url = typeof input === "string" ? input : input instanceof Request ? input.url : String(input);
  return new URL(url, "http://localhost").pathname;
}
