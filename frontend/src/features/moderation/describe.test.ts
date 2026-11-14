import { describe, expect, it } from "vitest";
import { metaFixture } from "../../test/fixtures/meta.js";
import { actionFixture, reportFixture, targetFixture } from "../../test/fixtures/people.js";
import { mayApprovePhotos, mayBan, roleChoices } from "./access.js";
import {
  actionSentence,
  deadlineReasons,
  dueWords,
  pointSourceWords,
  queueOrder,
  targetPhrase,
  targetState,
} from "./describe.js";

describe("the order of the report queue", () => {
  it("puts reports with a deadline first, soonest due first, and lists each report once", () => {
    const old = reportFixture({ id: 1 });
    const later = reportFixture({ id: 3, reason: "defamation", due_at: "2026-11-12T12:00:00Z" });
    const sooner = reportFixture({ id: 4, reason: "intimate_image", due_at: "2026-11-11T12:00:00Z" });
    const newer = reportFixture({ id: 5 });
    const order = queueOrder([later, sooner], [old, later, newer, sooner]);
    expect(order.map((report) => report.id)).toEqual([4, 3, 1, 5]);
  });

  it("takes the reasons with a deadline from /meta", () => {
    expect(deadlineReasons(metaFixture)).toEqual(["intimate_image", "defamation"]);
  });

  it("says when a report is due, and when it is overdue", () => {
    const now = Date.parse("2026-11-11T09:00:00Z");
    expect(dueWords(reportFixture(), now)).toBeNull();
    expect(dueWords(reportFixture({ due_at: "2026-11-12T09:00:00Z" }), now)).toMatch(/^Due by Thu 12 Nov/);
    expect(dueWords(reportFixture({ due_at: "2026-11-10T09:00:00Z" }), now)).toMatch(/^Overdue since Tue 10 Nov/);
  });
});

describe("moderation in words", () => {
  it("names a target and where it is", () => {
    expect(targetPhrase(targetFixture())).toBe("a comment on “Ring ditch by the long barrow”");
    expect(targetPhrase(targetFixture({ kind: "user", title: "Mary Anning", finding: null }))).toBe("Mary Anning");
    expect(targetState(targetFixture({ removed: true }))).toBe("Its author removed it.");
    expect(targetState(targetFixture({ exists: false }))).toBe("It no longer exists.");
    expect(targetState(targetFixture({ hidden: true }))).toBe("Hidden by a moderator.");
  });

  it("writes the log as sentences, with what changed", () => {
    expect(actionSentence(actionFixture())).toBe("Morag Kerr hid a comment on “Ring ditch by the long barrow”.");
    expect(
      actionSentence(
        actionFixture({
          action: "change_role",
          target: targetFixture({ kind: "user", title: "Mary Anning", finding: null }),
          data: { from: "member", to: "trusted" },
        }),
      ),
    ).toBe("Morag Kerr changed the role of Mary Anning from Member to Trusted member.");
    expect(
      actionSentence(
        actionFixture({
          action: "change_sensitivity",
          target: targetFixture({ kind: "finding", title: "Barrow", finding: null }),
          data: { from: "protected", to: "open" },
        }),
      ),
    ).toBe("Morag Kerr changed the level of the finding “Barrow” from protected to open.");
    // A level this version has no name for, stored in the log by an earlier one, is shown as stored.
    expect(
      actionSentence(
        actionFixture({
          action: "change_sensitivity",
          target: targetFixture({ kind: "finding", title: "Barrow", finding: null }),
          data: { from: "open", to: "restricted" },
        }),
      ),
    ).toBe("Morag Kerr changed the level of the finding “Barrow” from open to restricted.");
    // An admin's removal of an orphaned marking: the log holds the revisions, never a shape.
    expect(
      actionSentence(
        actionFixture({
          action: "remove_marking",
          target: targetFixture({ kind: "finding", title: "Road", finding: null }),
          data: { from_revision: 3, to_revision: 1 },
        }),
      ),
    ).toBe("Morag Kerr took back the marking of the finding “Road” to its shape at revision 1.");
    expect(
      actionSentence(
        actionFixture({
          action: "remove_marking",
          target: targetFixture({ kind: "finding", title: "Road", finding: null }),
          data: { from_revision: 3, to_revision: null },
        }),
      ),
    ).toBe("Morag Kerr took back the marking of the finding “Road” and removed its line or shape.");
    expect(actionSentence(actionFixture({ action: "resolve_report", data: { outcome: "dismissed" } }))).toMatch(
      /^Morag Kerr dismissed a report on a comment/,
    );
  });
});

describe("where a member's points came from", () => {
  it("puts the steps a finding reached in one sentence, then the rest", () => {
    expect(pointSourceWords(metaFixture, ["tier_seen", "tier_corroborated", "known_record"])).toEqual([
      "Their finding reached Seen by others and Corroborated",
      "Their finding matched a known record",
    ]);
    // In the ladder's order, whatever order the server sends.
    expect(pointSourceWords(metaFixture, ["tier_ground_checked", "tier_seen", "tier_corroborated"])).toEqual([
      "Their finding reached Seen by others, Corroborated and Checked on the ground",
    ]);
    expect(pointSourceWords(metaFixture, ["second_looks"])).toEqual([
      "Their second looks agreed with how findings turned out",
    ]);
  });
});

describe("who may do what", () => {
  it("lets trusted members, archaeologists and moderators approve photos", () => {
    expect(mayApprovePhotos("member")).toBe(false);
    expect(mayApprovePhotos("trusted")).toBe(true);
    expect(mayApprovePhotos("expert")).toBe(true);
    expect(mayApprovePhotos(null)).toBe(false);
  });

  it("offers only the role changes the server allows", () => {
    expect(roleChoices("moderator", "member", 60)).toEqual(["trusted", "expert"]);
    expect(roleChoices("moderator", "member", 10)).toEqual(["expert"]);
    expect(roleChoices("moderator", "trusted", 10)).toEqual(["member", "expert"]);
    expect(roleChoices("moderator", "moderator", 10)).toEqual([]);
    expect(roleChoices("admin", "moderator", 10)).toEqual(["member", "trusted", "expert"]);
    expect(roleChoices("admin", "admin", 10)).toEqual([]);
    expect(roleChoices("trusted", "member", 60)).toEqual([]);
  });

  it("lets a moderator ban anyone below moderator, and only an admin ban a moderator", () => {
    expect(mayBan("moderator", "trusted")).toBe(true);
    expect(mayBan("moderator", "moderator")).toBe(false);
    expect(mayBan("admin", "moderator")).toBe(true);
    expect(mayBan("admin", "admin")).toBe(false);
    expect(mayBan("trusted", "member")).toBe(false);
  });
});
