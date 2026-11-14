/**
 * "Remove the marking", at `/mod/markings/:publicId`: an admin takes back
 * an orphaned marking's shape, by putting back an earlier one or taking it
 * away so the finding is a spot (Decision 0040). Only the finding's own
 * `actions.remove_marking` opens it, and only then are the earlier shapes
 * asked for (`GET /mod/findings/{id}/shapes`, admins only, Decision 0041).
 * Anyone else, a moderator included, is shown what a page that isn't theirs
 * shows, and nothing is asked for.
 *
 * The chosen shape is drawn as a dashed band beneath the finding's own,
 * which the map draws solid in its tier's colour (`dashedShape.ts`). The finding, its second looks and its
 * evidence stay, and the reason goes to the moderation log.
 */

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Eraser, ShieldOff } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { isTransient } from "../../api/client.js";
import { useMainMap } from "../../map/mainMap.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { toast } from "../../ui/toastStore.js";
import { isShapeChanged } from "../finding/api.js";
import { dashedLayers, useDashedShapeOnMap } from "../finding/dashedShape.js";
import { formatDate } from "../finding/describe.js";
import { reasonOf } from "../finding/feedback.js";
import { findingPageKeys } from "../finding/keys.js";
import { frameExtent, whenStageSettled } from "../finding/mapView.js";
import { refreshAfterMarking } from "../finding/refreshLists.js";
import type { FindingDetail } from "../finding/types.js";
import { refreshFindingLists, useFinding } from "../finding/useFinding.js";
import { findingPath } from "../findings/selection.js";
import type { GeoJSONGeometry } from "../findings/types.js";
import { type Path, pathGeometry, plainPoints } from "../mark/path.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { type EarlierShape, fetchEarlierShapes, putMarking } from "./api.js";
import { moderationKeys } from "./keys.js";
import { removeMarkingPath } from "./paths.js";
import "./moderation.css";

export const RESTORE_SOURCE = "marking-restore";
export const RESTORE_LAYERS = dashedLayers(RESTORE_SOURCE);

const TAKEN_BACK = "The marking is taken back. The finding, its second looks and its evidence stay.";

/** What the change after an earlier shape did, as "Then … changed it". */
const CHANGED: Record<EarlierShape["kind"], string> = {
  drawn: "drew a line or shape",
  extended: "drew it further",
  reshaped: "reshaped it",
  closed: "closed it into a shape",
  opened: "opened it out into a line",
  removed: "took its shape away",
};

/** The choice: the revision to put back, or "none" to take the shape away. */
type Choice = number | "none";

function pathOf(shape: EarlierShape): Path | null {
  return shape.path_before ? { closed: shape.path_before.closed, points: plainPoints(shape.path_before.points) } : null;
}

function Removal({ finding }: { finding: FindingDetail }) {
  const map = useMainMap();
  const client = useQueryClient();
  const navigate = useNavigate();
  const groupId = useId();
  const [choice, setChoice] = useState<Choice | null>(null);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [reasonProblem, setReasonProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const query = useInfiniteQuery({
    queryKey: moderationKeys.shapes(finding.public_id),
    queryFn: ({ pageParam, signal }) => fetchEarlierShapes(finding.public_id, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? null,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });
  // An earlier shape that was only a spot is the same as taking the shape away, which is offered on its own.
  const earlier = (query.data?.pages.flatMap((page) => page.items) ?? []).filter((item) => item.path_before !== null);
  const chosen = typeof choice === "number" ? earlier.find((item) => item.revision - 1 === choice) : undefined;
  const chosenPath = useMemo(() => (chosen ? pathOf(chosen) : null), [chosen]);
  const geometry = useMemo(
    () => (chosenPath ? (pathGeometry(chosenPath) as GeoJSONGeometry | null) : null),
    [chosenPath],
  );
  useDashedShapeOnMap(map, RESTORE_SOURCE, RESTORE_LAYERS, geometry);

  // The marking as it is now is framed once, so the earlier shapes are weighed against it.
  const framed = useRef(false);
  useEffect(() => {
    if (framed.current) return;
    framed.current = true;
    const points = (finding.location.path?.points ?? []).map(({ lon, lat }) => [lon, lat] as const);
    return whenStageSettled(() => frameExtent(points, { keepOwnView: finding.public_id }));
  }, [finding]);

  function choose(next: Choice): void {
    setChoice(next);
    setProblem(null);
    const item = typeof next === "number" ? earlier.find((entry) => entry.revision - 1 === next) : undefined;
    // The shape chosen and the marking as it is now, framed together so the two can be compared.
    const points = [...(item?.path_before?.points ?? []), ...(finding.location.path?.points ?? [])].map(
      ({ lon, lat }) => [lon, lat] as const,
    );
    whenStageSettled(() => frameExtent(points));
  }

  async function submit(): Promise<void> {
    if (saving) return;
    if (choice === null) {
      setProblem("Choose an earlier shape to put back, or no line or shape.");
      return;
    }
    if (!reason.trim()) {
      setReasonProblem("Say why, for the moderation log.");
      return;
    }
    setSaving(true);
    setProblem(null);
    try {
      const updated = await putMarking(
        finding.public_id,
        choice === "none" ? null : choice,
        finding.location.shape.revision ?? 0,
        reason.trim(),
      );
      client.setQueryData(findingPageKeys.detail(updated.public_id), updated);
      refreshFindingLists(client);
      void client.invalidateQueries({ queryKey: moderationKeys.shapes(finding.public_id) });
      refreshAfterMarking(client, { orphaned: true });
      navigate(findingPath(updated.public_id), { replace: true });
      toast(TAKEN_BACK, { kind: "success" });
    } catch (error) {
      if (isShapeChanged(error)) {
        setChoice(null);
        void client.invalidateQueries({ queryKey: findingPageKeys.detail(finding.public_id) });
        void client.invalidateQueries({ queryKey: moderationKeys.shapes(finding.public_id) });
        setProblem("The shape was changed while you were looking. Choose again from its shapes as they are now.");
      } else setProblem(reasonOf(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fc-removal">
      <p>
        Put its line or shape back to an earlier one, or take it away so the finding is a spot at its point. The
        finding, its second looks and its evidence stay. Its point may move to lie by the shape put back.
      </p>
      <p className="fc-finding__hint">
        The shape you choose is drawn as a dashed band beneath the marking as it is now, so you see both.
      </p>
      {query.isPending ? (
        <div role="status">
          <span className="fc-visually-hidden">Loading its earlier shapes</span>
          <Skeleton lines={3} />
        </div>
      ) : query.isError && earlier.length === 0 ? (
        <EmptyState
          tone="error"
          title="Its earlier shapes couldn't be loaded"
          action={
            <Button variant="primary" onClick={() => void query.refetch()}>
              Try again
            </Button>
          }
        >
          <p>{query.error.message}</p>
        </EmptyState>
      ) : (
        <>
          <p id={groupId} className="fc-removal__legend">
            Put it back to
          </p>
          <div role="radiogroup" aria-labelledby={groupId} className="fc-removal__choices">
            {earlier.map((item) => {
              const id = `${groupId}-${item.revision}`;
              return (
                <label key={item.revision} htmlFor={id} className="fc-removal__choice" data-disabled={!item.restorable}>
                  <input
                    id={id}
                    type="radio"
                    name={groupId}
                    disabled={!item.restorable}
                    checked={choice === item.revision - 1}
                    onChange={() => choose(item.revision - 1)}
                  />
                  <span>
                    <strong>As it was until {formatDate(item.created_at)}</strong>
                    <span className="fc-removal__detail">
                      {" "}
                      Then {item.by.display_name} {CHANGED[item.kind]}.{item.restorable ? "" : " It can't be put back."}
                    </span>
                  </span>
                </label>
              );
            })}
            <label htmlFor={`${groupId}-none`} className="fc-removal__choice">
              <input
                id={`${groupId}-none`}
                type="radio"
                name={groupId}
                checked={choice === "none"}
                onChange={() => choose("none")}
              />
              <span>
                <strong>No line or shape</strong>
                <span className="fc-removal__detail"> The finding is a spot at its point.</span>
              </span>
            </label>
          </div>
          {query.hasNextPage ? (
            <Button size="sm" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
              {query.isFetchingNextPage ? "Loading…" : "Show older shapes"}
            </Button>
          ) : null}
        </>
      )}
      <Field
        label="Why"
        hint="Kept in the moderation log, which only moderators read."
        error={reasonProblem ?? undefined}
      >
        {(control) => (
          <textarea
            {...control}
            className="fc-input"
            rows={2}
            maxLength={500}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
              setReasonProblem(null);
            }}
          />
        )}
      </Field>
      {problem ? (
        <p className="fc-field__error" role="alert">
          {problem}
        </p>
      ) : null}
      <div className="fc-removal__actions">
        <Button
          variant="danger"
          icon={<Eraser size={16} aria-hidden />}
          aria-disabled={saving || undefined}
          onClick={() => void submit()}
        >
          {saving ? "Saving…" : choice === "none" ? "Remove the marking" : "Put this shape back"}
        </Button>
        <Button variant="ghost" onClick={() => navigate(findingPath(finding.public_id))}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/** For anyone the server doesn't let remove this marking. An admin is told why; nobody else is told anything of it. */
function NotYours({ finding }: { finding: FindingDetail }) {
  const navigate = useNavigate();
  const back = <Button onClick={() => navigate(findingPath(finding.public_id))}>Back to the finding</Button>;
  if (finding.actions.remove_marking.reason === "not_orphaned") {
    return (
      <EmptyState icon={<ShieldOff size={22} />} title="It has a keeper" action={back}>
        <p>Only a marking whose keeper's account is deleted or banned can be taken back. A moderator can hide it.</p>
      </EmptyState>
    );
  }
  return (
    <EmptyState icon={<ShieldOff size={22} />} title="This part is for admins" action={back}>
      <p>If something on the map looks wrong, use its Report button and a moderator will look at it.</p>
    </EmptyState>
  );
}

export function RemoveMarkingPanel() {
  const { publicId = "" } = useParams();
  const navigate = useNavigate();
  const query = useFinding(publicId);
  const finding = query.data;
  useDocumentTitle("Remove the marking");

  return (
    <PanelFrame
      panelKey={removeMarkingPath(publicId)}
      title="Remove the marking"
      subtitle={finding?.title}
      onClose={() => navigate(findingPath(publicId))}
    >
      {finding ? (
        finding.actions.remove_marking.allowed ? (
          <Removal finding={finding} />
        ) : (
          <NotYours finding={finding} />
        )
      ) : query.isError ? (
        <EmptyState
          tone="error"
          title="This finding couldn't be loaded"
          action={
            <Button variant="primary" onClick={() => void query.refetch()}>
              Try again
            </Button>
          }
        >
          <p>{query.error.message}</p>
        </EmptyState>
      ) : (
        <div role="status">
          <span className="fc-visually-hidden">Loading the finding</span>
          <Skeleton lines={3} />
        </div>
      )}
    </PanelFrame>
  );
}
