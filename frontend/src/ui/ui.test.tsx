import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { metaFixture } from "../test/fixtures/meta.js";
import { Avatar, hueOf, initialsOf } from "./Avatar.js";
import { Button } from "./Button.js";
import { ChipGroup } from "./Chip.js";
import { Dialog } from "./Dialog.js";
import { EmptyState } from "./EmptyState.js";
import { Field } from "./Field.js";
import { FEATURE_ICON_IDS, FeatureIcon, hasFeatureIcon } from "./featureIcons.js";
import { IconButton } from "./IconButton.js";
import { Meter } from "./Meter.js";
import { Panel } from "./Panel.js";
import { nearestStop, Sheet, type SheetStop, sheetHeights } from "./Sheet.js";
import { Skeleton } from "./Skeleton.js";
import { Slider } from "./Slider.js";
import { Switch } from "./Switch.js";
import { TabPanel, Tabs } from "./Tabs.js";
import { TierBadge } from "./TierBadge.js";
import { ToastViewport } from "./Toast.js";
import { toast, useToastStore } from "./toastStore.js";

const tiers = metaFixture.vocab.tiers;

function tier(id: string) {
  const found = tiers.find((t) => t.id === id);
  if (!found) throw new Error(`The fixture has no tier "${id}"`);
  return found;
}

function state(id: string) {
  const found = metaFixture.vocab.states.find((s) => s.id === id);
  if (!found) throw new Error(`The fixture has no state "${id}"`);
  return found;
}

describe("Button and IconButton", () => {
  it("renders each variant as a button that does not submit forms", () => {
    render(
      <>
        <Button variant="primary">Save</Button>
        <Button variant="danger">Withdraw</Button>
      </>,
    );
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toHaveClass("fc-button--primary");
    expect(save).toHaveAttribute("type", "button");
    expect(screen.getByRole("button", { name: "Withdraw" })).toHaveClass("fc-button--danger");
  });

  it("names an icon-only button and reports its pressed state", () => {
    render(
      <IconButton label="Layers" pressed>
        <svg aria-hidden="true" />
      </IconButton>,
    );
    const button = screen.getByRole("button", { name: "Layers" });
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(button).toHaveAttribute("title", "Layers");
  });
});

const CHIP_OPTIONS = [
  { id: "enclosure", label: "Enclosure" },
  { id: "hillfort", label: "Hillfort" },
  { id: "moat", label: "Moat", disabled: true },
  { id: "pit", label: "Pit or quarry" },
];

function SingleChips() {
  const [value, setValue] = useState<string | null>(null);
  return <ChipGroup label="Feature" options={CHIP_OPTIONS} value={value} onChange={setValue} />;
}

function MultipleChips() {
  const [value, setValue] = useState<string[]>(["hillfort"]);
  return <ChipGroup multiple label="Feature" options={CHIP_OPTIONS} value={value} onChange={setValue} />;
}

describe("ChipGroup", () => {
  it("is a radio group for a single choice, with arrow keys that skip disabled chips", async () => {
    const user = userEvent.setup();
    render(<SingleChips />);
    const group = screen.getByRole("radiogroup", { name: "Feature" });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(4);
    expect(radios[0]).toHaveAttribute("tabindex", "0");

    await user.click(screen.getByRole("radio", { name: "Hillfort" }));
    expect(screen.getByRole("radio", { name: "Hillfort" })).toBeChecked();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Pit or quarry" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Pit or quarry" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Enclosure" })).toBeChecked();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "Pit or quarry" })).toBeChecked();
  });

  it("toggles chips independently when multiple", async () => {
    const user = userEvent.setup();
    render(<MultipleChips />);
    const hillfort = screen.getByRole("button", { name: "Hillfort" });
    const enclosure = screen.getByRole("button", { name: "Enclosure" });
    expect(hillfort).toHaveAttribute("aria-pressed", "true");
    await user.click(enclosure);
    expect(enclosure).toHaveAttribute("aria-pressed", "true");
    expect(hillfort).toHaveAttribute("aria-pressed", "true");
    await user.click(hillfort);
    expect(hillfort).toHaveAttribute("aria-pressed", "false");
  });
});

function TabsExample() {
  const [tab, setTab] = useState("evidence");
  return (
    <>
      <Tabs
        label="Sections"
        idPrefix="t"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "evidence", label: "Evidence" },
          { id: "discussion", label: "Discussion" },
          { id: "timeline", label: "Timeline" },
        ]}
      />
      <TabPanel idPrefix="t" id={tab}>
        Showing {tab}
      </TabPanel>
    </>
  );
}

describe("Tabs", () => {
  it("moves with the arrow keys and ties each tab to its panel", async () => {
    const user = userEvent.setup();
    render(<TabsExample />);
    const evidence = screen.getByRole("tab", { name: "Evidence" });
    expect(evidence).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName("Evidence");

    await user.click(evidence);
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Discussion" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Discussion" })).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Showing discussion");
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Timeline" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowRight}");
    expect(evidence).toHaveAttribute("aria-selected", "true");
  });
});

describe("Field, Slider and Switch", () => {
  it("ties the label, hint and error to the control", () => {
    render(
      <Field label="Link" hint="Paste a web address." error="That doesn't look like a web address.">
        {(control) => <input {...control} />}
      </Field>,
    );
    const input = screen.getByLabelText("Link");
    expect(input).toHaveAccessibleDescription("Paste a web address. That doesn't look like a web address.");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("That doesn't look like a web address.");
  });

  it("reports slider changes as numbers and shows the formatted value", () => {
    const onChange = vi.fn();
    render(
      <Slider label="Opacity" value={80} min={0} max={100} step={5} format={(v) => `${v}%`} onChange={onChange} />,
    );
    const slider = screen.getByRole("slider", { name: "Opacity" });
    expect(slider).toHaveAttribute("aria-valuetext", "80%");
    expect(screen.getByText("80%")).toBeInTheDocument();
    fireEvent.change(slider, { target: { value: "35" } });
    expect(onChange).toHaveBeenCalledWith(35);
  });

  it("can be read out with more context than its shown label gives", () => {
    render(
      <>
        <Slider
          label="Opacity"
          accessibleName="OpenStreetMap opacity"
          value={80}
          min={0}
          max={100}
          onChange={() => {}}
        />
        <Slider label="Opacity" accessibleName="Findings opacity" value={50} min={0} max={100} onChange={() => {}} />
      </>,
    );
    expect(screen.getByRole("slider", { name: "OpenStreetMap opacity" })).toHaveValue("80");
    expect(screen.getByRole("slider", { name: "Findings opacity" })).toHaveValue("50");
    // The words on screen are unchanged.
    expect(screen.getAllByText("Opacity")).toHaveLength(2);
  });

  it("is a switch with a described state", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Switch label="Tilt into 3D" hint="Drapes the map over the terrain." checked={false} onChange={onChange} />);
    const control = screen.getByRole("switch", { name: "Tilt into 3D" });
    expect(control).not.toBeChecked();
    expect(control).toHaveAccessibleDescription("Drapes the map over the terrain.");
    await user.click(control);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe("Meter", () => {
  it("fills to the score and marks a tick for every tier", () => {
    const { container } = render(<Meter value={40} tiers={tiers} tierId="seen" showScale />);
    const meter = screen.getByRole("meter", { name: "Confidence" });
    expect(meter).toHaveAttribute("aria-valuenow", "40");
    expect(meter).toHaveAttribute("aria-valuetext", "Seen by others. Confidence 40 out of 100.");
    expect(container.querySelector(".fc-meter__fill")).toHaveStyle({ width: "40%" });

    const ticks = [...container.querySelectorAll<HTMLElement>(".fc-meter__tick")];
    expect(ticks.map((tick) => tick.dataset.tier)).toEqual(tiers.map((t) => t.id));
    expect(ticks.map((tick) => tick.style.left)).toEqual(tiers.map((t) => `${t.base_score}%`));
    const reached = ticks.filter((tick) => tick.classList.contains("fc-meter__tick--reached"));
    expect(reached.map((tick) => tick.dataset.tier)).toEqual(["spotted", "seen"]);
    const current = ticks.filter((tick) => tick.classList.contains("fc-meter__tick--current"));
    expect(current.map((tick) => tick.dataset.tier)).toEqual(["seen"]);
    expect(ticks[1]).toHaveAttribute("title", "Seen by others: 30");
  });

  it("clamps the score and copes with a tier it does not know", () => {
    render(<Meter value={140} tiers={tiers} tierId="mystery" />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "Unknown step. Confidence 100 out of 100.");
  });

  it("shows an empty track for a ruled-out finding", () => {
    const { container } = render(<Meter value={35} tiers={tiers} tierId="seen" ruledOut />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "0");
    expect(container.querySelector(".fc-meter")).toHaveClass("fc-meter--ruled-out");
    expect(container.querySelectorAll(".fc-meter__tick--reached")).toHaveLength(0);
  });
});

describe("TierBadge", () => {
  it("names the tier in words and takes its colour from the tier token", () => {
    const { container } = render(<TierBadge tier={tier("probable")} />);
    const badge = container.querySelector<HTMLElement>(".fc-tier-badge");
    expect(badge).toHaveTextContent("Probable");
    expect(badge?.style.getPropertyValue("--badge-colour")).toBe("var(--tier-probable)");
    expect(container.querySelector(".fc-tier-badge__mark--ring")).toBeNull();
  });

  it("uses the ground-checked token, whose id has an underscore", () => {
    const { container } = render(<TierBadge tier={tier("ground_checked")} />);
    const badge = container.querySelector<HTMLElement>(".fc-tier-badge");
    expect(badge?.style.getPropertyValue("--badge-colour")).toBe("var(--tier-ground-checked)");
  });

  it("shows a ring and the state for a known finding", () => {
    const { container } = render(<TierBadge tier={tier("seen")} state={state("known")} />);
    expect(container.querySelector(".fc-tier-badge")).toHaveTextContent("Seen by others· Matches a known record");
    expect(container.querySelector(".fc-tier-badge__mark--ring")).not.toBeNull();
  });

  it("shows the state alone, in grey, for a ruled-out finding", () => {
    const { container } = render(<TierBadge tier={tier("seen")} state={state("ruled_out")} />);
    const badge = container.querySelector<HTMLElement>(".fc-tier-badge");
    expect(badge).toHaveTextContent(/^Explained$/);
    expect(badge?.style.getPropertyValue("--badge-colour")).toBe("var(--state-ruled-out)");
  });

  it("leaves out an open state", () => {
    const { container } = render(<TierBadge tier={tier("spotted")} state={state("open")} />);
    expect(container.querySelector(".fc-tier-badge")).toHaveTextContent(/^Spotted$/);
  });
});

describe("Avatar", () => {
  it("takes initials from names of every shape", () => {
    expect(initialsOf("Mary Leakey")).toBe("ML");
    expect(initialsOf("QuietBarrow42")).toBe("QB");
    expect(initialsOf("os_surveyor")).toBe("OS");
    expect(initialsOf("mortimer")).toBe("M");
    expect(initialsOf("  ")).toBe("?");
    expect(initialsOf("42")).toBe("?");
  });

  it("gives the same person the same colour every time", () => {
    expect(hueOf("QuietBarrow42")).toBe(hueOf("QuietBarrow42"));
    expect(hueOf("QuietBarrow42")).not.toBe(hueOf("QuietBarrow43"));
    expect(hueOf("anything")).toBeGreaterThanOrEqual(0);
    expect(hueOf("anything")).toBeLessThan(360);
  });

  it("is an image with the person's name", () => {
    render(<Avatar name="Mary Leakey" />);
    expect(screen.getByRole("img", { name: "Mary Leakey" })).toHaveTextContent("ML");
  });

  it("never draws a picture, so no other site is asked for one", () => {
    const { container } = render(<Avatar name="Mary Leakey" handle="MaryL" size={40} />);
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("Toast", () => {
  afterEach(() => {
    act(() => useToastStore.getState().clear());
    vi.useRealTimers();
  });

  it("shows a message, runs its action and can be dismissed", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    render(<ToastViewport />);
    act(() => {
      toast("Couldn't save your answer.", { kind: "error", action: { label: "Retry", onClick: retry } });
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't save your answer.");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();

    act(() => {
      toast("Saved.", { kind: "success" });
    });
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("Saved.")).toBeNull();
  });

  it("goes away on its own and keeps only the newest few", () => {
    vi.useFakeTimers();
    render(<ToastViewport />);
    act(() => {
      for (const n of [1, 2, 3, 4]) toast(`Message ${n}`);
    });
    expect(screen.queryByText("Message 1")).toBeNull();
    expect(screen.getAllByRole("status")).toHaveLength(3);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryAllByRole("status")).toHaveLength(0);
  });
});

/** A button that opens a dialog, which is taken out of the page to close it. */
function Opener() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Edit the note</Button>
      {open ? (
        <Dialog open onClose={() => setOpen(false)} title="Edit this note" actions={<Button>Save</Button>}>
          <input aria-label="Note" />
        </Dialog>
      ) : null}
    </>
  );
}

describe("Dialog", () => {
  it("shows its content only while open and closes from its button", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { rerender } = render(
      <Dialog open={false} onClose={onClose} title="Withdraw this finding?">
        <p>It stays visible.</p>
      </Dialog>,
    );
    expect(screen.queryByText("It stays visible.")).toBeNull();

    rerender(
      <Dialog open onClose={onClose} title="Withdraw this finding?" actions={<Button>Keep it</Button>}>
        <p>It stays visible.</p>
      </Dialog>,
    );
    const dialog = screen.getByRole("dialog", { name: "Withdraw this finding?" });
    expect(dialog).toHaveAttribute("open");
    expect(within(dialog).getByText("It stays visible.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps Tab inside: from the last control to the first, and back", async () => {
    const user = userEvent.setup();
    render(
      <Dialog open onClose={() => {}} title="Delete your account?" actions={<Button>Delete</Button>}>
        <input aria-label="Reason" />
      </Dialog>,
    );
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    const close = within(dialog).getByRole("button", { name: "Close" });
    const last = within(dialog).getByRole("button", { name: "Delete" });
    // It opens with focus on its title. Shift+Tab from there goes round to the end.
    expect(within(dialog).getByRole("heading", { name: "Delete your account?" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(last).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(last).toHaveFocus();
    await user.tab({ shift: true });
    expect(within(dialog).getByRole("textbox", { name: "Reason" })).toHaveFocus();
  });

  it("gives focus back to what opened it when it is taken out of the page, not to the page", async () => {
    const user = userEvent.setup();
    render(<Opener />);
    const opener = screen.getByRole("button", { name: "Edit the note" });
    await user.click(opener);
    await user.click(screen.getByRole("textbox", { name: "Note" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();

    await user.click(opener);
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(opener).toHaveFocus();
  });
});

function SheetExample({ onClose }: { onClose: () => void }) {
  const [stop, setStop] = useState<SheetStop>("half");
  return (
    <Sheet title="Layers" onClose={onClose} stop={stop} onStopChange={setStop} availableHeight={720}>
      <button type="button">Inside</button>
    </Sheet>
  );
}

describe("Panel and Sheet", () => {
  it("labels the side panel with its title and closes from the header", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Panel title="Layers" subtitle="What the map shows" onClose={onClose}>
        <p>Body</p>
      </Panel>,
    );
    expect(screen.getByRole("complementary", { name: "Layers" })).toHaveTextContent("What the map shows");
    await user.click(screen.getByRole("button", { name: "Close panel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("works out the three sheet stops and the nearest one", () => {
    const heights = sheetHeights(720);
    expect(heights).toEqual({ peek: 76, half: 360, full: 720 });
    expect(nearestStop(80, heights)).toBe("peek");
    expect(nearestStop(300, heights)).toBe("half");
    expect(nearestStop(600, heights)).toBe("full");
    // A tiny screen never makes a stop smaller than the title row.
    expect(sheetHeights(40)).toEqual({ peek: 76, half: 76, full: 76 });
  });

  it("steps through its stops from the handle and hides its body at the lowest", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<SheetExample onClose={onClose} />);
    const sheet = screen.getByRole("complementary", { name: "Layers" });
    const handle = screen.getByRole("button", { name: /Press to resize/ });
    expect(sheet).toHaveAttribute("data-stop", "half");
    // The sheet is as tall as the part of it on screen, so its body always scrolls to its end.
    expect(sheet.style.getPropertyValue("--sheet-height")).toBe("360px");

    await user.click(handle);
    expect(sheet).toHaveAttribute("data-stop", "full");
    expect(sheet.style.getPropertyValue("--sheet-height")).toBe("720px");
    await user.click(handle);
    expect(sheet).toHaveAttribute("data-stop", "peek");
    expect(sheet.style.getPropertyValue("--sheet-height")).toBe("76px");
    expect(sheet.querySelector(".fc-panel__body")).toHaveAttribute("inert");

    handle.focus();
    await user.keyboard("{ArrowUp}");
    expect(sheet).toHaveAttribute("data-stop", "half");
    expect(sheet.querySelector(".fc-panel__body")).not.toHaveAttribute("inert");
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape from any control inside, unless that control has used the key itself", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Panel title="Layers" onClose={onClose}>
        <button type="button">Inside</button>
        <input
          aria-label="Uses Escape"
          onKeyDown={(event) => {
            if (event.key === "Escape") event.preventDefault();
          }}
        />
      </Panel>,
    );
    screen.getByRole("textbox", { name: "Uses Escape" }).focus();
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
    screen.getByRole("button", { name: "Inside" }).focus();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes the sheet on Escape from its body as well as its handle", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<SheetExample onClose={onClose} />);
    const sheet = screen.getByRole("complementary", { name: "Layers" });
    within(sheet).getByRole("button", { name: "Inside" }).focus();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("lets a script put focus on the title, without adding it to the Tab order", () => {
    const title = { current: null as HTMLHeadingElement | null };
    render(
      <Panel title="Layers" onClose={() => {}} titleRef={title}>
        <p>Body</p>
      </Panel>,
    );
    expect(title.current).toHaveAttribute("tabindex", "-1");
    title.current?.focus();
    expect(screen.getByRole("heading", { name: "Layers" })).toHaveFocus();
  });

  it("snaps to the nearest stop after a drag", () => {
    render(<SheetExample onClose={() => {}} />);
    const sheet = screen.getByRole("complementary", { name: "Layers" });
    const handle = screen.getByRole("button", { name: /Press to resize/ });
    fireEvent.pointerDown(handle, { pointerId: 1, clientY: 500, button: 0 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientY: 200 });
    expect(sheet).toHaveClass("fc-sheet--dragging");
    expect(sheet.style.getPropertyValue("--sheet-height")).toBe("660px");
    fireEvent.pointerUp(handle, { pointerId: 1, clientY: 200 });
    expect(sheet).toHaveAttribute("data-stop", "full");
    expect(sheet).not.toHaveClass("fc-sheet--dragging");
  });
});

describe("EmptyState and Skeleton", () => {
  it("says what happened and offers the next step", () => {
    render(
      <EmptyState tone="error" title="The map couldn't start" action={<Button>Try again</Button>}>
        <p>Couldn't reach the server.</p>
      </EmptyState>,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The map couldn't start");
    expect(within(alert).getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("draws the asked-for number of lines, hidden from screen readers", () => {
    const { container } = render(<Skeleton lines={3} />);
    expect(container.querySelectorAll(".fc-skeleton")).toHaveLength(3);
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });
});

describe("feature pictograms", () => {
  it("has a drawing for every feature class the vocabulary lists", () => {
    const ids = metaFixture.vocab.feature_classes.map((item) => item.id);
    expect(ids.length).toBeGreaterThan(0);
    for (const id of ids) expect(hasFeatureIcon(id), id).toBe(true);
    expect([...FEATURE_ICON_IDS].sort()).toEqual([...ids].sort());
  });

  it("draws a different glyph for each class", () => {
    const drawings = new Set(
      FEATURE_ICON_IDS.map((id) => render(<FeatureIcon classId={id} />).container.querySelector("svg")?.innerHTML),
    );
    expect(drawings.size).toBe(FEATURE_ICON_IDS.length);
  });

  it("falls back to the not-sure glyph for a class it has never seen", () => {
    const unknown = render(<FeatureIcon classId="unknown" />).container.querySelector("svg");
    const novel = render(<FeatureIcon classId="crannog" />).container.querySelector("svg");
    expect(novel?.innerHTML).toBe(unknown?.innerHTML);
    expect(novel).toHaveAttribute("data-feature-class", "crannog");
  });

  it("is decorative unless given a title", () => {
    const { container, rerender } = render(<FeatureIcon classId="moat" />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    rerender(<FeatureIcon classId="moat" title="Moat" />);
    expect(screen.getByRole("img", { name: "Moat" })).toBeInTheDocument();
  });
});
