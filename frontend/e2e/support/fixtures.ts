import { test as base, type ConsoleMessage, expect } from "@playwright/test";
import { type NetworkLog, stubNetwork } from "./network.js";

/**
 * What counts against a test. "all": uncaught errors, console errors, and the
 * map's own warnings, which it prints for a failing overlay or a layer the
 * tiles do not have. "page-errors": uncaught errors only, for tests that make
 * things fail on purpose and so expect the warnings.
 */
export type PageProblems = "all" | "page-errors";

/**
 * A browser logs every 4xx answer as a console error, and `GET /auth/me`
 * answers 401 to everyone who isn't signed in. That one is expected.
 */
function isSignedOutAnswer(message: ConsoleMessage): boolean {
  const { url } = message.location();
  return (
    message.text().startsWith("Failed to load resource") &&
    message.text().includes("401") &&
    url !== "" &&
    new URL(url).pathname === "/api/v1/auth/me"
  );
}

interface Fixtures {
  pageProblems: PageProblems;
  /** The network stubs, set up before every test. A test that lets a request past them fails. */
  network: NetworkLog;
}

/**
 * Playwright's `test`, with every request that would leave the dev server
 * answered by `stubNetwork`, and the page watched for problems. Both are
 * checked when the test ends.
 */
export const test = base.extend<Fixtures>({
  pageProblems: ["all", { option: true }],
  network: [
    async ({ page, pageProblems }, use) => {
      const network = await stubNetwork(page);
      const problems: string[] = [];
      page.on("pageerror", (error) =>
        problems.push(pageProblems === "all" ? `page error: ${error.message}` : (error.stack ?? error.message)),
      );
      if (pageProblems === "all") {
        page.on("console", (message) => {
          if (message.type() === "error" && !isSignedOutAnswer(message)) {
            problems.push(`console error: ${message.text()}`);
          }
          if (message.type() === "warning" && message.text().startsWith("[map]")) {
            problems.push(`map warning: ${message.text()}`);
          }
        });
      }
      await use(network);
      expect(network.unexpected, "requests that escaped the stubs").toEqual([]);
      expect(problems, "errors in the page").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
