import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CreditItem } from "./Credits.js";

const CREDIT = {
  key: "k",
  name: "Some records",
  publisher: "A council",
  licence: "OGL v3.0",
  licenceUrl: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  attribution: null,
  homepage: "https://example.org/",
};

describe("CreditItem", () => {
  it("links the licence and the publisher's website", () => {
    render(<CreditItem credit={CREDIT} />);
    expect(screen.getByRole("link", { name: /OGL v3.0/ })).toHaveAttribute("href", CREDIT.licenceUrl);
    expect(screen.getByRole("link", { name: /Their website/ })).toHaveAttribute("href", CREDIT.homepage);
  });

  it("follows no address that isn't a web address", () => {
    const { container } = render(
      <CreditItem credit={{ ...CREDIT, licenceUrl: "javascript:alert(1)", homepage: "data:text/html,hi" }} />,
    );
    expect(container.querySelectorAll("a")).toHaveLength(0);
    // The licence is still named.
    expect(screen.getByText(/OGL v3.0/)).toBeInTheDocument();
  });
});
