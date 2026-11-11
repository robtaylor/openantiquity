// @vitest-environment node
import { describe, expect, it } from "vitest";
import { metaFixture as meta } from "../../test/fixtures/meta.js";
import type { TaskGroup, TaskItem } from "./api.js";
import { countWords, findKind, helpKinds, kindCount, kindFromAddress, kindTasks, taskPath } from "./kinds.js";

function task(publicId: string, code: TaskItem["code"], missing: string[] = []): TaskItem {
  const blind = ["need_observers", "need_class_agreement", "need_check", "need_trusted_review"].includes(code);
  return {
    public_id: publicId,
    code,
    place: { lon: -1.85, lat: 51.42, obscured: false, grid_ref: "SU 1 2", square: null, outline: null },
    view_state: {},
    step: blind ? null : { code, prompt: "Wanted.", missing_strands: missing, pending_evidence: [] },
    finding: blind ? null : { title: `Finding ${publicId}`, feature_class: "enclosure", tier: "seen", state: "open" },
  };
}

function group(code: TaskItem["code"], items: TaskItem[], total = items.length, next: string | null = null): TaskGroup {
  return { code, total, items, next_cursor: next, strands: [] };
}

const GROUPS: TaskGroup[] = [
  group("need_observers", [task("a", "need_observers"), task("b", "need_observers")], 4),
  group("need_class_agreement", [task("a", "need_class_agreement")], 1),
  group("need_strand", [task("c", "need_strand", ["historic_map", "aerial"]), task("d", "need_strand", ["aerial"])]),
  group("need_ground", []),
];

describe("helpKinds", () => {
  const kinds = helpKinds(meta, GROUPS);

  it("puts second looks first, then one kind per strand of desk evidence, then the field and official work", () => {
    expect(kinds.map((kind) => kind.id)).toEqual([
      "second-look",
      "lidar",
      "aerial",
      "historic_map",
      "records",
      "literature",
      "need_ground",
      "need_official",
    ]);
  });

  it("names each kind plainly and says what the work is", () => {
    const maps = findKind(kinds, "historic_map");
    expect(maps).toMatchObject({ name: "Map detectives", code: "need_strand", strand: "historic_map", blind: false });
    expect(maps?.line).toMatch(/^Map detectives check old maps/);
    expect(findKind(kinds, "second-look")).toMatchObject({ blind: true });
  });

  it("gives a kind for a code this build doesn't know, so no work is hidden", () => {
    const more = helpKinds(meta, [...GROUPS, group("need_photo" as TaskItem["code"], [task("e", "need_ground")])]);
    expect(findKind(more, "need_photo")).toMatchObject({ name: "Need photo", code: "need_photo", blind: false });
  });
});

describe("kindTasks and kindCount", () => {
  const kinds = helpKinds(meta, GROUPS);
  const aerial = findKind(kinds, "aerial");
  const maps = findKind(kinds, "historic_map");
  const looks = findKind(kinds, "second-look");
  if (!aerial || !maps || !looks) throw new Error("kinds missing");

  it("lists the findings whose evidence step wants that strand", () => {
    expect(kindTasks(aerial, GROUPS).map((item) => item.public_id)).toEqual(["c", "d"]);
    expect(kindTasks(maps, GROUPS).map((item) => item.public_id)).toEqual(["c"]);
  });

  it("never lists a second look by its finding", () => {
    expect(kindTasks(looks, GROUPS)).toEqual([]);
  });

  it("counts second looks by the busiest of their groups, and a strand by what it has loaded", () => {
    expect(kindCount(looks, GROUPS)).toEqual({ count: 4, more: false });
    expect(kindCount(maps, GROUPS)).toEqual({ count: 1, more: false });
    const paged = [group("need_strand", [task("c", "need_strand", ["historic_map"])], 80, "next")];
    expect(kindCount(maps, paged)).toEqual({ count: 1, more: true });
  });

  it("says the count in words", () => {
    expect(countWords({ count: 1, more: false })).toBe("1 finding");
    expect(countWords({ count: 3, more: false })).toBe("3 findings");
    expect(countWords({ count: 3, more: true })).toBe("3 or more findings");
    expect(countWords({ count: 0, more: true })).toBe("Some findings");
    expect(countWords({ count: 0, more: false })).toBe("Nothing waiting");
  });
});

describe("taskPath", () => {
  it("opens the finding with the right form named", () => {
    const kinds = helpKinds(meta, GROUPS);
    const maps = findKind(kinds, "historic_map");
    const ground = findKind(kinds, "need_ground");
    if (!maps || !ground) throw new Error("kinds missing");
    expect(taskPath(maps, task("c", "need_strand"))).toBe("/f/c?step=need_strand&strand=historic_map");
    expect(taskPath(ground, task("e", "need_ground"))).toBe("/f/e?step=need_ground");
  });
});

describe("kindFromAddress", () => {
  it("finds our kinds, takes an unknown step code, and refuses anything else", () => {
    expect(kindFromAddress(meta, "historic_map")?.name).toBe("Map detectives");
    expect(kindFromAddress(meta, "second-look")?.blind).toBe(true);
    expect(kindFromAddress(meta, "need_photo")?.name).toBe("Need photo");
    expect(kindFromAddress(meta, "need_observers")).toBeNull();
    expect(kindFromAddress(meta, "../etc")).toBeNull();
  });
});
