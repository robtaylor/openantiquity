import type { CSSProperties } from "react";
import "./Avatar.css";

export interface AvatarProps {
  /** Display name, used for the initials and the accessible name. */
  name: string;
  /** Stable id for the colour. Defaults to the name. */
  handle?: string;
  src?: string;
  size?: number;
}

/** Up to two initials. Generated names such as "QuietBarrow42" split on their capitals. */
export function initialsOf(name: string): string {
  const words = name
    .trim()
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .split(/[\s._-]+/)
    .filter((word) => /\p{L}/u.test(word));
  const first = words[0]?.match(/\p{L}/u)?.[0] ?? "?";
  const second = words.length > 1 ? (words[words.length - 1]?.match(/\p{L}/u)?.[0] ?? "") : "";
  return (first + second).toUpperCase();
}

/** A hue from 0 to 359 that is always the same for the same text. */
export function hueOf(text: string): number {
  let hash = 0;
  for (const char of text) hash = (hash * 31 + (char.codePointAt(0) ?? 0)) % 360;
  return hash;
}

export function Avatar({ name, handle, src, size = 32 }: AvatarProps) {
  const style = { "--avatar-size": `${size}px`, "--avatar-hue": hueOf(handle ?? name) } as CSSProperties;
  return (
    <span className="fc-avatar" style={style} role="img" aria-label={name}>
      {src ? <img src={src} alt="" /> : initialsOf(name)}
    </span>
  );
}
