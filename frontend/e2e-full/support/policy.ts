import type { Page } from "@playwright/test";

/**
 * Watching for `Content-Security-Policy` violations in a full-stack test.
 * The browser fires `securitypolicyviolation` in the document for each one,
 * and Chrome also writes a console line; both are collected into the running
 * test's list (`collectViolations`), which the test fixture checks is empty.
 */

const VIOLATION_PREFIX = "[csp-violation]";
let sink: string[] | null = null;

/** Where violations go while a test runs, or null between tests. */
export function collectViolations(into: string[] | null): void {
  sink = into;
}

function record(text: string): void {
  // A page another person's browser keeps open after its test can still report one; it belongs to no test.
  if (sink === null) console.warn(`A policy violation after its test ended: ${text}`);
  else sink.push(text);
}

/** Collect every policy violation in `page`, and in each page its context opens later. */
export async function watchPolicy(page: Page): Promise<void> {
  await page.context().addInitScript((prefix: string) => {
    document.addEventListener("securitypolicyviolation", (event) => {
      const where = event.sourceFile ? ` in ${event.sourceFile}:${event.lineNumber}` : "";
      console.error(`${prefix} ${event.effectiveDirective} blocked ${event.blockedURI || "inline"}${where}`);
    });
  }, VIOLATION_PREFIX);
  const listen = (target: Page): void => {
    target.on("console", (message) => {
      const text = message.text();
      if (text.startsWith(VIOLATION_PREFIX) || /Content Security Policy/i.test(text)) record(text);
    });
  };
  listen(page);
  page.context().on("page", listen);
}
