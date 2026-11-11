import { describe, expect, it } from "vitest";
import type { Member } from "./api.js";
import { cleanHandle, itemCountText, mayInvite, powersOf, visibilityChoices } from "./describe.js";

const user = (handle: string) => ({ handle, display_name: handle, avatar_url: null, role: "member" });
const owner: Member = { user: user("Owner1"), role: "owner", joined_at: "2026-11-01T10:00:00Z", pending: false };
const invited: Member = { user: user("Guest1"), role: "editor", joined_at: "2026-11-02T10:00:00Z", pending: true };

describe("powersOf", () => {
  it("gives the owner everything, an editor the contents, and a reader nothing but leaving", () => {
    expect(powersOf({ my_role: "owner", invited_as: null, hidden: false })).toEqual({
      edit: true,
      own: true,
      leave: false,
      answer: false,
    });
    expect(powersOf({ my_role: "editor", invited_as: null, hidden: false })).toMatchObject({
      edit: true,
      own: false,
      leave: true,
    });
    expect(powersOf({ my_role: "viewer", invited_as: null, hidden: false })).toMatchObject({
      edit: false,
      leave: true,
    });
  });

  it("lets someone invited answer, and someone else only read", () => {
    expect(powersOf({ my_role: null, invited_as: "editor", hidden: false }).answer).toBe(true);
    expect(powersOf({ my_role: null, invited_as: null, hidden: false })).toEqual({
      edit: false,
      own: false,
      leave: false,
      answer: false,
    });
  });
});

describe("visibilityChoices", () => {
  it("offers private only while the owner is the one member, invitations counted", () => {
    expect(visibilityChoices({ visibility: "public" }, [owner])).toEqual(["private", "unlisted"]);
    expect(visibilityChoices({ visibility: "public" }, [owner, invited])).toEqual(["unlisted"]);
    expect(visibilityChoices({ visibility: "private" }, [owner])).toEqual(["unlisted", "public"]);
    // While the members aren't known, private isn't offered: the server would refuse it if there were others.
    expect(visibilityChoices({ visibility: "public" }, undefined)).toEqual(["unlisted"]);
  });
});

describe("mayInvite", () => {
  it("never offers to invite anyone to a private investigation", () => {
    const own = powersOf({ my_role: "owner", invited_as: null, hidden: false });
    expect(mayInvite(own, { visibility: "private" })).toBe(false);
    expect(mayInvite(own, { visibility: "unlisted" })).toBe(true);
    const edit = powersOf({ my_role: "editor", invited_as: null, hidden: false });
    expect(mayInvite(edit, { visibility: "public" })).toBe(false);
  });
});

describe("cleanHandle", () => {
  it("takes a handle with or without its @, and refuses what can't be one", () => {
    expect(cleanHandle(" @QuietBarrow42 ")).toBe("QuietBarrow42");
    expect(cleanHandle("KeenLynchet7")).toBe("KeenLynchet7");
    expect(cleanHandle("no spaces")).toBeNull();
    expect(cleanHandle("@")).toBeNull();
  });
});

describe("itemCountText", () => {
  it("counts items in words", () => {
    expect(itemCountText(0)).toBe("Nothing in it yet");
    expect(itemCountText(1)).toBe("1 item");
    expect(itemCountText(12)).toBe("12 items");
  });
});
