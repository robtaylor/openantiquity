import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { observationFixture, pageFixture, revealFixture } from "../../test/fixtures/findingPage.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import type { FindingDetail, Observation } from "../finding/types.js";
import { RevealCard } from "./RevealCard.js";

describe("a reveal naming a class a later version of the server added", () => {
  // This page's `/meta` was loaded before the deploy, so it has no name for the class.
  const LATER = "added_by_a_later_version";

  it("says Not sure for the finder's class, and doesn't call the same class a disagreement", () => {
    const finding = pageFixture({ feature_class: LATER as FindingDetail["feature_class"] });
    const answer = observationFixture({ feature_class: "unknown" as Observation["feature_class"] });
    const reveal = revealFixture(answer, finding, {
      comparison: {
        finder_class: LATER as FindingDetail["feature_class"],
        community_class: LATER as FindingDetail["feature_class"],
        matches_finder: false,
        others: { yes: 1, unsure: 0, no: 0 },
      },
    });

    render(
      <MemoryRouter>
        <RevealCard meta={metaFixture} reveal={reveal} onNext={() => {}} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/The finder marked it as: Not sure\./)).toBeInTheDocument();
    expect(screen.queryByText(/Most people say/)).toBeNull();
    expect(screen.queryByText(/later version/)).toBeNull();
    const looksLike = screen.getByText("Looks like").nextElementSibling as HTMLElement;
    expect(looksLike).toHaveTextContent("Not sure");
  });
});
