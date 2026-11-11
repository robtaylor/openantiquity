/**
 * When something happened, in words: "just now", "5 minutes ago", "yesterday",
 * and the date itself after a week.
 */

import { useEffect, useState } from "react";
import { formatDate } from "../finding/describe.js";

const RELATIVE = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" });
const FULL = new Intl.DateTimeFormat("en-GB", { dateStyle: "long", timeStyle: "short" });

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export function whenWords(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const ago = now - then;
  if (ago < MINUTE) return "just now";
  if (ago < HOUR) return RELATIVE.format(-Math.floor(ago / MINUTE), "minute");
  if (ago < DAY) return RELATIVE.format(-Math.floor(ago / HOUR), "hour");
  if (ago < 7 * DAY) return RELATIVE.format(-Math.floor(ago / DAY), "day");
  return formatDate(iso);
}

/** The exact time, for a tooltip. */
export function fullTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : FULL.format(date);
}

/** The time now, a minute at a time, so "5 minutes ago" keeps up. */
export function useNow(every = 60_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), every);
    return () => clearInterval(timer);
  }, [every]);
  return now;
}
