// @vitest-environment node
import { describe, expect, it } from "vitest";
import { pageFixture, seenFixture } from "../../test/fixtures/findingPage.js";
import { metaFixture as meta } from "../../test/fixtures/meta.js";
import { positionOf, type Viewer } from "./describe.js";
import { actionForStep, findingStepPath, stepFromAddress } from "./stepLink.js";

const MEMBER: Viewer = { ready: true, signedIn: true, handle: "KeenLynchet7", role: "member" };

describe("findingStepPath", () => {
  it("names the step, and the strand when there is one", () => {
    expect(findingStepPath("f-ring", "need_strand", "historic_map")).toBe(
      "/f/f-ring?step=need_strand&strand=historic_map",
    );
    expect(findingStepPath("f ring", "need_ground")).toBe("/f/f%20ring?step=need_ground");
  });

  it("reads back what it wrote", () => {
    const url = new URL(findingStepPath("f-ring", "need_strand", "aerial"), "http://localhost");
    expect(stepFromAddress(url.searchParams)).toEqual({ code: "need_strand", strand: "aerial" });
    expect(stepFromAddress(new URLSearchParams())).toBeNull();
  });
});

describe("actionForStep", () => {
  const finding = seenFixture();
  const position = positionOf(finding, MEMBER);

  it("opens the form for the strand asked for", () => {
    expect(actionForStep(finding, meta, position, { code: "need_strand", strand: "historic_map" })).toMatchObject({
      kind: "evidence",
      evidenceKind: "historic_map",
    });
    expect(actionForStep(finding, meta, position, { code: "need_strand", strand: "aerial" })).toMatchObject({
      evidenceKind: "aerial",
    });
  });

  it("opens the first form when no strand is named", () => {
    expect(actionForStep(finding, meta, position, { code: "need_strand", strand: null })).toMatchObject({
      kind: "evidence",
      evidenceKind: "aerial",
    });
  });

  it("does nothing for a step the finding no longer has", () => {
    expect(actionForStep(finding, meta, position, { code: "need_ground", strand: null })).toBeNull();
    const done = pageFixture();
    expect(actionForStep(done, meta, positionOf(done, MEMBER), { code: "need_strand", strand: null })).toBeNull();
  });
});
