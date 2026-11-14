import { useQueryClient } from "@tanstack/react-query";
import { MapPinned, Unplug } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { scrollBehaviour } from "../../ui/motion.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { useSession } from "../account/session.js";
import { MentionsSection } from "../mentions/MentionsSection.js";
import { FindingModeration } from "../moderation/FindingModeration.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { Discussion } from "./Discussion.js";
import { changeMessage, positionOf, type StepAction, type Viewer } from "./describe.js";
import { EvidenceSection, type OpenForm, openForm } from "./evidence/EvidenceSection.js";
import { RecordSuggestions } from "./evidence/RecordSuggestions.js";
import { FindingHead } from "./FindingHead.js";
import { OfferToYou } from "./Keeping.js";
import { findingPageKeys } from "./keys.js";
import { panIntoView, useFindingOnMap, whenStageSettled } from "./mapView.js";
import { NextSteps } from "./NextSteps.js";
import { Answers, Credits } from "./People.js";
import { SuggestedChanges } from "./SuggestedChanges.js";
import { SecondLook } from "./secondLook/SecondLook.js";
import { AddedSince } from "./shapeChanges.js";
import { actionForStep, STEP_PARAM, STRAND_PARAM, stepFromAddress } from "./stepLink.js";
import { copyLink, Tools } from "./Tools.js";
import { FollowUpTimeline } from "./timeline/FollowUpTimeline.js";
import type { FindingDetail, Observation, Reveal } from "./types.js";
import { isNotFound, useApplyFinding, useFinding, useOptimisticFinding } from "./useFinding.js";
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
 * look, because the person needs the map above the sheet to answer it, and
 * a sheet pulled up fully would cover the place (docs/UI.md, "Behaviour").
 */
function useReveal() {
  const environment = usePanelEnvironment();
  return useCallback(
    (find: () => HTMLElement | null, stop: "half" | "full" = "full") => {
      // A sheet already open fully stays so for a form. A second look brings it down to half-way.
      const keepFull = environment.stop === "full" && stop === "full";
      if (environment.isPhone && !keepFull && environment.stop !== stop) environment.setStop(stop);
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
  const optimistic = useOptimisticFinding(finding.public_id);
  // The server holds the answer for its detail. Only the person's own answer changes on the page: the tier and
  // the score it moved wait for the reveal, which shows the move.
  const onHeld = useCallback(
    (observation: Observation) =>
      void optimistic((current) => ({
        ...current,
        my_observation: observation,
        actions: { ...current.actions, answer: { allowed: false, reason: "already_answered" } },
      })),
    [optimistic],
  );

  function openEvidence(next: OpenForm): void {
    setForm(next);
    // The evidence section's form, by its heading, which takes focus so the form is read next.
    reveal(() => document.querySelector<HTMLElement>("#fc-evidence .fc-evidence-add__title"));
  }

  function act(action: StepAction): void {
    switch (action.kind) {
      case "answer":
        reveal(() => secondLook.current, "half");
        // Once the sheet has come down, the place is put back in sight if it now covers it.
        if (position.seesExact) whenStageSettled(() => panIntoView([finding.location.lon, finding.location.lat]));
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

  // A link from help wanted names a next step: open its form once, then take it out of the address.
  const [searchParams, setSearchParams] = useSearchParams();
  const stepAsked = useRef(false);
  const sessionKnown = session.status !== "loading";
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs once, when the finding and the session are known
  useEffect(() => {
    const request = stepFromAddress(searchParams);
    if (stepAsked.current || request === null || !sessionKnown) return;
    stepAsked.current = true;
    setSearchParams(
      (params) => {
        params.delete(STEP_PARAM);
        params.delete(STRAND_PARAM);
        return params;
      },
      { replace: true },
    );
    const action = actionForStep(finding, meta, position, request);
    if (action) act(action);
  }, [searchParams, sessionKnown]);

  const linked = finding.evidence.some((item) => item.kind === "record_link");
  const displayName = session.me?.display_name ?? "You";

  return (
    <div className="fc-finding">
      <FindingHead meta={meta} finding={finding} signedIn={viewer.signedIn} change={change} />
      <OfferToYou finding={finding} onApplied={apply} />
      <NextSteps meta={meta} finding={finding} position={position} onAction={act} />
      <AddedSince finding={finding} />
      <SuggestedChanges finding={finding} viewerHandle={viewer.handle} onApplied={apply} />
      <SecondLook
        ref={secondLook}
        meta={meta}
        finding={finding}
        position={position}
        ready={viewer.ready}
        onRevealed={onRevealed}
        onHeld={onHeld}
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
        onOpen={openEvidence}
        onApplied={apply}
      />
      <Answers meta={meta} finding={finding} />
      <Credits finding={finding} />
      <MentionsSection
        meta={meta}
        finding={finding}
        viewer={viewer}
        displayName={displayName}
        mayAdd={position.takesWork && position.mayComment}
      />
      <FollowUpTimeline
        meta={meta}
        finding={finding}
        position={position}
        onAdd={(kindId) => openEvidence(openForm(kindId))}
      />
      <Discussion finding={finding} viewer={viewer} displayName={displayName} mayComment={position.mayComment} />
      <Tools meta={meta} finding={finding} position={position} onApplied={apply} />
      <FindingModeration finding={finding} />
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
