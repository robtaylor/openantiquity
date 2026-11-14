/** Where OpenAntiquity's code and its issues are kept: a public repository on GitHub (Decision 0026). */

export const SOURCE_URL = "https://github.com/robtaylor/openantiquity";
export const ISSUES_URL = `${SOURCE_URL}/issues`;
/** GitHub's form for a new issue, which takes `title` and `body` from its address. */
export const NEW_ISSUE_URL = `${ISSUES_URL}/new`;

/** A commit as it is usually shown: its first seven characters. */
export function shortCommit(commit: string): string {
  return commit.slice(0, 7);
}
