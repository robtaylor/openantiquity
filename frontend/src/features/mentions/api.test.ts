import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client.js";
import { retryOnceIfTransient } from "./api.js";

describe("retryOnceIfTransient", () => {
  it("asks once more after a failure that may pass, and no more", () => {
    const busy = new ApiError(503, "unavailable", "The server is busy.");
    expect(retryOnceIfTransient(0, busy)).toBe(true);
    expect(retryOnceIfTransient(1, busy)).toBe(false);
    expect(retryOnceIfTransient(0, new ApiError(0, "network", "Offline."))).toBe(true);
  });

  it("doesn't ask again after a refusal", () => {
    expect(retryOnceIfTransient(0, new ApiError(404, "finding_not_found", "Gone."))).toBe(false);
    expect(retryOnceIfTransient(0, new Error("boom"))).toBe(false);
  });
});
