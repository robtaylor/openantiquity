import { useQueryClient } from "@tanstack/react-query";
import { CircleUser, LogOut, Unplug } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { Link, useLocation } from "react-router";
import { ApiError } from "../../api/client.js";
import { useMeta } from "../../api/useMeta.js";
import { Avatar } from "../../ui/Avatar.js";
import { Button } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { toast } from "../../ui/toastStore.js";
import { discardAllDrafts, useDrafts } from "../drafts/store.js";
import { ModerationLink } from "../moderation/ModerationLink.js";
import { NotificationsSection } from "../notifications/NotificationsSection.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { accountKeys, deleteMe, logout, type Me, type MeUpdate, updateMe } from "./api.js";
import { HANDLE_MAX_LENGTH, HANDLE_PATTERN, HANDLE_RULE, HANDLE_RULE_MESSAGE } from "./handles.js";
import { Notice } from "./Notice.js";
import { useAccountUi } from "./requireAccount.js";
import { signedIn, signedOut, useSession } from "./session.js";
import "./account.css";

const MAX_BIO = 1000;
const MAX_DISPLAY_NAME = 60;

function pictureRule(me: Me): string {
  if (me.age_band === "16_17") {
    return "Other people see only your handle. No picture or name from your sign-in is shown, because you're 16 or 17.";
  }
  if (me.age_band === null) return "Until you finish joining, other people see only your handle.";
  if (me.avatar_url)
    return "Your picture comes from the service you signed in with. Other people see it beside what you add.";
  return "You don't have a picture, so other people see your initials.";
}

interface ProfileErrors {
  handle?: string;
  display_name?: string;
  bio?: string;
}

function ProfileForm({ me }: { me: Me }) {
  const client = useQueryClient();
  const [displayName, setDisplayName] = useState(me.display_name);
  const [handle, setHandle] = useState(me.handle);
  const [bio, setBio] = useState(me.bio ?? "");
  const [errors, setErrors] = useState<ProfileErrors>({});

  const changes: { display_name?: string; handle?: string; bio?: string } & MeUpdate = {};
  if (displayName.trim() !== me.display_name) changes.display_name = displayName.trim();
  if (handle.trim() !== me.handle) changes.handle = handle.trim();
  if (bio.trim() !== (me.bio ?? "")) changes.bio = bio.trim();
  const dirty = Object.keys(changes).length > 0;

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const found: ProfileErrors = {};
    if (changes.handle !== undefined && !HANDLE_PATTERN.test(changes.handle)) {
      found.handle = HANDLE_RULE_MESSAGE;
    }
    if (changes.display_name !== undefined && changes.display_name === "")
      found.display_name = "Your name can't be empty.";
    setErrors(found);
    if (!dirty || Object.keys(found).length > 0) return;

    // Shown at once, and put back if the server says no.
    const before = me;
    const shown: Me = {
      ...me,
      display_name: changes.display_name ?? me.display_name,
      handle: changes.handle ?? me.handle,
      bio: changes.bio === undefined ? me.bio : changes.bio || null,
    };
    client.setQueryData<Me | null>(accountKeys.me, shown);
    try {
      signedIn(client, await updateMe(changes));
      toast("Your details are saved.", { kind: "success" });
    } catch (error) {
      client.setQueryData(accountKeys.me, before);
      const code = error instanceof ApiError ? error.code : "";
      if (code === "handle_taken") setErrors({ handle: "Someone already has that name. Please choose another." });
      else if (code === "invalid_handle") setErrors({ handle: `That name can't be used. ${HANDLE_RULE_MESSAGE}` });
      else if (code === "invalid_display_name")
        setErrors({ display_name: error instanceof ApiError ? error.message : "" });
      toast(`Your changes weren't saved. ${error instanceof Error ? error.message : ""}`.trim(), { kind: "error" });
    }
  }

  return (
    <form className="fc-account-form" onSubmit={(event) => void onSubmit(event)} noValidate>
      <Field label="Display name" hint="Shown with what you add." error={errors.display_name}>
        {(control) => (
          <input
            {...control}
            className="fc-input"
            value={displayName}
            maxLength={MAX_DISPLAY_NAME}
            autoComplete="name"
            onChange={(event) => setDisplayName(event.target.value)}
          />
        )}
      </Field>
      <Field
        label="Handle"
        hint={`Your name in links, such as the one to your profile. ${HANDLE_RULE}`}
        error={errors.handle}
      >
        {(control) => (
          <input
            {...control}
            className="fc-input"
            value={handle}
            maxLength={HANDLE_MAX_LENGTH}
            spellCheck={false}
            autoComplete="username"
            onChange={(event) => setHandle(event.target.value)}
          />
        )}
      </Field>
      <Field
        label="About you"
        hint={
          me.needs_welcome
            ? "You can write a short public bio once you've finished joining."
            : "A short public bio, shown on your profile. Up to 1,000 characters."
        }
        error={errors.bio}
      >
        {(control) => (
          <textarea
            {...control}
            className="fc-input fc-account-textarea"
            value={bio}
            maxLength={MAX_BIO}
            disabled={me.needs_welcome && bio === ""}
            onChange={(event) => setBio(event.target.value)}
          />
        )}
      </Field>
      <div className="fc-account-actions">
        <Button type="submit" variant="primary" disabled={!dirty}>
          Save changes
        </Button>
      </div>
    </form>
  );
}

function draftCount(n: number): string {
  return n === 1 ? "1 draft" : `${n} drafts`;
}

function DeleteAccount() {
  const client = useQueryClient();
  const meta = useMeta();
  const drafts = useDrafts().length;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [discardDrafts, setDiscardDrafts] = useState(true);
  const licence = meta.data?.app.contribution_licence ?? "an open licence";

  async function remove(): Promise<void> {
    setBusy(true);
    try {
      await deleteMe();
      setOpen(false);
      if (discardDrafts) discardAllDrafts();
      signedOut(client);
      toast("Your account has been deleted.");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Your account wasn't deleted. Please try again.", {
        kind: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant="danger" onClick={() => setOpen(true)}>
        Delete my account
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Delete your account?"
        className="fc-account-sheet"
        actions={
          <>
            <Button onClick={() => setOpen(false)}>Keep my account</Button>
            <Button variant="danger" onClick={() => void remove()} disabled={busy}>
              {busy ? "Deleting…" : "Delete my account"}
            </Button>
          </>
        }
      >
        <div className="fc-account-stack">
          <p>
            This removes your email address and the ways you sign in, and signs you out on every device. It can't be
            undone.
          </p>
          <p>
            Your findings, second looks, evidence and comments stay on the map, credited to “Former member”. They were
            published under {licence}, and other people's work builds on them.
          </p>
          {drafts > 0 ? (
            <label className="fc-account-check">
              <input
                type="checkbox"
                checked={discardDrafts}
                onChange={(event) => setDiscardDrafts(event.target.checked)}
              />
              Also discard the {draftCount(drafts)} kept in this browser
            </label>
          ) : null}
        </div>
      </Dialog>
    </>
  );
}

/**
 * Sign out. With drafts in this browser, it first asks whether to keep them,
 * because whoever uses the browser next will see them.
 */
function SignOut() {
  const client = useQueryClient();
  const drafts = useDrafts().length;
  const [asking, setAsking] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  async function signOut(discard: boolean): Promise<void> {
    setSigningOut(true);
    try {
      await logout();
      setAsking(false);
      if (discard) discardAllDrafts();
      signedOut(client);
      toast(discard ? "You've signed out, and your drafts are discarded." : "You've signed out.");
    } catch (error) {
      setSigningOut(false);
      toast(error instanceof ApiError ? error.message : "You weren't signed out. Please try again.", { kind: "error" });
    }
  }

  return (
    <>
      <Button
        icon={<LogOut size={16} aria-hidden />}
        onClick={() => (drafts > 0 ? setAsking(true) : void signOut(false))}
        disabled={signingOut}
      >
        Sign out
      </Button>
      <Dialog
        open={asking}
        onClose={() => setAsking(false)}
        title="Keep your drafts?"
        className="fc-account-sheet"
        actions={
          <>
            <Button onClick={() => void signOut(false)} disabled={signingOut}>
              Keep and sign out
            </Button>
            <Button variant="danger" onClick={() => void signOut(true)} disabled={signingOut}>
              Discard and sign out
            </Button>
          </>
        }
      >
        <div className="fc-account-stack">
          <p>
            There {drafts === 1 ? "is 1 draft" : `are ${drafts} drafts`} in this browser that{" "}
            {drafts === 1 ? "hasn't" : "haven't"} been saved.
          </p>
          <p>
            If you keep {drafts === 1 ? "it" : "them"}, whoever uses this browser next will see{" "}
            {drafts === 1 ? "it" : "them"}. Discard {drafts === 1 ? "it" : "them"} if this isn't your own device.
          </p>
        </div>
      </Dialog>
    </>
  );
}

function SignedIn({ me }: { me: Me }) {
  return (
    <div className="fc-account-stack">
      <div className="fc-account-who">
        <Avatar name={me.display_name} handle={me.handle} src={me.avatar_url ?? undefined} size={52} />
        <div className="fc-account-who__names">
          <div className="fc-account-who__name">{me.display_name}</div>
          <div className="fc-account-who__handle">@{me.handle}</div>
        </div>
      </div>
      <Link className="fc-account-link" to={`/u/${encodeURIComponent(me.handle)}`}>
        See your public profile
      </Link>
      <ModerationLink role={me.role} />

      {me.needs_welcome ? (
        <Notice tone="info" title="You haven't finished joining">
          <p>Choose your age band and accept the contributor terms, and then you can save what you do.</p>
          <p>
            <Button size="sm" variant="primary" onClick={() => useAccountUi.getState().openWelcome()}>
              Finish joining
            </Button>
          </p>
        </Notice>
      ) : null}

      <NotificationsSection />

      <section className="fc-account-section" aria-labelledby="account-details">
        <h3 id="account-details">Your details</h3>
        <ProfileForm key={`${me.handle}\u0000${me.display_name}\u0000${me.bio ?? ""}`} me={me} />
      </section>

      <section className="fc-account-section" aria-labelledby="account-picture">
        <h3 id="account-picture">Picture</h3>
        <p className="fc-account-small">{pictureRule(me)}</p>
      </section>

      <section className="fc-account-section" aria-labelledby="account-signin">
        <h3 id="account-signin">Signing in</h3>
        {me.email ? <p className="fc-account-small">Signed in as {me.email}.</p> : null}
        <div className="fc-account-actions">
          <SignOut />
          <DeleteAccount />
        </div>
      </section>
    </div>
  );
}

/** `/account`: an invitation to sign in, or the signed-in person's own details. */
export function AccountPage() {
  const { pathname } = useLocation();
  const session = useSession();
  useDocumentTitle("Account");

  let body: ReactNode;
  if (session.status === "loading") {
    body = (
      <div role="status">
        <span className="fc-visually-hidden">Checking whether you're signed in</span>
        <Skeleton lines={4} />
      </div>
    );
  } else if (session.status === "unknown") {
    body = (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="We couldn't check whether you're signed in"
        action={
          <Button variant="primary" onClick={session.refetch}>
            Try again
          </Button>
        }
      >
        <p>{session.error?.message ?? "The server didn't answer."}</p>
      </EmptyState>
    );
  } else if (session.me) {
    body = <SignedIn me={session.me} />;
  } else {
    body = (
      <EmptyState
        icon={<CircleUser size={22} />}
        title="You're not signed in"
        action={
          <Button variant="primary" onClick={() => useAccountUi.getState().openSignIn()}>
            Sign in
          </Button>
        }
      >
        <p>
          You can look at everything, and try marking and checking, without an account. Saving needs one, so that
          everything on the map has a real person behind it.
        </p>
      </EmptyState>
    );
  }

  return (
    <PanelFrame panelKey={pathname} title="Account">
      {body}
    </PanelFrame>
  );
}
