import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Where `pnpm e2e:full` runs things. The config, the global set-up and the
 * workers all read these, and the first to load fixes the database name in
 * the environment so the others agree with it.
 */

const here = dirname(fileURLToPath(import.meta.url));
export const FRONTEND_DIR = resolve(here, "../..");
export const BACKEND_DIR = resolve(FRONTEND_DIR, "../backend");

/** The Vite dev server's port. */
export const WEB_PORT = Number(process.env.FIELDCLUB_E2E_PORT ?? 5198);
/** The backend's port. Never 8000, which something else may have. */
export const API_PORT = Number(process.env.FIELDCLUB_E2E_API_PORT ?? 6198);

process.env.FIELDCLUB_E2E_DATABASE ??= `fieldclub_e2e_${process.pid}`;
export const DATABASE = process.env.FIELDCLUB_E2E_DATABASE;

/**
 * Where the backend's output goes. The log mailer writes each emailed
 * sign-in link there, which is how the tests read their "inbox".
 */
export const BACKEND_LOG = join(tmpdir(), `fieldclub-e2e-backend-${API_PORT}.log`);

const SERVER_URL =
  process.env.FIELDCLUB_TEST_SERVER_URL ?? "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub";

export function databaseUrl(): string {
  const url = new URL(SERVER_URL.replace("postgresql+psycopg://", "http://"));
  url.pathname = `/${DATABASE}`;
  return url.href.replace("http://", "postgresql+psycopg://");
}

/** The backend's settings: a test environment with the development sign-in on, and no developer `.env`. */
export function backendEnv(): Record<string, string> {
  return {
    FIELDCLUB_ENV_FILE: "",
    FIELDCLUB_ENV: "test",
    FIELDCLUB_DEV_LOGIN: "true",
    FIELDCLUB_DATABASE_URL: databaseUrl(),
    FIELDCLUB_HOST: "127.0.0.1",
    FIELDCLUB_PORT: String(API_PORT),
    FIELDCLUB_PUBLIC_URL: `http://localhost:${WEB_PORT}`,
    FIELDCLUB_SECRET_KEY: "e2e-full-secret-key",
    FIELDCLUB_RATELIMIT_ENABLED: "false",
    FIELDCLUB_AUTO_CREATE_SCHEMA: "false",
    FIELDCLUB_MAIL_BACKEND: "log",
    FIELDCLUB_VAR_DIR: join(tmpdir(), `fieldclub-e2e-var-${DATABASE}`),
    FIELDCLUB_FRONTEND_DIST: join(tmpdir(), "fieldclub-e2e-no-frontend"),
    // INFO, so the log mailer's links reach BACKEND_LOG.
    FIELDCLUB_LOG_LEVEL: "INFO",
  };
}

const DATABASE_SCRIPT = join(here, "database.py");

/** The shell command that creates the database, for the backend's start command. */
export function createDatabaseCommand(): string {
  return `uv run python ${JSON.stringify(DATABASE_SCRIPT)} create ${DATABASE}`;
}

/** Run `database.py` with the backend's Python. */
export function database(action: "create" | "drop"): void {
  execFileSync("uv", ["run", "--project", BACKEND_DIR, "python", DATABASE_SCRIPT, action, DATABASE], {
    cwd: BACKEND_DIR,
    stdio: "inherit",
    env: { ...process.env, FIELDCLUB_ENV_FILE: "" },
  });
}

/** Put the records spec's sources, records and place in the database, once however often it is called. */
export function seedRecords(): void {
  execFileSync("uv", ["run", "--project", BACKEND_DIR, "python", join(here, "records.py"), DATABASE], {
    cwd: BACKEND_DIR,
    stdio: "inherit",
    env: { ...process.env, FIELDCLUB_ENV_FILE: "" },
  });
}
