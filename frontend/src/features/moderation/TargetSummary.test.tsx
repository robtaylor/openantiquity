import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { targetFixture } from "../../test/fixtures/people.js";
import { TargetSummary } from "./TargetSummary.js";

describe("TargetSummary", () => {
  it("links a web address", () => {
    render(
      <MemoryRouter>
        <TargetSummary target={targetFixture({ url: "https://example.org/page" })} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "https://example.org/page" })).toHaveAttribute(
      "href",
      "https://example.org/page",
    );
  });

  it.each(["javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:x", "/relative"])(
    "shows %s as words a moderator can't follow",
    (url) => {
      const { container } = render(
        <MemoryRouter>
          <TargetSummary target={targetFixture({ url })} />
        </MemoryRouter>,
      );
      expect(screen.getByText(url)).toBeInTheDocument();
      expect(container.querySelector(`a[href="${CSS.escape(url)}"]`)).toBeNull();
      expect([...container.querySelectorAll("a")].map((a) => a.getAttribute("href"))).not.toContain(url);
    },
  );
});
