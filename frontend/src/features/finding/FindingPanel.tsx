import { useQueryClient } from "@tanstack/react-query";
import { MapPinned, Unplug } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { scrollBehaviour } from "../../ui/motion.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { useSession } from "../account/session.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { Discussion } from "./Discussion.js";
import { changeMessage, positionOf, type StepAction, type Viewer } from "./describe.js";
import { EvidenceSection, type OpenForm, openForm } from "./evidence/EvidenceSection.js";
import { RecordSuggestions } from "./evidence/RecordSuggestions.js";
import { FindingHead } from "./FindingHead.js";
import { findingPageKeys } from "./keys.js";
import { useFindingOnMap } from "./mapView.js";
import { NextSteps } from "./NextSteps.js";
import { Answers, Credits } from "./People.js";
import { FollowUpTimelineSlot, MentionsSlot } from "./Slots.js";
import { SecondLook } from "./secondLook/SecondLook.js";
import { copyLink, Tools } from "./Tools.js";
import type { FindingDetail, Reveal } from "./types.js";
import { isNotFound, useApplyFinding, useFinding } from "./useFinding.js";
import "./finding.css";

function BackToExplore() {
  return (
    <Link className="fc-button fc-button--secondary fc-button--md" to="/">
      Back to Explore
    </Link>
  );
}

/**
 * Bring a part of the page into view and give it focus. On a phone the sheet
 * opens to `stop` first: fully for a form, but only half-way for a second
 * look, because the person needs the map above the sheet to answer it.
 */
function useReveal() {
  const environment = usePanelEnvironment();
  return useCallback(
    (find: () => HTMLElement | null, stop: "half" | "full" = "full") => {
      // A sheet already open fully stays so.
      if (environment.isPhone && environment.stop !== "full" && environment.stop !== stop) environment.setStop(stop);
      // After the render that opens the form or the sheet.
      requestAnimationFrame(() => {
        const element = find();
        element?.scrollIntoView?.({ block: "start", behavior: scrollBehaviour() });
        element?.focus({ preventScroll: true });
      });
    },
    [environment],
  );
}

/**
 * Says what just happened to the finding's step or state when it changes
 * while the page is open, whatever changed it: an answer, evidence, a vote,
 * or someone else's work picked up on a refresh.
 */
function useChangeMessage(meta: Meta, finding: FindingDetail): string | null {
  const last = useRef({ publicId: finding.public_id, tier: finding.assessment.tier, state: finding.assessment.state });
  const [message, setMessage] = useState<string | null>(null);
  const { public_id: publicId } = finding;
  const { tier, state } = finding.assessment;
  useEffect(() => {
    const before = last.current;
    last.current = { publicId, tier, state };
    if (before.publicId !== publicId) {
      setMessage(null);
      return;
    }
    const said = changeMessage(meta, before, { tier, state });
    if (said) setMessage(said);
  }, [meta, publicId, tier, state]);
  return message;
}

function FindingPage({ meta, finding }: { meta: Meta; finding: FindingDetail }) {
  const session = useSession();
  const client = useQueryClient();
  const apply = useApplyFinding();
  const reveal = useReveal();
  const secondLook = useRef<HTMLElement>(null);
  const [form, setForm] = useState<OpenForm | null>(null);
  const viewer: Viewer = {
    ready: session.ready,
    signedIn: session.status === "signed-in",
    handle: session.me?.handle ?? null,
    role: session.role,
  };
  const position = positionOf(finding, viewer);
  const change = useChangeMessage(meta, finding);
  useFindingOnMap(finding);

  const refresh = useCallback(
    () => void client.invalidateQueries({ queryKey: findingPageKeys.detail(finding.public_id) }),
    [client, finding.public_id],
  );
  const onRevealed = useCallback((answered: Reveal) => apply(answered.finding), [apply]);

  function openEvidence(next: OpenForm): void {
    setForm(next);
    reveal(() => document.querySelector<HTMLElement>(".fc-evidence-add"));
  }

  function act(action: StepAction): void {
    switch (action.kind) {
      case "answer":
        reveal(() => secondLook.current, "half");
        return;
      case "share":
        void copyLink(finding.public_id);
        return;
      case "endorse": {
        const [first] = action.evidenceIds;
        reveal(() => document.getElementById(`evidence-${first}`));
        return;
      }
      case "evidence":
        openEvidence(openForm(action.evidenceKind));
        return;
    }
  }

  const linked = finding.evidence.some((item) => item.kind === "record_link");
  const displayName = session.me?.display_name ?? "You";

  return (
    <div className="fc-finding">
      <FindingHead meta={meta} finding={finding} signedIn={viewer.signedIn} change={change} />
      <NextSteps meta={meta} finding={finding} position={position} onAction={act} />
      <SecondLook
        ref={secondLook}
        meta={meta}
        finding={finding}
        position={position}
        ready={viewer.ready}
        onRevealed={onRevealed}
        onRefresh={refresh}
      />
      {!linked && position.seesExact && position.takesWork && form === null ? (
        <RecordSuggestions
          meta={meta}
          publicId={finding.public_id}
          onLink={(recordId) => openEvidence(openForm("record_link", { recordId: String(recordId) }))}
        />
      ) : null}
      <EvidenceSection
        meta={meta}
        finding={finding}
        position={position}
        viewer={viewer}
        displayName={displayName}
        youngContributor={session.me?.age_band === "16_17"}
        form={form}
        setForm={setForm}
        onApplied={apply}
      />
      <Answers meta={meta} finding={finding} />
      <Credits finding={finding} />
      <MentionsSlot finding={finding} />
      <FollowUpTimelineSlot finding={finding} />
      <Discussion finding={finding} viewer={viewer} displayName={displayName} />
      <Tools meta={meta} finding={finding} position={position} onApplied={apply} />
    </div>
  );
}

/**
 * A finding's page, at `/f/:id`: what it is and how sure people are, what
 * would move it up, a second look, the evidence, the discussion, and the
 * finder's own controls. Opening it moves the map to the finding. Loading,
 * not-found and failed states each say what to do next.
 */
export function FindingPanel({ meta }: { meta: Meta }) {
  const { id = "" } = useParams();
  const query = useFinding(id);
  const panelKey = `/f/${id}`;
  useDocumentTitle(query.data?.title ?? "Finding");

  if (query.data) {
    return (
      <PanelFrame panelKey={panelKey} title={query.data.title}>
        <FindingPage meta={meta} finding={query.data} />
      </PanelFrame>
    );
  }
  if (query.isError && isNotFound(query.error)) {
    return (
      <PanelFrame panelKey={panelKey} title="Finding not found">
        <EmptyState
          icon={<MapPinned size={22} />}
          title="There's no finding at this address"
          action={<BackToExplore />}
        >
          <p>
            The link may be mistyped, or a moderator may have hidden the finding. The findings in view are listed in
            Explore.
          </p>
        </EmptyState>
      </PanelFrame>
    );
  }
  if (query.isError) {
    return (
      <PanelFrame panelKey={panelKey} title="Finding">
        <EmptyState
          tone="error"
          icon={<Unplug size={22} />}
          title="This finding couldn't be loaded"
          action={
            <Button variant="primary" onClick={() => void query.refetch()}>
              Try again
            </Button>
          }
        >
          <p>{query.error.message}</p>
        </EmptyState>
      </PanelFrame>
    );
  }
  return (
    <PanelFrame panelKey={panelKey} title="Finding">
      <div className="fc-finding" role="status">
        <span className="fc-visually-hidden">Loading the finding</span>
        <Skeleton height={26} width="45%" />
        <Skeleton height={10} />
        <Skeleton lines={4} />
        <Skeleton lines={3} />
      </div>
    </PanelFrame>
  );
}
