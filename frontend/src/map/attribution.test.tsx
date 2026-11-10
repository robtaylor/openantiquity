import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Attribution, attributionText, parseAttribution } from "./attribution.js";

const OSM = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const OPENFREEMAP =
  '<a href="https://openfreemap.org" target="_blank">OpenFreeMap</a> ' +
  '<a href="https://www.openmaptiles.org/" target="_blank">&copy; OpenMapTiles</a> ' +
  'Data from <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>';

describe("parseAttribution", () => {
  it("leaves plain text alone", () => {
    expect(parseAttribution("LIDAR: Environment Agency, under the Open Government Licence v3.0")).toEqual([
      { text: "LIDAR: Environment Agency, under the Open Government Licence v3.0" },
    ]);
    expect(parseAttribution("   ")).toEqual([]);
  });

  it("keeps web links and the text around them", () => {
    expect(parseAttribution(OSM)).toEqual([
      { text: "© " },
      { text: "OpenStreetMap", href: "https://www.openstreetmap.org/copyright" },
      { text: " contributors" },
    ]);
  });

  it("decodes entities", () => {
    const parts = parseAttribution(OPENFREEMAP);
    expect(parts.map((part) => part.text).join("")).toBe("OpenFreeMap © OpenMapTiles Data from OpenStreetMap");
    expect(parts.filter((part) => part.href).map((part) => part.href)).toEqual([
      "https://openfreemap.org/",
      "https://www.openmaptiles.org/",
      "https://www.openstreetmap.org/copyright",
    ]);
    expect(parseAttribution("Fish &amp; chips")).toEqual([{ text: "Fish & chips" }]);
  });

  it("drops scripts, event handlers and every tag but links", () => {
    const hostile =
      'Maps <img src=x onerror="alert(1)"><script>alert(2)</script><b>bold</b> ' +
      '<a href="javascript:alert(3)">click</a> <a href="/relative">here</a> <a onclick="alert(4)" href="https://ok.example/">ok</a>';
    const parts = parseAttribution(hostile);
    expect(parts).toEqual([{ text: "Maps bold click here " }, { text: "ok", href: "https://ok.example/" }]);
  });
});

describe("attributionText", () => {
  it("flattens to one line of text", () => {
    expect(attributionText(OSM)).toBe("© OpenStreetMap contributors");
    expect(attributionText("  a\n  b  ")).toBe("a b");
  });
});

describe("Attribution", () => {
  it("renders links that open safely in a new tab", () => {
    const { container } = render(
      <p>
        <Attribution html={OSM} />
      </p>,
    );
    expect(container.textContent).toBe("© OpenStreetMap contributors");
    const link = screen.getByRole("link", { name: "OpenStreetMap" });
    expect(link).toHaveAttribute("href", "https://www.openstreetmap.org/copyright");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("never renders markup from the string", () => {
    const { container } = render(
      <p>
        <Attribution html={'<img src=x onerror="alert(1)"><script>alert(2)</script>Safe'} />
      </p>,
    );
    expect(container.querySelector("img, script")).toBeNull();
    expect(container.textContent).toBe("Safe");
  });
});
