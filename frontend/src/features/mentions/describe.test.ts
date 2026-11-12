import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client.js";
import {
  mentionFailure,
  mentionHref,
  mentionTitle,
  parseStart,
  previewProblem,
  safeThumbnail,
  startWords,
} from "./describe.js";

describe("start times", () => {
  it("are written as minutes and seconds, with hours when there are any", () => {
    expect(startWords(0)).toBe("0:00");
    expect(startWords(754)).toBe("12:34");
    expect(startWords(3723)).toBe("1:02:03");
  });

  it("are read from minutes and seconds, hours, or plain seconds", () => {
    expect(parseStart("")).toBeNull();
    expect(parseStart("  ")).toBeNull();
    expect(parseStart("12:34")).toBe(754);
    expect(parseStart("1:02:03")).toBe(3723);
    expect(parseStart("90")).toBe(90);
    expect(parseStart(" 4:05 ")).toBe(245);
  });

  it("refuse what isn't a time, or is longer than twelve hours", () => {
    for (const text of ["abc", "12:75", "1:2:3:4", "-5", "12.5", "13:00:00"]) {
      expect(parseStart(text), text).toBeNaN();
    }
    expect(parseStart("12:00:00")).toBe(12 * 3600);
  });
});

describe("the address a mention opens", () => {
  it("starts a YouTube or Vimeo video at its start time", () => {
    expect(mentionHref({ canonical_url: "https://www.youtube.com/watch?v=abc123", start_seconds: 754 })).toBe(
      "https://www.youtube.com/watch?v=abc123&t=754s",
    );
    expect(mentionHref({ canonical_url: "https://vimeo.com/76979871", start_seconds: 90 })).toBe(
      "https://vimeo.com/76979871#t=90s",
    );
  });

  it("is the canonical address for anything else, or a video from its beginning", () => {
    expect(mentionHref({ canonical_url: "https://doi.org/10.5284/1040209", start_seconds: null })).toBe(
      "https://doi.org/10.5284/1040209",
    );
    expect(mentionHref({ canonical_url: "https://www.youtube.com/watch?v=abc123", start_seconds: 0 })).toBe(
      "https://www.youtube.com/watch?v=abc123",
    );
    // A podcast's start time can't be put in its address, so it opens at the episode.
    expect(mentionHref({ canonical_url: "https://pod.example.org/ep/4", start_seconds: 60 })).toBe(
      "https://pod.example.org/ep/4",
    );
  });

  it("is never anything but a web address", () => {
    expect(mentionHref({ canonical_url: "javascript:alert(1)", start_seconds: null })).toBeNull();
    expect(mentionHref({ canonical_url: "not an address", start_seconds: null })).toBeNull();
  });

  it("opens nothing when the server withholds the address from this viewer", () => {
    expect(mentionHref({ canonical_url: null, start_seconds: 30 })).toBeNull();
  });
});

describe("what a mention shows", () => {
  it("takes its title, or its address when its page gave none", () => {
    expect(mentionTitle({ title: "Barrows of the Ridgeway", canonical_url: "https://example.org/a" })).toBe(
      "Barrows of the Ridgeway",
    );
    expect(mentionTitle({ title: null, canonical_url: "https://example.org/a/" })).toBe("example.org/a");
    expect(mentionTitle({ title: null, canonical_url: null })).toBe("A link");
  });

  it("shows only a picture served over https", () => {
    expect(safeThumbnail("https://i.ytimg.com/vi/abc/hqdefault.jpg")).toBe("https://i.ytimg.com/vi/abc/hqdefault.jpg");
    expect(safeThumbnail("http://i.ytimg.com/vi/abc/hqdefault.jpg")).toBeNull();
    expect(safeThumbnail(null)).toBeNull();
  });

  it("says plainly when the preview found nothing", () => {
    expect(previewProblem({ fetch_status: "ok", title: "A title" })).toBeNull();
    expect(previewProblem({ fetch_status: "ok", title: null })).toMatch(/listed by its address/);
    expect(previewProblem({ fetch_status: "refused", title: null })).toMatch(/address alone/);
    expect(previewProblem({ fetch_status: "failed", title: null })).toMatch(/still save it/);
  });
});

describe("a refusal, in plain words", () => {
  it("puts an address problem beside the address", () => {
    for (const code of ["invalid_address", "mention_exists", "mention_hidden"]) {
      const failure = mentionFailure(new ApiError(code === "invalid_address" ? 422 : 409, code, "server words"));
      expect(failure.field, code).toBe("url");
      expect(failure.message, code).not.toBe("server words");
    }
  });

  it("says why a finding takes no more, above the buttons", () => {
    expect(mentionFailure(new ApiError(409, "finding_withdrawn", "x"))).toEqual({
      field: null,
      message: "This finding has been withdrawn, so it takes no more mentions.",
    });
    expect(mentionFailure(new ApiError(429, "rate_limited", "x")).message).toMatch(/Try again a little later/);
  });

  it("puts a map link refused on a protected finding beside the address", () => {
    const error = new ApiError(422, "position_in_text", "x", { fields: [{ field: "body.url", message: "x" }] });
    expect(mentionFailure(error)).toEqual({
      field: "url",
      message: expect.stringMatching(/shows where this finding is/),
    });
  });

  it("names the field a validation error is about", () => {
    const error = new ApiError(422, "validation_error", "Invalid", {
      fields: [{ field: "body.note", message: "Too long." }],
    });
    expect(mentionFailure(error)).toEqual({ field: "note", message: "Too long." });
  });

  it("keeps the server's words for anything else", () => {
    expect(mentionFailure(new ApiError(500, "internal", "The server broke."))).toEqual({
      field: null,
      message: "The server broke.",
    });
    expect(mentionFailure(new Error("offline"))).toEqual({ field: null, message: "offline" });
  });
});
