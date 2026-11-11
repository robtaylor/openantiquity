import { describe, expect, it } from "vitest";
import type { Meta } from "../../api/meta.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import {
  ageBandWords,
  licenceAddress,
  minimumAge,
  offersEmailLink,
  orList,
  signInProviders,
  takesUnder18s,
} from "./facts.js";

const withBands = (age_bands: string[]): Meta => ({ ...metaFixture, auth: { ...metaFixture.auth, age_bands } });

describe("the facts the notices take from /meta", () => {
  it("follows the minimum age the server sets", () => {
    expect(minimumAge(metaFixture)).toBe(16);
    expect(ageBandWords(metaFixture)).toBe("16 or 17, or 18 and over");
    expect(takesUnder18s(metaFixture)).toBe(true);
    const adults = withBands(["18_plus"]);
    expect(minimumAge(adults)).toBe(18);
    expect(ageBandWords(adults)).toBe("18 and over");
    expect(takesUnder18s(adults)).toBe(false);
  });

  it("names only the providers on offer, and not the emailed link", () => {
    expect(signInProviders(metaFixture)).toEqual(["Google", "OpenStreetMap"]);
    const emailOnly: Meta = {
      ...metaFixture,
      auth: {
        ...metaFixture.auth,
        providers: metaFixture.auth.providers.map((provider) => ({ ...provider, enabled: provider.id === "email" })),
      },
    };
    expect(signInProviders(emailOnly)).toEqual([]);
    expect(offersEmailLink(emailOnly)).toBe(true);
  });

  it("links a licence only where it knows the address", () => {
    expect(licenceAddress("CC BY 4.0")).toBe("https://creativecommons.org/licenses/by/4.0/");
    expect(licenceAddress("CC0 1.0")).toBeNull();
    expect(orList(["Google", "Apple", "OpenStreetMap"])).toBe("Google, Apple or OpenStreetMap");
  });
});
