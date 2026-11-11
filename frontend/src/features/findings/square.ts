/**
 * How a one-kilometre square is written for people. The API sends it run
 * together, "SU1069", which is hard to read beside a grid reference such as
 * "SU 1025 6996", so it is shown spaced the same way: "SU 10 69".
 */

const SQUARE = /^([A-Z]{2})\s*(\d{2})\s*(\d{2})$/;

/** "SU1069" as "SU 10 69". Anything that isn't a square's reference comes back as it was. */
export function squareWords(ref: string): string {
  const match = SQUARE.exec(ref.trim());
  return match ? `${match[1]} ${match[2]} ${match[3]}` : ref;
}

interface Where {
  obscured: boolean;
  square?: string | null;
  grid_ref: string | null;
}

/** The reference to show for where a finding is: its square, spaced, for a viewer sent only that. */
export function whereRef({ obscured, square, grid_ref }: Where): string | null {
  if (!obscured) return grid_ref;
  const ref = square ?? grid_ref;
  return ref === null ? null : squareWords(ref);
}
