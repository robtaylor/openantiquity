import { wrapDegrees } from "../ui/math.js";

const POINTS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"] as const;

/** The nearest of the eight compass points to a bearing, in words. */
export function compassPoint(degrees: number): string {
  return POINTS[Math.round(wrapDegrees(degrees) / 45) % 8] as string;
}
