import { useQueryClient } from "@tanstack/react-query";
import { UserMinus, UserPlus } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../../api/client.js";
import { Avatar } from "../../ui/Avatar.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { toast } from "../../ui/toastStore.js";
import { HANDLE_MAX_LENGTH, HANDLE_RULE_MESSAGE } from "../account/handles.js";
import { useSession } from "../account/session.js";
import { reasonOf, toastFailure } from "../finding/feedback.js";
import {
  acceptInvitation,
  INVESTIGATIONS_PATH,
  type InvestigationDetail,
  inviteMember,
  type Member,
  removeMember,
} from "./api.js";
import { cleanHandle, INVITABLE, mayInvite, type Powers, ROLE } from "./describe.js";
import { investigationKeys } from "./keys.js";
import { optimistic } from "./useInvestigation.js";

type Invitable = (typeof INVITABLE)[number];

function isInvitable(value: string): value is Invitable {
  return (INVITABLE as readonly string[]).includes(value);
}

/** Why an invitation was refused, in words that say what to do. */
function inviteProblem(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "user_not_found") return "Nobody has that handle. Check it on their profile.";
    if (error.code === "owner_is_always_a_member") return "That's you: you're its owner already.";
  }
  return reasonOf(error);
}

function InviteForm({ publicId }: { publicId: string }) {
  const client = useQueryClient();
  const [handle, setHandle] = useState("");
  const [role, setRole] = useState<Invitable>("editor");
  const [problem, setProblem] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function invite(event: FormEvent): Promise<void> {
    event.preventDefault();
    const clean = cleanHandle(handle);
    if (!clean) {
      setProblem(HANDLE_RULE_MESSAGE);
      return;
    }
    setSending(true);
    setProblem(null);
    try {
      const member = await inviteMember(publicId, clean, role);
      client.setQueryData<Member[]>(investigationKeys.members(publicId), (members) => {
        const others = (members ?? []).filter((current) => current.user.handle !== member.user.handle);
        return [...others, member];
      });
      setHandle("");
      toast(
        member.pending
          ? `${member.user.display_name} is invited. They'll be a member once they accept.`
          : `${member.user.display_name} is now a${role === "editor" ? "n" : ""} ${ROLE[role].label.toLowerCase()}.`,
        { kind: "success" },
      );
    } catch (error) {
      setProblem(inviteProblem(error));
    } finally {
      setSending(false);
    }
  }

  return (
    <form className="fc-inv-invite" onSubmit={(event) => void invite(event)} noValidate>
      <Field label="Invite someone by their handle" error={problem ?? undefined}>
        {(control) => (
          <input
            {...control}
            className="fc-input"
            value={handle}
            maxLength={HANDLE_MAX_LENGTH + 1}
            autoComplete="off"
            spellCheck={false}
            placeholder="@KeenLynchet7"
            onChange={(event) => setHandle(event.target.value)}
          />
        )}
      </Field>
      <div className="fc-field">
        <span className="fc-field__label" aria-hidden="true">
          As
        </span>
        <ChipGroup
          label="Invite them as"
          value={role}
          onChange={(value) => {
            if (isInvitable(value)) setRole(value);
          }}
          options={INVITABLE.map((id) => ({ id, label: ROLE[id].label }))}
        />
        <p className="fc-field__hint" aria-live="polite">
          {ROLE[role].says}
        </p>
      </div>
      <Button type="submit" size="sm" disabled={sending} icon={<UserPlus size={15} aria-hidden />}>
        {sending ? "Inviting…" : "Invite"}
      </Button>
    </form>
  );
}

interface Asking {
  member: Member;
  /** True when the person is leaving on their own account. */
  self: boolean;
}

/**
 * Who works on it: the owner, members with their roles, and invitations
 * still waiting. The owner invites and removes people, and anyone else can
 * leave. Removing someone and leaving each ask first.
 */
export function People({
  detail,
  members,
  powers,
  myHandle,
}: {
  detail: InvestigationDetail;
  members: readonly Member[];
  powers: Powers;
  myHandle: string | null;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [asking, setAsking] = useState<Asking | null>(null);
  const publicId = detail.public_id;

  async function remove({ member, self }: Asking): Promise<void> {
    setAsking(null);
    const done = await optimistic<Member[], true>(
      client,
      investigationKeys.members(publicId),
      (current) => current.filter((other) => other.user.handle !== member.user.handle),
      async () => {
        await removeMember(publicId, member.user.handle);
        return true as const;
      },
      self ? "You couldn't leave it." : "They couldn't be removed.",
    );
    if (!done) return;
    void client.invalidateQueries({ queryKey: investigationKeys.lists });
    if (self) {
      toast(`You've left “${detail.title}”.`);
      void client.invalidateQueries({ queryKey: investigationKeys.detail(publicId) });
      navigate(INVESTIGATIONS_PATH);
    } else {
      toast(member.pending ? "Invitation taken back." : `${member.user.display_name} has been removed.`);
      void client.invalidateQueries({ queryKey: investigationKeys.detail(publicId) });
    }
  }

  return (
    <section className="fc-inv-section" aria-labelledby="inv-people">
      <h3 id="inv-people">Who works on it</h3>
      <ul className="fc-inv-people">
        {members.map((member) => {
          const isMe = member.user.handle === myHandle;
          return (
            <li key={member.user.handle} className="fc-inv-person">
              <Avatar
                name={member.user.display_name}
                handle={member.user.handle}
                src={member.user.avatar_url ?? undefined}
              />
              <span className="fc-inv-person__text">
                <span className="fc-inv-person__name">
                  {member.user.display_name}
                  {isMe ? " (you)" : ""}
                </span>
                <span className="fc-inv-person__role">
                  {ROLE[member.role].label}
                  {member.pending ? " · invited, hasn't accepted yet" : ""}
                </span>
              </span>
              {powers.own && member.role !== "owner" ? (
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<UserMinus size={15} aria-hidden />}
                  onClick={() => setAsking({ member, self: false })}
                >
                  {member.pending ? "Take back" : "Remove"}
                  <span className="fc-visually-hidden"> {member.user.display_name}</span>
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
      {powers.own && detail.visibility === "private" ? (
        <p className="fc-field__hint">
          A private investigation has one member, you. To invite someone, make it public or unlisted first, below.
        </p>
      ) : null}
      {mayInvite(powers, detail) ? <InviteForm publicId={publicId} /> : null}
      {powers.leave && myHandle ? (
        <Button
          size="sm"
          variant="ghost"
          icon={<UserMinus size={15} aria-hidden />}
          onClick={() => {
            const me = members.find((member) => member.user.handle === myHandle);
            if (me) setAsking({ member: me, self: true });
          }}
        >
          Leave this investigation
        </Button>
      ) : null}
      <Dialog
        open={asking !== null}
        onClose={() => setAsking(null)}
        title={
          asking?.self
            ? "Leave this investigation?"
            : asking?.member.pending
              ? "Take back this invitation?"
              : `Remove ${asking?.member.user.display_name ?? "them"}?`
        }
        actions={
          <>
            <Button onClick={() => setAsking(null)}>{asking?.self ? "Stay" : "Keep them"}</Button>
            <Button variant="danger" onClick={() => asking && void remove(asking)}>
              {asking?.self ? "Leave" : asking?.member.pending ? "Take it back" : "Remove"}
            </Button>
          </>
        }
      >
        <p>
          {asking?.self
            ? "What you added stays in it. To work on it again, the owner has to invite you again."
            : "What they added stays in it. The owner can invite them again later."}
        </p>
      </Dialog>
    </section>
  );
}

/**
 * Accept or decline an invitation: accepting makes the person a member,
 * and declining is leaving, which the server takes from anyone with a session.
 */
export function InvitationAnswer({
  target,
  className,
  onAccepted,
  onDeclined,
}: {
  target: Pick<InvestigationDetail, "public_id" | "title">;
  className: string;
  onAccepted?: () => void;
  onDeclined?: () => void;
}) {
  const session = useSession();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const publicId = target.public_id;

  async function answer(accept: boolean): Promise<void> {
    const handle = session.me?.handle;
    if (!handle) return;
    setBusy(true);
    try {
      if (accept) {
        client.setQueryData(investigationKeys.detail(publicId), await acceptInvitation(publicId));
        toast(`You're working on “${target.title}” now.`, { kind: "success" });
        onAccepted?.();
      } else {
        await removeMember(publicId, handle);
        toast("Invitation declined.");
        onDeclined?.();
      }
      void client.invalidateQueries({ queryKey: investigationKeys.lists });
      void client.invalidateQueries({ queryKey: investigationKeys.members(publicId) });
    } catch (error) {
      toastFailure(accept ? "It couldn't be accepted." : "It couldn't be declined.", error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={className}>
      <Button size="sm" variant="primary" disabled={busy || !session.ready} onClick={() => void answer(true)}>
        Accept
      </Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => void answer(false)}>
        Decline
      </Button>
    </div>
  );
}

/** For someone invited: who asked, what they may do, and accept or decline. */
export function InvitationBanner({ detail }: { detail: InvestigationDetail }) {
  const navigate = useNavigate();
  const role = detail.invited_as;
  if (!role) return null;
  return (
    <section className="fc-inv-banner" aria-label="Your invitation">
      <p>
        {detail.owner.display_name} has invited you to work on this as a{role === "editor" ? "n" : ""}{" "}
        {ROLE[role].label.toLowerCase()}. {ROLE[role].says}
      </p>
      <InvitationAnswer
        target={detail}
        className="fc-inv-banner__actions"
        onDeclined={() => navigate(INVESTIGATIONS_PATH)}
      />
    </section>
  );
}
