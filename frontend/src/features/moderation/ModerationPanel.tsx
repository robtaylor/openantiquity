import { CircleUser, ShieldOff, Unplug } from "lucide-react";
import type { ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { TabPanel, Tabs } from "../../ui/Tabs.js";
import { useAccountUi } from "../account/requireAccount.js";
import { useSession } from "../account/session.js";
import { PhotoQueue } from "../photos/PhotoQueue.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { ActionLog } from "./ActionLog.js";
import { isModerator, mayApprovePhotos } from "./access.js";
import { Members } from "./Members.js";
import { ReportQueue } from "./ReportQueue.js";
import "./moderation.css";

export const MOD_PATH = "/mod";
export const MOD_ROUTE = `${MOD_PATH}/:section?`;

type SectionId = "reports" | "photos" | "members" | "log";

const SECTIONS: Array<{ id: SectionId; label: string; moderatorsOnly: boolean }> = [
  { id: "reports", label: "Reports", moderatorsOnly: true },
  { id: "photos", label: "Photos", moderatorsOnly: false },
  { id: "members", label: "Members", moderatorsOnly: true },
  { id: "log", label: "Log", moderatorsOnly: true },
];

/** The sections this role may open, in order. Trusted members and archaeologists get the photo queue alone. */
export function sectionsFor(role: string | null): SectionId[] {
  if (isModerator(role)) return SECTIONS.map((section) => section.id);
  return mayApprovePhotos(role) ? ["photos"] : [];
}

function sectionPath(id: SectionId): string {
  return id === "reports" ? MOD_PATH : `${MOD_PATH}/${id}`;
}

function Frame({ title = "Moderation", children }: { title?: string; children: ReactNode }) {
  return (
    <PanelFrame panelKey={MOD_PATH} title={title}>
      {children}
    </PanelFrame>
  );
}

/**
 * `/mod`: moderation, for the people whose role allows it. Moderators get
 * the report queue, the photo queue, the members who could be trusted, and
 * the log; trusted members and archaeologists get the photo queue alone.
 * Everyone else is told it isn't for them. Every part needs the welcome step
 * finished, because that is where the terms are accepted (Decision 0013).
 */
export function ModerationPanel({ meta }: { meta: Meta }) {
  const session = useSession();
  const navigate = useNavigate();
  const { section } = useParams();
  const allowed = sectionsFor(session.role);
  const asked = (section ?? (allowed[0] === "photos" ? "photos" : "reports")) as SectionId;
  const title = allowed.length === 1 ? "Photos to approve" : "Moderation";
  useDocumentTitle(title);

  if (session.status === "loading") {
    return (
      <Frame>
        <div role="status">
          <span className="fc-visually-hidden">Checking who you are</span>
          <Skeleton lines={3} />
        </div>
      </Frame>
    );
  }
  if (session.status === "unknown") {
    return (
      <Frame>
        <EmptyState
          tone="error"
          icon={<Unplug size={22} />}
          title="We couldn't check who you are"
          action={
            <Button variant="primary" onClick={session.refetch}>
              Try again
            </Button>
          }
        >
          <p>{session.error?.message ?? "The server didn't answer."}</p>
        </EmptyState>
      </Frame>
    );
  }
  if (session.status !== "signed-in") {
    return (
      <Frame>
        <EmptyState
          icon={<CircleUser size={22} />}
          title="Sign in to moderate"
          action={
            <Button variant="primary" onClick={() => useAccountUi.getState().openSignIn()}>
              Sign in
            </Button>
          }
        >
          <p>This part of Open Antiquity is for moderators and trusted members.</p>
        </EmptyState>
      </Frame>
    );
  }
  if (allowed.length === 0) {
    return (
      <Frame>
        <EmptyState
          icon={<ShieldOff size={22} />}
          title="This part is for moderators"
          action={
            <Link className="fc-button fc-button--secondary fc-button--md" to="/">
              Back to the map
            </Link>
          }
        >
          <p>If something on the map looks wrong, use its Report button and a moderator will look at it.</p>
        </EmptyState>
      </Frame>
    );
  }
  if (session.needsWelcome) {
    return (
      <Frame title={title}>
        <EmptyState
          icon={<CircleUser size={22} />}
          title="Finish joining first"
          action={
            <Button variant="primary" onClick={() => useAccountUi.getState().openWelcome()}>
              Finish joining
            </Button>
          }
        >
          <p>Moderating means acting under the contributor terms, which you accept when you finish joining.</p>
        </EmptyState>
      </Frame>
    );
  }
  if (!allowed.includes(asked)) return <Navigate to={sectionPath(allowed[0] ?? "photos")} replace />;

  const tabs = SECTIONS.filter((entry) => allowed.includes(entry.id)).map((entry) => ({
    id: entry.id,
    label: entry.label,
  }));
  const body = (
    <div className="fc-mod__section">
      {asked === "reports" ? <ReportQueue meta={meta} /> : null}
      {asked === "photos" ? <PhotoQueue /> : null}
      {asked === "members" ? <Members meta={meta} /> : null}
      {asked === "log" ? <ActionLog /> : null}
    </div>
  );
  return (
    <Frame title={title}>
      <div className="fc-mod">
        {tabs.length > 1 ? (
          <Tabs
            label="Moderation"
            idPrefix="fc-mod"
            tabs={tabs}
            value={asked}
            onChange={(id) => navigate(sectionPath(id as SectionId))}
          />
        ) : null}
        {tabs.length > 1 ? (
          <TabPanel idPrefix="fc-mod" id={asked}>
            {body}
          </TabPanel>
        ) : (
          body
        )}
      </div>
    </Frame>
  );
}
