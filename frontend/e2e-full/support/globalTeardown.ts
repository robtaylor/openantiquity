import { database } from "./env.js";

/** After the servers stop: the database goes. */
export default function globalTeardown(): void {
  database("drop");
}
