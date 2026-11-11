import { Link } from "react-router";
import { MOD_PATH, sectionsFor } from "./ModerationPanel.js";

/** The way into `/mod`, on the account page, for the people whose role allows it, and nobody else. */
export function ModerationLink({ role }: { role: string }) {
  const sections = sectionsFor(role);
  if (sections.length === 0) return null;
  return (
    <Link className="fc-account-link" to={sections.length === 1 ? `${MOD_PATH}/photos` : MOD_PATH}>
      {sections.length === 1 ? "Photos waiting for approval" : "Moderation"}
    </Link>
  );
}
