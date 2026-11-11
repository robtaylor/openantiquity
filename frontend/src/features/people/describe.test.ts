import { describe, expect, it } from "vitest";
import { metaFixture } from "../../test/fixtures/meta.js";
import { contributionFixture } from "../../test/fixtures/people.js";
import { contributionWords, joinedWords, pointsWords, pointWords } from "./describe.js";

describe("a person's page in words", () => {
  it("says what each contribution was, with words from /meta", () => {
    expect(contributionWords(metaFixture, contributionFixture(), false)).toBe("Added an aerial photo");
    expect(contributionWords(metaFixture, contributionFixture({ subkind: "historic_map" }), true)).toBe(
      "You added an old map",
    );
    expect(contributionWords(metaFixture, contributionFixture({ kind: "comment", subkind: null }), false)).toBe(
      "Commented",
    );
    expect(contributionWords(metaFixture, contributionFixture({ kind: "mention", subkind: "video" }), false)).toBe(
      "Linked a video about it",
    );
  });

  it("says where each point came from", () => {
    expect(pointWords(metaFixture, "tier_seen")).toBe("Your finding reached Seen by others");
    expect(pointWords(metaFixture, "evidence_endorsed_12")).toBe("Two people endorsed evidence you added");
    expect(pointWords(metaFixture, "known_record")).toBe("Your finding matched a known record");
    expect(pointWords(metaFixture, "observation_corroborated")).toBe("Your second look agreed with how it turned out");
    expect(pointWords(metaFixture, "something_new")).toBe("something new");
  });

  it("counts points and gives the month someone joined", () => {
    expect(pointsWords(1)).toBe("1 point");
    expect(pointsWords(2.5)).toBe("2.5 points");
    expect(joinedWords("2026-10-02T09:00:00Z")).toBe("Joined October 2026");
  });
});
