import { useInfiniteQuery, useQueries, useQueryClient } from "@tanstack/react-query";
import { Check, Clock, Inbox, Unplug, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { toast } from "../../ui/toastStore.js";
import { useSession } from "../account/session.js";
import { useNow, whenWords } from "../activity/time.js";
import { toastFailure } from "../finding/feedback.js";
import { profilePath } from "../people/api.js";
import { fetchReports, isHideable, type Report, resolveReport, setHidden, type Target } from "./api.js";
import { BanButton } from "./BanButton.js";
import { deadlineReasons, dueWords, KIND_WORDS, queueOrder, reasonLabel } from "./describe.js";
import { HIDING, HideButton } from "./HideButton.js";
import { moderationKeys } from "./keys.js";
import { ReasonDialog } from "./ReasonDialog.js";
import { TargetSummary } from "./TargetSummary.js";

/** How many reports of each reason with a deadline are asked for, to put first. */
const URGENT_LIMIT = 50;

const targetKey = (target: Target) => `${target.kind}:${target.id}`;
const retry = (failureCount: number, error: Error) => failureCount < 1 && isTransient(error);

/**
 * The open reports a moderator may resolve, those with a legal deadline
 * first and marked, then the rest oldest first. The server leaves out the
 * reports they made and those about them or their work.
 */
function useReportQueue(meta: Meta) {
  const reasons = deadlineReasons(meta);
  const urgent = useQueries({
    queries: reasons.map((reason) => ({
      queryKey: moderationKeys.reports(reason),
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchReports({ reason, limit: URGENT_LIMIT }, signal),
      retry,
    })),
  });
  const rest = useInfiniteQuery({
    queryKey: moderationKeys.reports(null),
    queryFn: ({ pageParam, signal }) => fetchReports({ cursor: pageParam }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? null,
    retry,
  });
  const urgentItems = urgent.flatMap((query) => query.data?.items ?? []);
  const restItems = rest.data?.pages.flatMap((page) => page.items) ?? [];
  const failed = [rest, ...urgent].find((query) => query.isError);
  return {
    items: queueOrder(urgentItems, restItems),
    pending: rest.isPending || urgent.some((query) => query.isPending),
    error: failed?.error ?? null,
    hasMore: rest.hasNextPage,
    loadingMore: rest.isFetchingNextPage,
    loadMore: () => void rest.fetchNextPage(),
    retry: () => {
      void rest.refetch();
      for (const query of urgent) void query.refetch();
    },
  };
}

type Resolving = { report: Report; outcome: "upheld" | "dismissed" };

function ResolveDialog({
  resolving,
  mayHide,
  onConfirm,
  onClose,
}: {
  resolving: Resolving;
  mayHide: boolean;
  onConfirm: (note: string, hide: boolean) => void;
  onClose: () => void;
}) {
  const [hide, setHide] = useState(mayHide);
  const { report, outcome } = resolving;
  const others = report.open_on_target - 1;
  const upheld = outcome === "upheld";
  return (
    <ReasonDialog
      title={upheld ? "Uphold this report?" : "Dismiss this report?"}
      confirmLabel={upheld ? (hide && mayHide ? "Uphold and hide" : "Uphold") : "Dismiss"}
      danger={upheld && hide && mayHide}
      label="Note for the log"
      hint="Only moderators read it. The person who reported it isn't told what you decided."
      onConfirm={(note) => onConfirm(note, upheld && hide && mayHide)}
      onClose={onClose}
    >
      <p>
        {upheld ? "You agree it breaks the rules." : "You've looked, and it doesn't break the rules."}
        {others > 0
          ? ` This resolves the ${others} other open ${others === 1 ? "report" : "reports"} on it as well.`
          : ""}
      </p>
      {upheld && mayHide ? (
        <label className="fc-mod-dialog__check">
          <input type="checkbox" checked={hide} onChange={(event) => setHide(event.target.checked)} />
          <span>
            Hide it as well
            <span className="fc-mod-dialog__check-hint">{HIDING[report.target.kind as keyof typeof HIDING]}</span>
          </span>
        </label>
      ) : null}
    </ReasonDialog>
  );
}

function ReportCard({
  meta,
  report,
  hidden,
  now,
  onResolve,
  onHidden,
}: {
  meta: Meta;
  report: Report;
  hidden: boolean;
  now: number;
  onResolve: (outcome: "upheld" | "dismissed") => void;
  onHidden: (hidden: boolean) => void;
}) {
  const target = { ...report.target, hidden };
  const due = dueWords(report, now);
  const live = target.exists && !target.removed;
  return (
    <li className="fc-mod-card" data-due={due ? "true" : undefined}>
      <div className="fc-mod-card__head">
        <span className="fc-mod-card__reason">{reasonLabel(meta, report.reason)}</span>
        {due ? (
          <span className="fc-mod-card__due">
            <Clock size={14} aria-hidden /> Legal deadline · {due}
          </span>
        ) : null}
      </div>
      <p className="fc-mod-card__by">
        <Link to={profilePath(report.reporter.handle)}>{report.reporter.display_name}</Link> reported{" "}
        {KIND_WORDS[report.target.kind]} {whenWords(report.created_at, now)}
        {report.open_on_target > 1 ? ` · ${report.open_on_target} open reports on it` : ""}
      </p>
      {report.note ? (
        <figure className="fc-mod-card__quote">
          <figcaption>Their note</figcaption>
          <blockquote className="fc-mod-card__note" aria-label="The reporter's note">
            {report.note}
          </blockquote>
        </figure>
      ) : null}
      <TargetSummary target={target} />
      <div className="fc-mod-card__actions">
        <Button size="sm" variant="primary" icon={<Check size={14} aria-hidden />} onClick={() => onResolve("upheld")}>
          Uphold
        </Button>
        <Button size="sm" icon={<X size={14} aria-hidden />} onClick={() => onResolve("dismissed")}>
          Dismiss
        </Button>
        {live && isHideable(target.kind) && target.ref !== null ? (
          <HideButton
            kind={target.kind}
            targetRef={target.ref}
            ownerHandle={target.owner?.handle ?? null}
            hidden={hidden}
            onChange={onHidden}
          />
        ) : null}
        {live && target.kind === "user" && target.ref !== null && target.owner ? (
          <BanButton handle={target.ref} targetRole={target.owner.role} banned={false} />
        ) : null}
      </div>
    </li>
  );
}

/**
 * The report queue: each open report with its reason, who made it and
 * their note, and enough of what was reported to decide. Upholding or
 * dismissing needs a note for the log, and resolves every open report on the
 * same target. Upholding offers to hide the target too. Every change shows
 * at once and is put back with a toast if the server refuses.
 */
export function ReportQueue({ meta }: { meta: Meta }) {
  const queue = useReportQueue(meta);
  const session = useSession();
  const client = useQueryClient();
  const now = useNow();
  const [resolved, setResolved] = useState<ReadonlySet<string>>(new Set());
  const [hiddenNow, setHiddenNow] = useState<ReadonlyMap<string, boolean>>(new Map());
  const [resolving, setResolving] = useState<Resolving | null>(null);
  const items = queue.items.filter((report) => !resolved.has(targetKey(report.target)));

  const markResolved = (key: string, gone: boolean) =>
    setResolved((before) => {
      const next = new Set(before);
      if (gone) next.add(key);
      else next.delete(key);
      return next;
    });
  const markHidden = (key: string, hidden: boolean) => setHiddenNow((before) => new Map(before).set(key, hidden));

  function mayHide(report: Report): boolean {
    const { target } = report;
    return (
      isHideable(target.kind) &&
      target.exists &&
      !target.removed &&
      !(hiddenNow.get(targetKey(target)) ?? target.hidden) &&
      target.owner?.handle !== session.me?.handle
    );
  }

  async function resolve(report: Report, outcome: "upheld" | "dismissed", note: string, hide: boolean) {
    const key = targetKey(report.target);
    markResolved(key, true);
    try {
      const { target } = report;
      if (hide && isHideable(target.kind) && target.ref !== null) {
        await setHidden(target.kind, target.ref, true, note);
        markHidden(key, true);
      }
      const done = await resolveReport(report.id, outcome, note);
      toast(
        `${outcome === "upheld" ? "Upheld" : "Dismissed"}${hide ? " and hidden" : ""}.${done.resolved > 1 ? ` That resolved ${done.resolved} reports.` : ""}`,
        { kind: "success" },
      );
      void client.invalidateQueries({ queryKey: moderationKeys.actionsAll });
    } catch (error) {
      markResolved(key, false);
      toastFailure("The report couldn't be resolved.", error);
    }
  }

  if (queue.pending) {
    return (
      <div role="status" className="fc-mod__loading">
        <span className="fc-visually-hidden">Loading the reports</span>
        <Skeleton lines={3} />
        <Skeleton lines={3} />
      </div>
    );
  }
  if (queue.error && items.length === 0) {
    return (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="The reports couldn't be loaded"
        action={
          <Button variant="primary" onClick={queue.retry}>
            Try again
          </Button>
        }
      >
        <p>{queue.error.message}</p>
      </EmptyState>
    );
  }
  if (items.length === 0) {
    return (
      <EmptyState icon={<Inbox size={22} />} title="No reports are waiting">
        <p>
          When someone reports something, it shows here. Reports you made, and reports about you or your work, go to
          another moderator.
        </p>
      </EmptyState>
    );
  }

  return (
    <>
      <p className="fc-mod__hint">
        Reports with a legal deadline come first, marked with when they are due. The rest are oldest first. Upholding or
        dismissing one resolves every open report on the same thing.
      </p>
      <ul className="fc-mod-list" aria-label="Open reports">
        {items.map((report) => {
          const key = targetKey(report.target);
          return (
            <ReportCard
              key={report.id}
              meta={meta}
              report={report}
              hidden={hiddenNow.get(key) ?? report.target.hidden}
              now={now}
              onResolve={(outcome) => setResolving({ report, outcome })}
              onHidden={(hidden) => markHidden(key, hidden)}
            />
          );
        })}
      </ul>
      {queue.hasMore ? (
        <div className="fc-mod__more">
          <Button disabled={queue.loadingMore} onClick={queue.loadMore}>
            {queue.loadingMore ? "Loading…" : "Show more"}
          </Button>
        </div>
      ) : null}
      {resolving ? (
        <ResolveDialog
          resolving={resolving}
          mayHide={mayHide(resolving.report)}
          onConfirm={(note, hide) => void resolve(resolving.report, resolving.outcome, note, hide)}
          onClose={() => setResolving(null)}
        />
      ) : null}
    </>
  );
}
