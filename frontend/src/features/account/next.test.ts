import { describe, expect, it } from "vitest";
import { nextFromLocation, SIGNIN_ERROR_PARAM, safeNext, withoutSigninError } from "./next.js";

describe("safeNext", () => {
  it.each([
    "/",
    "/account",
    "/f/abc123",
    "/review?panel=layers",
    "/#m=14/51.4286/-1.8542/0/0&v=composite",
    "/f/x?panel=layers#m=12.5/51.1788/-1.8263/0/0&v=raking&s=90/20&o=osm:40,findings:100:h",
    "/u/Quiet%20Barrow",
  ])("keeps a path on this site: %s", (path) => {
    expect(safeNext(path)).toBe(path);
  });

  it.each([
    ["another origin", "https://evil.example/"],
    ["another origin over http", "http://evil.example"],
    ["scheme-relative", "//evil.example"],
    ["scheme-relative with a path", "//evil.example/account"],
    ["a backslash", "/\\evil.example"],
    ["a leading backslash", "\\\\evil.example"],
    ["an encoded backslash", "/%5Cevil.example"],
    ["an encoded slash pair", "/%2F%2Fevil.example"],
    ["a doubly encoded slash pair", "/%252F%252Fevil.example"],
    ["a trebly encoded slash pair", "/%25252F%25252Fevil.example"],
    ["javascript:", "javascript:alert(1)"],
    ["javascript: after a slash", "/javascript:alert(1)/../..//evil.example"],
    ["data:", "data:text/html,hi"],
    ["a dot-dot segment", "/a/..//evil.example"],
    ["an encoded dot-dot segment", "/a/%2E%2E/b"],
    ["a dot segment", "/./account"],
    ["a tab", "/\t/evil.example"],
    ["an encoded tab", "/%09/evil.example"],
    ["an encoded newline", "/%0A/evil.example"],
    ["a zero-width space", "/%E2%80%8B/x"],
    ["a right-to-left override", "/%E2%80%AEx"],
    ["a space", "/a b"],
    ["a relative path", "account"],
    ["nothing", ""],
    ["malformed percent-encoding", "/%E0%A4%A"],
    ["something far too long", `/${"a".repeat(2001)}`],
  ])("sends %s home", (_label, path) => {
    expect(safeNext(path)).toBe("/");
  });

  it("sends null and undefined home", () => {
    expect(safeNext(null)).toBe("/");
    expect(safeNext(undefined)).toBe("/");
  });
});

describe("withoutSigninError", () => {
  it("removes the parameter and keeps the rest", () => {
    expect(withoutSigninError(`?panel=layers&${SIGNIN_ERROR_PARAM}=cancelled`)).toBe("?panel=layers");
    expect(withoutSigninError(`?${SIGNIN_ERROR_PARAM}=cancelled`)).toBe("");
    expect(withoutSigninError("")).toBe("");
  });
});

describe("nextFromLocation", () => {
  it("is where the person is: path, query and map position", () => {
    expect(nextFromLocation({ pathname: "/review", search: "?panel=layers", hash: "#m=14/51.4/-1.8/0/0" })).toBe(
      "/review?panel=layers#m=14/51.4/-1.8/0/0",
    );
  });

  it("leaves out a sign-in error that is still in the address", () => {
    expect(nextFromLocation({ pathname: "/", search: `?${SIGNIN_ERROR_PARAM}=cancelled`, hash: "#m=1/2/3/0/0" })).toBe(
      "/#m=1/2/3/0/0",
    );
  });

  it("goes home from the sign-in pages themselves", () => {
    expect(nextFromLocation({ pathname: "/signin/email", search: "?next=/account", hash: "" })).toBe("/");
  });

  it("goes home from an address that would not be safe to come back to", () => {
    expect(nextFromLocation({ pathname: "//evil.example", search: "", hash: "" })).toBe("/");
  });
});
