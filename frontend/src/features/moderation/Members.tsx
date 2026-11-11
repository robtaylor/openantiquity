import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { BadgeCheck, Search, Unplug, Users } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { Avatar } from "../../ui/Avatar.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { toast } from "../../ui/toastStore.js";
import { useSession } from "../account/session.js";
import { toastFailure } from "../finding/feedback.js";
import { fetchProfile, isNoSuchPerson, profilePath } from "../people/api.js";
import { joinedWords, pointsWords } from "../people/describe.js";
import { peopleKeys } from "../people/keys.js";
import { roleWords } from "../people/roles.js";
import { roleChoices, TRUSTED_AT } from "./access.js";
import { changeRole, type Eligible, fetchEligible, type Role } from "./api.js";
import { BanButton } from "./BanButton.js";
import { pointSourceWords } from "./describe.js";
import { moderationKeys } from "./keys.js";
import { ReasonDialog } from "./ReasonDialog.js";

const retry = (failureCount: number, error: Error) => failureCount < 1 && isTransient(error);

function RoleDialog({
  handle,
  choices,
  initial,
  onConfirm,
  onClose,
}: {
  handle: string;
  choices: Role[];
  initial: Role | null;
  onConfirm: (role: Role, reason: string) => void;
  onClose: () => void;
}) {
  const [role, setRole] = useState<Role | null>(initial);
  return (
    <ReasonDialog
      title={`Change ${handle}'s role`}
      confirmLabel={role ? `Make them ${roleWords(role).label.toLowerCase()}` : "Change it"}
      ready={role !== null}
      onConfirm={(reason) => {
        if (role) onConfirm(role, reason);
      }}
      onClose={onClose}
    >
      <ChipGroup
        label="New role"
        value={role}
        onChange={(value) => setRole(value as Role)}
        options={choices.map((id) => ({ id, label: roleWords(id).label }))}
      />
      {role ? <p className="fc-mod__hint">{roleWords(role).hint}</p> : null}
      {role === "trusted" ? (
        <p className="fc-mod__hint">
          A trusted member sees the exact place of restricted findings. Check that their points come from findings other
          people checked, not from the same few accounts.
        </p>
      ) : null}
    </ReasonDialog>
  );
}

function EligibleCard({ meta, member, onTrusted }: { meta: Meta; member: Eligible; onTrusted: () => void }) {
  const { user } = member;
  return (
    <li className="fc-mod-card">
      <div className="fc-mod-person">
        <Avatar name={user.display_name} handle={user.handle} src={user.avatar_url ?? undefined} size={36} />
        <div>
          <p>
            <Link to={profilePath(user.handle)}>
              <strong>{user.display_name}</strong>
            </Link>
            {user.display_name !== user.handle ? <span className="fc-muted"> @{user.handle}</span> : null}
          </p>
          <p className="fc-muted">
            {pointsWords(user.reputation)} · {joinedWords(user.created_at)}
          </p>
        </div>
      </div>
      <div>
        <h4 className="fc-mod-card__subhead">Where the points came from</h4>
        <ul className="fc-mod-sources">
          {member.sources.map((source) => (
            <li key={source.finding?.public_id ?? source.reasons.join(",")}>
              <span className="fc-mod-sources__points">{pointsWords(source.points)}</span>
              <span>
                {source.finding ? (
                  <Link to={`/f/${encodeURIComponent(source.finding.public_id)}`}>{source.finding.title}</Link>
                ) : (
                  "Second looks, counted together"
                )}
                {source.finding?.hidden ? <span className="fc-muted"> (hidden)</span> : null}
                <span className="fc-mod-sources__why">{pointSourceWords(meta, source.reasons).join(". ")}.</span>
                {source.others.length > 0 ? (
                  <span className="fc-mod-sources__why">
                    Also on it: {source.others.map((other) => other.display_name).join(", ")}
                  </span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      </div>
      {member.associates.length > 0 ? (
        <div>
          <h4 className="fc-mod-card__subhead">Who else was on those findings</h4>
          <p className="fc-mod__hint">The same few names on every finding can mean accounts working together.</p>
          <ul className="fc-mod-associates">
            {member.associates.map((associate) => (
              <li key={associate.user.handle}>
                <Link to={profilePath(associate.user.handle)}>{associate.user.display_name}</Link>{" "}
                <span className="fc-muted">
                  on {associate.shared_findings} of {member.sources.filter((source) => source.finding).length}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="fc-mod-card__actions">
        <Button size="sm" variant="primary" icon={<BadgeCheck size={14} aria-hidden />} onClick={onTrusted}>
          Make trusted
        </Button>
        <BanButton handle={user.handle} targetRole={user.role} banned={user.banned} />
      </div>
    </li>
  );
}

function EligibleList({ meta }: { meta: Meta }) {
  const query = useInfiniteQuery({
    queryKey: moderationKeys.eligible,
    queryFn: ({ pageParam, signal }) => fetchEligible(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? null,
    retry,
  });
  const [done, setDone] = useState<ReadonlySet<string>>(new Set());
  const [trusting, setTrusting] = useState<Eligible | null>(null);
  const items = (query.data?.pages.flatMap((page) => page.items) ?? []).filter(
    (member) => !done.has(member.user.handle),
  );
  const mark = (handle: string, gone: boolean) =>
    setDone((before) => {
      const next = new Set(before);
      if (gone) next.add(handle);
      else next.delete(handle);
      return next;
    });

  async function trust(member: Eligible, reason: string): Promise<void> {
    const { handle } = member.user;
    mark(handle, true);
    try {
      await changeRole(handle, "trusted", reason);
      toast(`${member.user.display_name} is now a trusted member.`, { kind: "success" });
    } catch (error) {
      mark(handle, false);
      toastFailure("Their role couldn't be changed.", error);
    }
  }

  let body: ReactNode;
  if (query.isPending) {
    body = (
      <div role="status" className="fc-mod__loading">
        <span className="fc-visually-hidden">Loading the members who could be trusted</span>
        <Skeleton lines={3} />
      </div>
    );
  } else if (query.isError && items.length === 0) {
    body = (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="The list couldn't be loaded"
        action={
          <Button variant="primary" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      >
        <p>{query.error.message}</p>
      </EmptyState>
    );
  } else if (items.length === 0) {
    body = (
      <EmptyState icon={<Users size={22} />} title="Nobody is waiting">
        <p>Members who reach {TRUSTED_AT} points show here, for a moderator to decide whether to trust them.</p>
      </EmptyState>
    );
  } else {
    body = (
      <ul className="fc-mod-list" aria-label="Members who could be trusted">
        {items.map((member) => (
          <EligibleCard key={member.user.handle} meta={meta} member={member} onTrusted={() => setTrusting(member)} />
        ))}
      </ul>
    );
  }

  return (
    <section className="fc-mod-section" aria-labelledby="fc-mod-eligible">
      <h3 id="fc-mod-eligible">Could be trusted</h3>
      <p className="fc-mod__hint">
        Members with {TRUSTED_AT} points or more. Points never make anyone trusted by themselves: a moderator decides,
        because a few accounts working together could earn their way to restricted places.
      </p>
      {body}
      {query.hasNextPage ? (
        <div className="fc-mod__more">
          <Button disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            {query.isFetchingNextPage ? "Loading…" : "Show more"}
          </Button>
        </div>
      ) : null}
      {trusting ? (
        <RoleDialog
          handle={trusting.user.handle}
          choices={["trusted"]}
          initial="trusted"
          onConfirm={(_role, reason) => void trust(trusting, reason)}
          onClose={() => setTrusting(null)}
        />
      ) : null}
    </section>
  );
}

function LookUp() {
  const session = useSession();
  const [params, setParams] = useSearchParams();
  const asked = params.get("handle")?.trim() ?? "";
  const [typed, setTyped] = useState(asked);
  const [changing, setChanging] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const [banned, setBannedNow] = useState(false);
  const profile = useQuery({
    queryKey: peopleKeys.profile(asked),
    queryFn: ({ signal }) => fetchProfile(asked, signal),
    enabled: asked !== "",
    retry,
  });
  const person = profile.data;
  const shownRole = role ?? person?.role ?? "member";
  const mine = person?.is_me ?? false;
  // A banned person's role can't be changed: the server refuses with user_banned.
  const choices = person && !mine && !banned ? roleChoices(session.role, shownRole, person.reputation) : [];

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setRole(null);
    setBannedNow(false);
    setParams(
      (next) => {
        if (typed.trim()) next.set("handle", typed.trim());
        else next.delete("handle");
        return next;
      },
      { replace: true },
    );
  }

  async function change(to: Role, reason: string): Promise<void> {
    const before = shownRole;
    setRole(to);
    try {
      await changeRole(asked, to, reason);
      toast(`${asked} is now ${roleWords(to).label.toLowerCase()}.`, { kind: "success" });
    } catch (error) {
      setRole(before);
      toastFailure("Their role couldn't be changed.", error);
    }
  }

  return (
    <section className="fc-mod-section" aria-labelledby="fc-mod-lookup">
      <h3 id="fc-mod-lookup">Find a member</h3>
      <form className="fc-mod-lookup" onSubmit={submit}>
        <Field label="Handle" hint="Change someone's role, or ban them.">
          {(control) => (
            <input
              {...control}
              className="fc-input"
              autoComplete="off"
              spellCheck={false}
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
            />
          )}
        </Field>
        <Button type="submit" icon={<Search size={15} aria-hidden />}>
          Look up
        </Button>
      </form>
      {asked === "" ? null : profile.isPending ? (
        <Skeleton lines={2} />
      ) : person ? (
        <div className="fc-mod-card">
          <div className="fc-mod-person">
            <Avatar name={person.display_name} handle={person.handle} src={person.avatar_url ?? undefined} size={36} />
            <div>
              <p>
                <Link to={profilePath(person.handle)}>
                  <strong>{person.display_name}</strong>
                </Link>
                {person.display_name !== person.handle ? <span className="fc-muted"> @{person.handle}</span> : null}
              </p>
              <p className="fc-muted">
                {roleWords(shownRole).label}
                {banned ? " · banned" : ""} · {joinedWords(person.joined_at)}
              </p>
            </div>
          </div>
          {mine ? (
            <p className="fc-mod__hint">That's you. Nobody changes their own role or bans themselves.</p>
          ) : (
            <div className="fc-mod-card__actions">
              {choices.length > 0 ? (
                <Button size="sm" onClick={() => setChanging(true)}>
                  Change role
                </Button>
              ) : null}
              <BanButton handle={person.handle} targetRole={shownRole} banned={banned} onChange={setBannedNow} />
            </div>
          )}
          {changing ? (
            <RoleDialog
              handle={person.handle}
              choices={choices}
              initial={null}
              onConfirm={(to, reason) => void change(to, reason)}
              onClose={() => setChanging(false)}
            />
          ) : null}
        </div>
      ) : isNoSuchPerson(profile.error) ? (
        <div className="fc-mod-card">
          <p>
            Nobody can be found as <strong>{asked}</strong>. The handle may be mistyped, the account closed, or the
            person banned, since a banned person's page can't be found. A ban can't be lifted from here yet, because the
            site can't yet tell a moderator who is banned.
          </p>
        </div>
      ) : (
        <p className="fc-field__error" role="alert">
          {profile.error?.message ?? "They couldn't be looked up."}
        </p>
      )}
    </section>
  );
}

/** Members who could be trusted, with where their points came from, and finding anyone else by handle. */
export function Members({ meta }: { meta: Meta }) {
  return (
    <>
      <EligibleList meta={meta} />
      <LookUp />
    </>
  );
}
