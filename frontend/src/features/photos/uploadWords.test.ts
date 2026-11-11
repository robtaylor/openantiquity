import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client.js";
import { uploadProblem } from "./uploadWords.js";

describe("why a photo didn't upload", () => {
  it.each([
    ["image_too_large", 413, /over 15 MB/, false],
    ["not_an_image", 422, /isn't a picture we can read/, false],
    ["unsupported_image", 422, /can't take that kind of picture/, false],
    ["image_too_many_pixels", 422, /very large for the size/, false],
    ["media_blocked", 409, /refused before/, false],
    ["uploads_busy", 503, /busy with other photos/, true],
  ])("says what %s means, and whether to try again", (code, status, message, retry) => {
    const problem = uploadProblem(new ApiError(status, code, "server words"));
    expect(problem.message).toMatch(message);
    expect(problem.retry).toBe(retry);
  });

  it("offers a retry after the network or the server let it down, but not after a refusal it doesn't know", () => {
    expect(uploadProblem(new ApiError(0, "network_error", "x")).retry).toBe(true);
    expect(uploadProblem(new ApiError(502, "http_502", "x")).retry).toBe(true);
    expect(uploadProblem(new ApiError(400, "odd", "The server's own words."))).toEqual({
      message: "The server's own words.",
      retry: false,
    });
  });
});
