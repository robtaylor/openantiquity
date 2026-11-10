import { describe, expect, it } from "vitest";
import css from "./tokens.css?raw";
import { COLOURS, LAYOUT, STATE_COLOURS, TIER_COLOURS } from "./tokens.js";

function cssValue(name: string): string | undefined {
  return new RegExp(`--${name}:\\s*([^;]+);`).exec(css)?.[1]?.trim();
}

function kebab(name: string): string {
  return name.replaceAll(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`).replaceAll("_", "-");
}

describe("tokens.ts", () => {
  it("matches the colours in tokens.css", () => {
    for (const [name, value] of Object.entries(COLOURS)) {
      expect(cssValue(kebab(name)), name).toBe(value);
    }
    for (const [tier, value] of Object.entries(TIER_COLOURS)) {
      expect(cssValue(`tier-${kebab(tier)}`), tier).toBe(value);
    }
    for (const [state, value] of Object.entries(STATE_COLOURS)) {
      expect(cssValue(`state-${kebab(state)}`), state).toBe(value);
    }
  });

  it("matches the layout sizes in tokens.css", () => {
    expect(cssValue("rail-width")).toBe(`${LAYOUT.railWidth}px`);
    expect(cssValue("panel-width")).toBe(`${LAYOUT.panelWidth}px`);
    expect(cssValue("tabbar-height")).toBe(`${LAYOUT.tabBarHeight}px`);
    expect(cssValue("status-height")).toBe(`${LAYOUT.statusHeight}px`);
  });

  it("covers every tier and state colour that tokens.css defines", () => {
    const tiers = [...css.matchAll(/--tier-([a-z-]+):/g)].map((m) => m[1]);
    const states = [...css.matchAll(/--state-([a-z-]+):/g)].map((m) => m[1]);
    expect(tiers.sort()).toEqual(Object.keys(TIER_COLOURS).map(kebab).sort());
    expect(states.sort()).toEqual(Object.keys(STATE_COLOURS).map(kebab).sort());
  });
});
