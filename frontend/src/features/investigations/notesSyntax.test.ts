import { describe, expect, it } from "vitest";
import { type Block, type Inline, parseInline, parseMarkdown } from "./notesSyntax.js";

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
