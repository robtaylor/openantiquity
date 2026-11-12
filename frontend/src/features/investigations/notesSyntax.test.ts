import { describe, expect, it } from "vitest";
import { type Block, type Inline, MAX_DEPTH, parseInline, parseMarkdown } from "./notesSyntax.js";

const text = (value: string): Inline => ({ type: "text", text: value });

describe("parseInline", () => {
  it("reads plain text as itself", () => {
    expect(parseInline("A bank and a ditch")).toEqual([text("A bank and a ditch")]);
  });

  it("reads strong and emphasis, with either marker for emphasis", () => {
    expect(parseInline("a **big** bank, *faint* and _low_")).toEqual([
      text("a "),
      { type: "strong", children: [text("big")] },
      text(" bank, "),
      { type: "em", children: [text("faint")] },
      text(" and "),
      { type: "em", children: [text("low")] },
    ]);
  });

  it("nests emphasis inside strong", () => {
    expect(parseInline("**very *faint***")).toEqual([
      { type: "strong", children: [text("very "), { type: "em", children: [text("faint")] }] },
    ]);
  });

  it("leaves a lone marker, or one with nothing inside, as text", () => {
    expect(parseInline("2 * 3 and ** and **")).toEqual([text("2 * 3 and ** and **")]);
    expect(parseInline("snake_case_name")).toEqual([text("snake_case_name")]);
  });

  it("reads a link to an http or https address", () => {
    expect(parseInline("see [the HER](https://example.org/her?id=1) entry")).toEqual([
      text("see "),
      { type: "link", href: "https://example.org/her?id=1", children: [text("the HER")] },
      text(" entry"),
    ]);
  });

  it("never makes a link of any other kind of address, and keeps its words", () => {
    expect(parseInline("[click](javascript:alert(1))")).toEqual([text("click")]);
    expect(parseInline("[file](file:///etc/passwd) and [rel](/f/abc)")).toEqual([text("file and rel")]);
  });

  it("keeps HTML as the characters it is", () => {
    expect(parseInline('<img src=x onerror="alert(1)">')).toEqual([text('<img src=x onerror="alert(1)">')]);
  });

  it("takes a backslash to mean the next marker is meant literally", () => {
    expect(parseInline("\\*not emphasis\\*")).toEqual([text("*not emphasis*")]);
  });
});

describe("parseMarkdown", () => {
  it("reads headings, paragraphs and both kinds of list", () => {
    const blocks: Block[] = parseMarkdown(
      ["# The parish", "", "Two lines of one", "paragraph.", "", "- first", "* second", "", "1. one", "2. two"].join(
        "\n",
      ),
    );
    expect(blocks).toEqual([
      { type: "heading", level: 1, children: [text("The parish")] },
      { type: "paragraph", children: [text("Two lines of one paragraph.")] },
      { type: "list", ordered: false, items: [[text("first")], [text("second")]] },
      { type: "list", ordered: true, items: [[text("one")], [text("two")]] },
    ]);
  });

  it("ends a list where a paragraph starts, and folds an indented line into the item above", () => {
    expect(parseMarkdown("- a bank\n  that runs north\nAfter the list")).toEqual([
      { type: "list", ordered: false, items: [[text("a bank that runs north")]] },
      { type: "paragraph", children: [text("After the list")] },
    ]);
  });

  it("caps headings at six levels and needs a space after the hashes", () => {
    expect(parseMarkdown("####### seven\n#tag")).toEqual([
      { type: "paragraph", children: [text("####### seven #tag")] },
    ]);
  });

  it("reads nothing from empty text", () => {
    expect(parseMarkdown("")).toEqual([]);
    expect(parseMarkdown("\n \n")).toEqual([]);
  });

  it("reads Windows line ends", () => {
    expect(parseMarkdown("## A\r\n\r\nB")).toEqual([
      { type: "heading", level: 2, children: [text("A")] },
      { type: "paragraph", children: [text("B")] },
    ]);
  });
});

describe("parseMarkdown on hostile text", () => {
  /** How long a parse takes, in milliseconds, the best of three so a busy machine doesn't decide it. */
  function timed(source: string): number {
    let best = Number.POSITIVE_INFINITY;
    for (let attempt = 0; attempt < 3; attempt++) {
      const start = performance.now();
      parseMarkdown(source);
      best = Math.min(best, performance.now() - start);
    }
    return best;
  }

  // Each is at or above the longest note the server takes, 50,000 characters.
  it.each([
    ["unclosed underscores", "_a ".repeat(17000)],
    ["unclosed stars", "*a ".repeat(17000)],
    ["unclosed doubles", "**a ".repeat(13000)],
    ["openers before a closer that ends mid-word", `${"_x ".repeat(17000)}a_b`],
    ["unfinished links", "[a](".repeat(12500)],
    ["brackets", `${"[".repeat(50000)}](https://example.org)`],
    ["deep nesting", `${"**".repeat(12500)}x${"**".repeat(12500)}`],
    ["a long line of spaces", `${" ".repeat(50000)}x`],
    ["a heading with a few thousand spaces inside", `# a${" ".repeat(3000)}b`],
    ["a heading with a run of spaces inside", `# a${" ".repeat(49995)}b`],
    ["many headings with spaces inside", `# a${" ".repeat(700)}b\n`.repeat(70)],
    ["a heading of hashes and spaces", `# ${"# ".repeat(24999)}x`],
    ["a heading that ends in a long run of hashes", `# a ${"#".repeat(49995)}`],
    ["a bullet with spaces inside", `- a${" ".repeat(49995)}b`],
    ["a numbered item with spaces inside", `1. a${" ".repeat(49994)}b`],
  ])("reads %s quickly", (_name, source) => {
    expect(timed(source)).toBeLessThan(50);
  });

  it("still reads a heading's closing hashes, and keeps hashes that are part of a word", () => {
    expect(parseMarkdown("## The bank ##")).toEqual([{ type: "heading", level: 2, children: [text("The bank")] }]);
    expect(parseMarkdown("# Ditch   #   ")).toEqual([{ type: "heading", level: 1, children: [text("Ditch")] }]);
    expect(parseMarkdown("# Notes in C#")).toEqual([{ type: "heading", level: 1, children: [text("Notes in C#")] }]);
    expect(parseMarkdown("### ###")).toEqual([{ type: "heading", level: 3, children: [] }]);
    expect(parseMarkdown("#\tTabbed")).toEqual([{ type: "heading", level: 1, children: [text("Tabbed")] }]);
  });

  it("nests emphasis no deeper than it allows, showing deeper markers as written", () => {
    const source = `${"**".repeat(20)}x${"**".repeat(20)}`;
    let depth = 0;
    let node: Inline | undefined = parseInline(source)[0];
    while (node && node.type !== "text") {
      depth++;
      node = node.children[0];
    }
    expect(depth).toBe(MAX_DEPTH);
    expect(node?.type === "text" && node.text.includes("**")).toBe(true);
  });

  it("still reads emphasis and links in a long ordinary note", () => {
    const paragraph = "A bank, *faint*, beside a **ditch**; see [the HER](https://example.org/her). ".repeat(600);
    const [block] = parseMarkdown(paragraph);
    expect(block?.type).toBe("paragraph");
    const children = block?.type === "paragraph" ? block.children : [];
    expect(children.filter((node) => node.type === "link")).toHaveLength(600);
    expect(children.filter((node) => node.type === "em")).toHaveLength(600);
  });
});
