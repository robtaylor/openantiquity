import { type ReactNode, useMemo } from "react";
import { type Inline, parseMarkdown } from "./notesSyntax.js";

function inlines(nodes: readonly Inline[]): ReactNode[] {
  return nodes.map((node, index) => {
    switch (node.type) {
      case "text":
        return node.text;
      case "strong":
        // biome-ignore lint/suspicious/noArrayIndexKey: the parts of one line never move
        return <strong key={index}>{inlines(node.children)}</strong>;
      case "em":
        // biome-ignore lint/suspicious/noArrayIndexKey: as above
        return <em key={index}>{inlines(node.children)}</em>;
      case "link":
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: as above
          <a key={index} href={node.href} target="_blank" rel="noopener noreferrer external nofollow">
            {inlines(node.children)}
            <span className="fc-visually-hidden"> (opens in a new tab)</span>
          </a>
        );
      default:
        return null;
    }
  });
}

/**
 * Markdown notes, as React elements and never as HTML. The panel's title is
 * the page's second-level heading and the notes sit under a third-level
 * one, so a note's own headings start at the fourth level.
 */
export function Markdown({ source }: { source: string }) {
  const blocks = useMemo(() => parseMarkdown(source), [source]);
  return (
    <div className="fc-markdown">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "heading": {
            const Tag = block.level === 1 ? "h4" : block.level === 2 ? "h5" : "h6";
            // biome-ignore lint/suspicious/noArrayIndexKey: blocks are re-read whole when the text changes
            return <Tag key={index}>{inlines(block.children)}</Tag>;
          }
          case "paragraph":
            // biome-ignore lint/suspicious/noArrayIndexKey: as above
            return <p key={index}>{inlines(block.children)}</p>;
          case "list": {
            const Tag = block.ordered ? "ol" : "ul";
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: as above
              <Tag key={index}>
                {block.items.map((item, itemIndex) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: as above
                  <li key={itemIndex}>{inlines(item)}</li>
                ))}
              </Tag>
            );
          }
          default:
            return null;
        }
      })}
    </div>
  );
}
