import { useEffect, useState } from "react";

/**
 * `value`, once it has stayed the same for `delay` milliseconds. Until the
 * first value has settled this returns `initial`, or the value at mount when
 * no `initial` is given. Compare by identity, so pass text or numbers, not
 * an object made afresh on every render.
 */
export function useDebounced<T>(value: T, delay: number, initial: T = value): T {
  const [settled, setSettled] = useState<T>(initial);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}
