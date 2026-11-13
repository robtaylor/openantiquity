import { afterEach, describe, expect, it } from "vitest";
import { focusAfter } from "./focus.js";

function button(name: string): HTMLButtonElement {
  const element = document.createElement("button");
  element.dataset.name = name;
  document.body.append(element);
  return element;
}

function frame(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("where focus goes when the control that had it is taken away", () => {
  it("goes to the control named, once a frame has passed, when focus went with the one pressed", async () => {
    const pressed = button("pressed");
    const next = button("next");
    pressed.focus();
    pressed.remove();
    focusAfter(pressed, '[data-name="next"]');
    await frame();
    expect(next).toHaveFocus();
  });

  it("leaves focus alone when the one pressed is still there and still has it", async () => {
    const pressed = button("pressed");
    button("next");
    pressed.focus();
    focusAfter(pressed, '[data-name="next"]');
    await frame();
    expect(pressed).toHaveFocus();
  });

  it("leaves focus alone when it has moved on to another control before the frame", async () => {
    // A handle is deleted, and before the frame the person, or the next thing they did, put focus
    // somewhere else. Taking it back would send their next key to the wrong control.
    const pressed = button("pressed");
    button("next");
    const elsewhere = button("elsewhere");
    pressed.focus();
    pressed.remove();
    focusAfter(pressed, '[data-name="next"]');
    elsewhere.focus();
    await frame();
    expect(elsewhere).toHaveFocus();
  });
});
