import { readFileSync } from "node:fs";
import { expect } from "@playwright/test";
import { BACKEND_LOG } from "./env.js";

/** The backend writes each email as `Email to <address>: <subject>` followed by the body. */
const LINK = /https?:\/\/\S+\/signin\/email\S*#token=[\w-]+/;

function readLog(): string {
  try {
    return readFileSync(BACKEND_LOG, "utf8");
  } catch {
    return "";
  }
}

/**
 * The sign-in link most recently emailed to `address`, read from the log
 * mailer's output. Waits for it to arrive, and never returns an earlier link
 * than `after` (a link already read).
 */
export async function emailedLink(address: string, after: string | null = null): Promise<string> {
  let link: string | null = null;
  await expect
    .poll(
      () => {
        const log = readLog();
        const start = log.lastIndexOf(`Email to ${address}:`);
        const found = start === -1 ? null : (LINK.exec(log.slice(start))?.[0] ?? null);
        link = found !== null && found !== after ? found : null;
        return link;
      },
      { message: `an emailed link for ${address}`, timeout: 15_000 },
    )
    .not.toBeNull();
  if (link === null) throw new Error(`No link was emailed to ${address}`);
  return link;
}
