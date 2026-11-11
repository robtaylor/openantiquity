import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Eye, HandHelping, MapPinPlus, Shield, Unplug, UserRoundX } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { Avatar } from "../../ui/Avatar.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { TabPanel, Tabs } from "../../ui/Tabs.js";
import { useSession } from "../account/session.js";
import { FindingRow } from "../explore/ExplorePanel.js";
import { formatDate } from "../finding/describe.js";
import { MARK_PATH } from "../mark/MarkPanel.js";
import { isModerator } from "../moderation/access.js";
import { useDocumentTitle } from "../placeholders.js";
import { ReportButton } from "../reports/ReportButton.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import {
  fetchContributions,
  fetchPersonFindings,
  fetchPoints,
  fetchProfile,
  isNoSuchPerson,
  type Profile,
} from "./api.js";
import { contributionWords, joinedWords, pointsWords, pointWords } from "./describe.js";
import { peopleKeys } from "./keys.js";
import { roleWords } from "./roles.js";
import "./people.css";

export const PROFILE_ROUTE = "/u/:handle";

type TabId = "found" | "helped" | "second_looks" | "points";

const retry = (failureCount: number, error: Error) => failureCount < 1 && isTransient(error);

interface Paged<T> {
  items: T[];
  status: "pending" | "error" | "success";
  error: Error | null;
  hasMore: boolean;
  loadingMore: boolean;
  loadMore: () => void;
  retry: () => void;
}

/** One of the profile's lists, a page at a time. */
function usePaged<T>(
  queryKey: readonly unknown[],
  fetchPage: (cursor: string | null, signal: AbortSignal) => Promise<{ items: T[]; next_cursor?: string | null }>,
): Paged<T> {
  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }) => fetchPage(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? null,
    retry,
  });
  return {
    items: query.data?.pages.flatMap((page) => page.items) ?? [],
    status: query.status,
    error: query.error,
    hasMore: query.hasNextPage,
    loadingMore: query.isFetchingNextPage,
    loadMore: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
    },
    retry: () => void query.refetch(),
  };
}

/** A list's loading, failed and empty states, its rows and its "Show more". */
function ListBody<T>({
  list,
  what,
  empty,
  children,
}: {
  list: Paged<T>;
  what: string;
  empty: ReactNode;
  children: (items: T[]) => ReactNode;
}) {
  if (list.status === "pending") {
    return (
      <div role="status" className="fc-profile__loading">
        <span className="fc-visually-hidden">Loading {what}</span>
        <Skeleton lines={2} />
        <Skeleton lines={2} />
      </div>
    );
  }
  if (list.status === "error" && list.items.length === 0) {
    return (
      <div className="fc-profile__error" role="alert">
        <p>
          {what[0]?.toUpperCase()}
          {what.slice(1)} couldn't be loaded. {list.error?.message}
        </p>
        <Button size="sm" onClick={list.retry}>
          Try again
        </Button>
      </div>
    );
  }
  if (list.items.length === 0) return <>{empty}</>;
  return (
    <>
      {children(list.items)}
      {list.hasMore ? (
        <div className="fc-profile__more">
          <Button onClick={list.loadMore} disabled={list.loadingMore}>
            {list.loadingMore ? "Loading…" : "Show more"}
          </Button>
        </div>
      ) : null}
    </>
  );
}

function Found({ meta, profile }: { meta: Meta; profile: Profile }) {
  const navigate = useNavigate();
  const list = usePaged(peopleKeys.findings(profile.handle), (cursor, signal) =>
    fetchPersonFindings(profile.handle, cursor, signal),
  );
  return (
    <ListBody
      list={list}
      what="their findings"
      empty={
        profile.is_me ? (
          <EmptyState
            icon={<MapPinPlus size={22} />}
            title="You haven't marked a finding yet"
            action={
              <Button variant="primary" onClick={() => navigate(MARK_PATH)}>
                Mark a finding
              </Button>
            }
          >
            <p>When you mark something on the map, it shows here.</p>
          </EmptyState>
        ) : (
          <p className="fc-muted">Nothing they've marked is on the map for you to see.</p>
        )
      }
    >
      {(items) => (
        <ul className="fc-explore__list" aria-label="Findings">
          {items.map((finding) => (
            <FindingRow
              key={finding.public_id}
              meta={meta}
              finding={finding}
              detail={`Marked on ${formatDate(finding.created_at)}`}
            />
          ))}
        </ul>
      )}
    </ListBody>
  );
}

function Helped({ meta, profile, kind }: { meta: Meta; profile: Profile; kind: "second_look" | null }) {
  const navigate = useNavigate();
  const list = usePaged(peopleKeys.contributions(profile.handle, kind), (cursor, signal) =>
    fetchContributions(profile.handle, kind, cursor, signal),
  );
  const secondLooks = kind === "second_look";
  const empty = secondLooks ? (
    <EmptyState
      icon={<Eye size={22} />}
      title="You haven't taken a second look yet"
      action={
        <Button variant="primary" onClick={() => navigate("/review")}>
          Give a second look
        </Button>
      }
    >
      <p>A second look is checking someone else's finding without being told what they think it is.</p>
    </EmptyState>
  ) : profile.is_me ? (
    <EmptyState
      icon={<HandHelping size={22} />}
      title="Nothing yet"
      action={
        <Button variant="primary" onClick={() => navigate("/help")}>
          See what needs help
        </Button>
      }
    >
      <p>Evidence you add, comments and mentions you link show here.</p>
    </EmptyState>
  ) : (
    <p className="fc-muted">Nothing they've added is on a finding you can see.</p>
  );
  return (
    <ListBody list={list} what={secondLooks ? "your second looks" : "what they helped with"} empty={empty}>
      {(items) => (
        <>
          {secondLooks ? (
            <p className="fc-profile__note">
              {profile.counts.second_looks === 1
                ? "You've taken a second look at 1 finding. "
                : `You've taken a second look at ${profile.counts.second_looks ?? items.length} findings. `}
              Only you see this list. It never says how you answered, so nobody can tell from your page.
            </p>
          ) : null}
          <ul className="fc-explore__list" aria-label={secondLooks ? "Second looks" : "Helped with"}>
            {items.map((item) => (
              <FindingRow
                key={`${item.kind}-${item.id ?? item.finding.public_id}`}
                meta={meta}
                finding={item.finding}
                detail={
                  item.created_at
                    ? `${contributionWords(meta, item, profile.is_me)} on ${formatDate(item.created_at)}`
                    : contributionWords(meta, item, profile.is_me)
                }
              />
            ))}
          </ul>
        </>
      )}
    </ListBody>
  );
}

function Points({ meta, profile }: { meta: Meta; profile: Profile }) {
  const total = profile.reputation_total ?? 0;
  const list = usePaged(peopleKeys.points(profile.handle), (cursor, signal) =>
    fetchPoints(profile.handle, cursor, signal),
  );
  return (
    <>
      <p className="fc-profile__total">{pointsWords(total)} in all</p>
      <p className="fc-profile__note">
        Only you see where your points came from. You earn them when your findings move up, when your second looks agree
        with how a finding turns out, and when two people endorse evidence you added. At fifty, a moderator can make you
        a trusted member.
      </p>
      <ListBody
        list={list}
        what="your points"
        empty={<p className="fc-muted">No points yet. They'll show here as your work is checked.</p>}
      >
        {(items) => (
          <ul className="fc-points" aria-label="Where your points came from">
            {items.map((point) => (
              <li key={point.id} className="fc-points__row">
                <span className="fc-points__delta">+{Math.round(point.delta * 10) / 10}</span>
                <span className="fc-points__text">
                  <span>{pointWords(meta, point.reason)}</span>
                  <span className="fc-muted">
                    {point.finding ? (
                      <>
                        <Link to={`/f/${encodeURIComponent(point.finding.public_id)}`}>{point.finding.title}</Link>
                        {" · "}
                      </>
                    ) : null}
                    {formatDate(point.created_at)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </ListBody>
    </>
  );
}

function Head({ profile }: { profile: Profile }) {
  const role = roleWords(profile.role);
  return (
    <div className="fc-profile__head">
      <Avatar name={profile.display_name} handle={profile.handle} src={profile.avatar_url ?? undefined} size={56} />
      <div className="fc-profile__who">
        <p className="fc-profile__role">
          <span className="fc-profile__badge" data-role={profile.role}>
            {role.label}
          </span>
          <span className="fc-muted">{joinedWords(profile.joined_at)}</span>
        </p>
        {profile.role !== "member" && role.hint ? <p className="fc-profile__hint">{role.hint}</p> : null}
      </div>
    </div>
  );
}

function ProfilePage({ meta, profile }: { meta: Meta; profile: Profile }) {
  const session = useSession();
  const [tab, setTab] = useState<TabId>("found");
  const { counts } = profile;
  // The counts are above, so the tabs say only what each holds and fit four abreast on a phone.
  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "found", label: "Found" },
    { id: "helped", label: "Helped" },
  ];
  if (profile.is_me && counts.second_looks !== null) tabs.push({ id: "second_looks", label: "Second looks" });
  if (profile.is_me && profile.reputation_total !== null) tabs.push({ id: "points", label: "Points" });
  const current = tabs.some((entry) => entry.id === tab) ? tab : "found";

  return (
    <div className="fc-profile">
      <Head profile={profile} />
      {profile.bio ? <p className="fc-profile__bio">{profile.bio}</p> : null}

      <dl className="fc-profile__counts">
        <div>
          <dt>{counts.findings === 1 ? "Finding" : "Findings"}</dt>
          <dd>{counts.findings}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>{counts.evidence}</dd>
        </div>
        <div>
          <dt>{counts.comments === 1 ? "Comment" : "Comments"}</dt>
          <dd>{counts.comments}</dd>
        </div>
        <div>
          <dt>{counts.mentions === 1 ? "Mention" : "Mentions"}</dt>
          <dd>{counts.mentions}</dd>
        </div>
      </dl>

      {profile.is_me ? (
        <p className="fc-profile__note">
          This is your page as others see it, except your points and second looks, which only you see.{" "}
          <Link to="/account">Change your details</Link>
        </p>
      ) : null}

      <div className="fc-profile__lists">
        <Tabs
          label="What they've done"
          idPrefix="fc-profile"
          tabs={tabs}
          value={current}
          onChange={(id) => setTab(id as TabId)}
        />
        <TabPanel idPrefix="fc-profile" id={current}>
          {current === "found" ? <Found meta={meta} profile={profile} /> : null}
          {current === "helped" ? <Helped meta={meta} profile={profile} kind={null} /> : null}
          {current === "second_looks" ? <Helped meta={meta} profile={profile} kind="second_look" /> : null}
          {current === "points" ? <Points meta={meta} profile={profile} /> : null}
        </TabPanel>
      </div>

      {profile.is_me ? null : (
        <div className="fc-profile__foot">
          <p className="fc-finding__hint">
            Open Antiquity has no private messages. To talk to someone, comment on a finding.
          </p>
          <div className="fc-profile__actions">
            <ReportButton target={{ kind: "user", id: profile.handle }} ownerHandle={profile.handle} />
            {isModerator(session.role) ? (
              <Link
                className="fc-button fc-button--ghost fc-button--sm"
                to={`/mod/members?handle=${encodeURIComponent(profile.handle)}`}
              >
                <Shield size={14} aria-hidden />
                Moderate
              </Link>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * `/u/:handle`: someone's page, exactly as the server gives it. What they
 * found and what they helped with, their role and when they joined. Their
 * own page also lists their second looks and where their points came from,
 * which nobody else sees (Decision 0010). There is no leaderboard and no way
 * to contact a person (Decision 0009).
 */
export function ProfilePanel({ meta }: { meta: Meta }) {
  const { handle = "" } = useParams();
  const panelKey = `/u/${handle}`;
  const query = useQuery({
    queryKey: peopleKeys.profile(handle),
    queryFn: ({ signal }) => fetchProfile(handle, signal),
    retry,
  });
  const profile = query.data;
  useDocumentTitle(profile?.display_name ?? "Profile");

  if (profile) {
    return (
      <PanelFrame
        panelKey={panelKey}
        title={profile.display_name}
        subtitle={profile.display_name === profile.handle ? undefined : `@${profile.handle}`}
      >
        <ProfilePage meta={meta} profile={profile} />
      </PanelFrame>
    );
  }
  if (query.isError && isNoSuchPerson(query.error)) {
    return (
      <PanelFrame panelKey={panelKey} title="Profile" subtitle={`@${handle}`}>
        <EmptyState
          icon={<UserRoundX size={22} />}
          title="There's nobody here"
          action={
            <Link className="fc-button fc-button--secondary fc-button--md" to="/">
              Back to the map
            </Link>
          }
        >
          <p>The link may be mistyped, or the account may have closed.</p>
        </EmptyState>
      </PanelFrame>
    );
  }
  if (query.isError) {
    return (
      <PanelFrame panelKey={panelKey} title="Profile" subtitle={`@${handle}`}>
        <EmptyState
          tone="error"
          icon={<Unplug size={22} />}
          title="This page couldn't be loaded"
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
    <PanelFrame panelKey={panelKey} title="Profile" subtitle={`@${handle}`}>
      <div className="fc-profile" role="status">
        <span className="fc-visually-hidden">Loading the profile</span>
        <div className="fc-profile__head">
          <Skeleton width={56} height={56} />
          <div className="fc-profile__who fc-profile__who--loading">
            <Skeleton lines={2} />
          </div>
        </div>
        <Skeleton lines={3} />
      </div>
    </PanelFrame>
  );
}
