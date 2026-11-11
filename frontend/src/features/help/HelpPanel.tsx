import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, Eye, HandHelping, ScanSearch, SearchX, Unplug } from "lucide-react";
import type { ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router";
import { isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { FeatureIcon } from "../../ui/featureIcons.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { TierBadge } from "../../ui/TierBadge.js";
import { labelOf } from "../finding/describe.js";
import { reasonOf } from "../finding/feedback.js";
import { whereRef } from "../findings/square.js";
import { useDocumentTitle } from "../placeholders.js";
import { REVIEW_PATH } from "../review/ReviewLayer.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { fetchTaskGroup, fetchTaskGroups, type TaskCode, type TaskItem } from "./api.js";
import { helpKeys } from "./keys.js";
import { countWords, type HelpKind, helpKinds, kindCount, kindFromAddress, kindTasks, taskPath } from "./kinds.js";
import "../explore/explore.css";
import "./help.css";

export const HELP_PATH = "/help";
const HELP_TITLE = "Help wanted";

const retry = (failureCount: number, error: Error): boolean => failureCount < 1 && isTransient(error);

function kindPath(kind: HelpKind): string {
  return kind.blind ? REVIEW_PATH : `${HELP_PATH}/${encodeURIComponent(kind.id)}`;
}

function Loading({ label }: { label: string }) {
  return (
    <div className="fc-help__loading" role="status">
      <span className="fc-visually-hidden">{label}</span>
      <Skeleton lines={2} />
      <Skeleton lines={2} />
      <Skeleton lines={2} />
    </div>
  );
}

function Failed({ title, error, onRetry }: { title: string; error: Error; onRetry: () => void }) {
  return (
    <EmptyState
      tone="error"
      icon={<Unplug size={22} />}
      title={title}
      action={
        <Button variant="primary" onClick={onRetry}>
          Try again
        </Button>
      }
    >
      <p>{reasonOf(error)}</p>
    </EmptyState>
  );
}

function OtherWork({ children }: { children?: ReactNode }) {
  return (
    <div className="fc-help__other">
      <Link className="fc-button fc-button--primary fc-button--md" to={REVIEW_PATH}>
        <Eye size={16} aria-hidden />
        Give a second look
      </Link>
      <Link className="fc-button fc-button--secondary fc-button--md" to="/scan">
        <ScanSearch size={16} aria-hidden />
        Scan a square
      </Link>
      {children}
    </div>
  );
}

/**
 * Help wanted, at `/help`: the open next steps across findings, by the
 * kind of work they are, each with a plain name, a line on what it means
 * and how many findings want it. A kind opens its list of findings, except
 * second looks, which go to the blind queue (Decision 0008).
 */
export function HelpPanel({ meta }: { meta: Meta }) {
  useDocumentTitle(HELP_TITLE);
  const query = useQuery({ queryKey: helpKeys.groups, queryFn: ({ signal }) => fetchTaskGroups(signal), retry });

  let body: ReactNode;
  if (query.data) {
    const groups = query.data.groups;
    const kinds = helpKinds(meta, groups).map((kind) => ({ kind, count: kindCount(meta, kind, groups) }));
    const waiting = kinds.filter(({ count }) => count.count > 0 || count.more);
    const quiet = kinds.filter(({ count }) => count.count === 0 && !count.more);
    body =
      waiting.length === 0 ? (
        <EmptyState icon={<HandHelping size={22} />} title="Nothing needs a hand just now" action={<OtherWork />}>
          <p>Every finding's next step is in hand. New ones arrive as people mark findings and others check them.</p>
        </EmptyState>
      ) : (
        <>
          <ul className="fc-help__kinds" aria-label="Kinds of help">
            {waiting.map(({ kind, count }) => {
              const Icon = kind.icon;
              return (
                <li key={kind.id}>
                  <Link className="fc-help__kind" to={kindPath(kind)}>
                    <span className="fc-explore__icon">
                      <Icon size={20} aria-hidden />
                    </span>
                    <span className="fc-help__kind-text">
                      <span className="fc-help__kind-name">{kind.name}</span>
                      <span className="fc-help__kind-line">{kind.line}</span>
                      <span className="fc-help__kind-count">{countWords(count)}</span>
                    </span>
                    <ChevronRight className="fc-help__chevron" size={18} aria-hidden />
                  </Link>
                </li>
              );
            })}
          </ul>
          {quiet.length > 0 ? (
            <p className="fc-help__quiet">
              Nothing waiting just now for {quiet.map(({ kind }) => kind.name.toLowerCase()).join(", ")}.
            </p>
          ) : null}
        </>
      );
  } else if (query.isError) {
    body = <Failed title="Help wanted couldn't be loaded" error={query.error} onRetry={() => void query.refetch()} />;
  } else {
    body = <Loading label="Loading what needs doing" />;
  }

  return (
    <PanelFrame panelKey={HELP_PATH} title={HELP_TITLE}>
      <div className="fc-help">
        <p className="fc-help__intro">
          Every finding says what would move it up the ladder. These are those next steps, gathered by the kind of work
          they are, so you can do the sort you like.
        </p>
        {body}
      </div>
    </PanelFrame>
  );
}

function TaskRow({ meta, kind, item }: { meta: Meta; kind: HelpKind; item: TaskItem }) {
  const { finding, place, step } = item;
  if (!finding) return null;
  const tier = { id: finding.tier, label: labelOf(meta.vocab.tiers, finding.tier) };
  const state = { id: finding.state, label: labelOf(meta.vocab.states, finding.state) };
  return (
    <li>
      <Link className="fc-explore__row" to={taskPath(kind, item)}>
        <span className="fc-explore__icon">
          <FeatureIcon classId={finding.feature_class} size={22} />
        </span>
        <span className="fc-explore__text">
          <span className="fc-explore__title">{finding.title}</span>
          <span className="fc-explore__meta">
            <TierBadge tier={tier} state={state} size="sm" />
            <span className="fc-explore__class">{labelOf(meta.vocab.feature_classes, finding.feature_class)}</span>
          </span>
          <span className="fc-explore__where">
            {place.obscured ? "Somewhere in square " : "At "}
            <span className="fc-mono">{whereRef(place)}</span>
          </span>
          {step ? <span className="fc-help__step">{step.prompt}</span> : null}
        </span>
      </Link>
    </li>
  );
}

function KindList({ meta, kind }: { meta: Meta; kind: HelpKind }) {
  const query = useInfiniteQuery({
    queryKey: helpKeys.group(kind.code),
    queryFn: ({ pageParam, signal }) => fetchTaskGroup(kind.code as TaskCode, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.groups[0]?.next_cursor ?? null,
    retry,
  });

  if (query.data) {
    const tasks = kindTasks(
      kind,
      query.data.pages.flatMap((page) => page.groups),
    );
    if (tasks.length === 0 && !query.hasNextPage) {
      return (
        <EmptyState icon={<HandHelping size={22} />} title="Nothing needs this just now" action={<OtherWork />}>
          <p>Every finding that wanted this has had it. Another kind of help may be waiting.</p>
        </EmptyState>
      );
    }
    return (
      <>
        <ul className="fc-explore__list" aria-label="Findings that need this">
          {tasks.map((item) => (
            <TaskRow key={`${item.public_id}-${item.code}`} meta={meta} kind={kind} item={item} />
          ))}
        </ul>
        {query.hasNextPage ? (
          <div className="fc-explore__more">
            <Button disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
              {query.isFetchingNextPage ? "Loading…" : "Show more"}
            </Button>
          </div>
        ) : null}
      </>
    );
  }
  if (query.isError) {
    return <Failed title="This list couldn't be loaded" error={query.error} onRetry={() => void query.refetch()} />;
  }
  return <Loading label="Loading the findings that need this" />;
}

/**
 * One kind of help, at `/help/:kind`: the findings that want it, each
 * opening its page with the form for that work ready. Second looks are
 * never listed by finding: their address goes to the blind queue.
 */
export function HelpKindPanel({ meta }: { meta: Meta }) {
  const { kind: id = "" } = useParams();
  const kind = kindFromAddress(meta, id);
  useDocumentTitle(kind ? `${kind.name} · ${HELP_TITLE}` : HELP_TITLE);
  if (kind?.blind) return <Navigate to={REVIEW_PATH} replace />;
  const path = `${HELP_PATH}/${id}`;
  return (
    <PanelFrame panelKey={path} title={kind?.name ?? HELP_TITLE} subtitle={kind ? HELP_TITLE : undefined}>
      <div className="fc-help">
        <Link className="fc-help__back" to={HELP_PATH}>
          <ArrowLeft size={15} aria-hidden />
          Every kind of help
        </Link>
        {kind ? (
          <>
            <p className="fc-help__intro">{kind.line}</p>
            <KindList meta={meta} kind={kind} />
          </>
        ) : (
          <EmptyState icon={<SearchX size={22} />} title="There's no such kind of help">
            <p>The link may be old or mistyped. Every kind of help is listed in Help wanted.</p>
          </EmptyState>
        )}
      </div>
    </PanelFrame>
  );
}
