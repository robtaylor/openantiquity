/**
 * The handle rule the backend applies (`fieldclub.auth.handles`), checked in
 * the browser so a slip is caught before anything is sent. The server checks
 * again and also refuses reserved names.
 */
export const HANDLE_PATTERN = /^[A-Za-z][A-Za-z0-9_-]{2,29}$/;
export const HANDLE_MAX_LENGTH = 30;
export const HANDLE_RULE = "3 to 30 letters, numbers, hyphens or underscores, starting with a letter.";

/** What to say about a handle that doesn't fit the rule. */
export const HANDLE_RULE_MESSAGE = `A name is ${HANDLE_RULE.toLowerCase()}`;
