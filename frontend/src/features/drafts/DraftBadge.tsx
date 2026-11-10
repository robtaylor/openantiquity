import { CloudOff } from "lucide-react";
import "./drafts.css";

/**
 * The "not saved yet" badge, for anything shown from a draft: a finding
 * marked while signed out, an answer, a scanned square.
 */
export function DraftBadge() {
  return (
    <span className="fc-draft-badge" title="Kept only in this browser until you sign in and save it">
      <CloudOff size={14} aria-hidden />
      Not saved yet
    </span>
  );
}
