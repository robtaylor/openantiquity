/**
 * Text from other people's catalogues, made fit to show.
 */

const ENTITIES: Readonly<Record<string, string>> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
};

const ENTITY = /&(?:#(\d{1,7})|#[xX]([0-9a-fA-F]{1,6})|([a-zA-Z]+));/g;

function fromCodePoint(code: number): string | null {
  // Control characters and surrogates are never wanted in a name.
  if (!Number.isInteger(code) || code < 0x20 || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) return null;
  return String.fromCodePoint(code);
}

/**
 * Some sources send names with HTML entities left in, such as
 * "Monitoring &amp; Recording". This turns the common ones back into the
 * characters they stand for, in one pass, so "&amp;lt;" becomes "&lt;" and
 * no further. The result is only ever shown as text, never as markup.
 * Anything it does not know is left as it was.
 */
export function decodeEntities(text: string): string {
  if (!text.includes("&")) return text;
  return text.replace(ENTITY, (whole, decimal?: string, hex?: string, name?: string) => {
    if (decimal !== undefined) return fromCodePoint(Number.parseInt(decimal, 10)) ?? whole;
    if (hex !== undefined) return fromCodePoint(Number.parseInt(hex, 16)) ?? whole;
    return (name !== undefined ? ENTITIES[name] : undefined) ?? whole;
  });
}
