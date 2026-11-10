import { CircleAlert, Info } from "lucide-react";
import type { ReactNode } from "react";

/** A boxed message inside a sheet or the account page: what happened, in a sentence or two. */
export function Notice({ tone, title, children }: { tone: "info" | "error"; title: string; children?: ReactNode }) {
  const Icon = tone === "error" ? CircleAlert : Info;
  return (
    <div className={`fc-account-notice fc-account-notice--${tone}`} role={tone === "error" ? "alert" : "status"}>
      <Icon size={18} aria-hidden />
      <div>
        <strong className="fc-account-notice__title">{title}</strong>
        {children}
      </div>
    </div>
  );
}
