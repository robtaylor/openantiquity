import { keepPreviousData, useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { EyeOff, Inbox, LogIn, NotebookText, Plus, Unplug } from "lucide-react";
import { type FormEvent, type ReactNode, useId, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { isTransient } from "../../api/client.js";
import { useViewAreaStore } from "../../map/store.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { Switch } from "../../ui/Switch.js";
import { TabPanel, Tabs } from "../../ui/Tabs.js";
import { useDebounced } from "../../ui/useDebounced.js";
import { useSession } from "../account/session.js";
import { reasonOf, useSignedInFirst } from "../finding/feedback.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import {
  createInvestigation,
  fetchInvestigations,
  INVESTIGATIONS_PATH,
  type InvestigationSummary,
  investigationPath,
  LIMITS,
  type Scope,
} from "./api.js";
import { bboxParam } from "./area.js";
import { dateText, itemCountText, VISIBILITY } from "./describe.js";
import { investigationKeys } from "./keys.js";
import { InvitationAnswer } from "./People.js";
import "./investigations.css";

/** The lists, as the address names them. */
const LISTS = ["mine", "invited", "public"] as const satisfies readonly Scope[];
type ListId = (typeof LISTS)[number];
const LIST_PARAM = "list";
const IN_VIEW_PARAM = "inview";

const TITLES: Record<ListId, string> = { mine: "Yours", invited: "Invitations", public: "Public" };

function useInvestigationList(scope: ListId, bbox: string | null, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: investigationKeys.list(scope, bbox),
    queryFn: ({ pageParam, signal }) => fetchInvestigations(scope, bbox, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    enabled,
    placeholderData: keepPreviousData,
    retry: (failures, error) => failures < 1 && isTransient(error),
  });
}

/** Start an investigation. It takes a title and nothing else; everything else is added on its page. */
export function StartForm({
  onStarted,
  onCancel,
}: {
  onStarted?: (created: InvestigationSummary) => void;
  /** Offered as "Cancel" beside "Start", and called by Escape in the title. */
  onCancel?: () => void;
}) {
  const [title, setTitle] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const signedInFirst = useSignedInFirst();
  const client = useQueryClient();
  const navigate = useNavigate();

  async function start(event: FormEvent): Promise<void> {
    event.preventDefault();
    const text = title.trim();
    if (!text) {
      setProblem("Give it a title, such as the parish or the question it's about.");
      return;
    }
    if (!(await signedInFirst())) return;
    setSaving(true);
    setProblem(null);
    try {
      const created = await createInvestigation(text);
      client.setQueryData(investigationKeys.detail(created.public_id), created);
      void client.invalidateQueries({ queryKey: investigationKeys.lists });
      setTitle("");
      if (onStarted) onStarted(created);
      else navigate(investigationPath(created.public_id));
    } catch (error) {
      setProblem(reasonOf(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="fc-inv-start" onSubmit={(event) => void start(event)} noValidate>
      <Field
        label="Start an investigation"
        hint="It starts private, so only you can see it, until you choose otherwise."
        error={problem ?? undefined}
      >
        {(control) => (
          <div className="fc-inv-start__row">
            <input
              {...control}
              className="fc-input"
              value={title}
              maxLength={LIMITS.title}
              placeholder="A title, such as “Barrows of Overton Down”"
              onChange={(event) => setTitle(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape" && onCancel) {
                  event.preventDefault();
                  onCancel();
                }
              }}
              // biome-ignore lint/a11y/noAutofocus: it appears because "Start an investigation" was pressed for it
              autoFocus={onCancel !== undefined}
            />
            <Button type="submit" variant="primary" disabled={saving} icon={<Plus size={16} aria-hidden />}>
              {saving ? "Starting…" : "Start"}
            </Button>
            {onCancel ? (
              <Button variant="ghost" onClick={onCancel}>
                Cancel
              </Button>
            ) : null}
          </div>
        )}
      </Field>
    </form>
  );
}

function SummaryRow({
  item,
  showVisibility,
  children,
}: {
  item: InvestigationSummary;
  showVisibility: boolean;
  children?: ReactNode;
}) {
  return (
    <li className="fc-inv-row">
      <Link className="fc-inv-row__link" to={investigationPath(item.public_id)}>
        <span className="fc-inv-row__title">{item.title}</span>
        {item.summary ? <span className="fc-inv-row__summary">{item.summary}</span> : null}
        <span className="fc-inv-row__meta">
          {showVisibility ? <span className="fc-inv-badge">{VISIBILITY[item.visibility].label}</span> : null}
          {item.hidden ? (
            <span className="fc-inv-badge fc-inv-badge--warn">
              <EyeOff size={12} aria-hidden /> Hidden by a moderator
            </span>
          ) : null}
          <span>
            {[item.owner.display_name, itemCountText(item.item_count), `changed ${dateText(item.updated_at)}`].join(
              " · ",
            )}
          </span>
        </span>
      </Link>
      {children}
    </li>
  );
}

/** Accept or decline, under an invitation in the list. Accepting opens it. */
function ListedInvitation({ item }: { item: InvestigationSummary }) {
  const navigate = useNavigate();
  return (
    <InvitationAnswer
      target={item}
      className="fc-inv-row__actions"
      onAccepted={() => navigate(investigationPath(item.public_id))}
    />
  );
}

function SignInFirst({ what }: { what: string }) {
  const signedInFirst = useSignedInFirst();
  return (
    <EmptyState
      icon={<LogIn size={22} />}
      title={`Sign in to see ${what}`}
      action={
        <Button variant="primary" onClick={() => void signedInFirst()}>
          Sign in
        </Button>
      }
    >
      <p>Public investigations are listed for everyone. Your own, and invitations to others, need an account.</p>
    </EmptyState>
  );
}

function List({ scope, bbox }: { scope: ListId; bbox: string | null }) {
  const session = useSession();
  const needsAccount = scope !== "public";
  const query = useInvestigationList(scope, scope === "public" ? bbox : null, !needsAccount || session.ready);

  if (needsAccount && session.status !== "loading" && !session.ready) {
    return <SignInFirst what={scope === "mine" ? "your investigations" : "your invitations"} />;
  }
  if (query.isError) {
    return (
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
  }
  if (!query.data) {
    return (
      <div role="status" className="fc-inv-loading">
        <span className="fc-visually-hidden">Loading the investigations</span>
        <Skeleton lines={2} />
        <Skeleton lines={2} />
      </div>
    );
  }
  const items = query.data.pages.flatMap((page) => page.items);
  if (items.length === 0) {
    if (scope === "mine") {
      return (
        <EmptyState icon={<NotebookText size={22} />} title="You haven't started one yet">
          <p>
            Start one with “Start an investigation” above. You can add findings, records, map views and notes to it as
            you go.
          </p>
        </EmptyState>
      );
    }
    if (scope === "invited") {
      return (
        <EmptyState icon={<Inbox size={22} />} title="No invitations waiting">
          <p>When someone asks you to work on their investigation, it shows here for you to accept or decline.</p>
        </EmptyState>
      );
    }
    return (
      <EmptyState icon={<NotebookText size={22} />} title={bbox ? "None here" : "No public investigations yet"}>
        <p>
          {bbox
            ? "No public investigation covers this part of the map. Move the map, or list them all."
            : "When someone publishes an investigation, it's listed here for everyone to read."}
        </p>
      </EmptyState>
    );
  }
  return (
    <>
      <ul className="fc-inv-list" aria-label={TITLES[scope]} aria-busy={query.isPlaceholderData}>
        {items.map((item) => (
          <SummaryRow key={item.public_id} item={item} showVisibility={scope === "mine"}>
            {scope === "invited" ? <ListedInvitation item={item} /> : null}
          </SummaryRow>
        ))}
      </ul>
      {query.hasNextPage ? (
        <div className="fc-inv-more">
          <Button onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}>
            {query.isFetchingNextPage ? "Loading…" : "Show more"}
          </Button>
        </div>
      ) : null}
    </>
  );
}

function isList(value: string | null): value is ListId {
  return (LISTS as readonly string[]).includes(value ?? "");
}

/**
 * `/investigations`: yours, the ones you're invited to with accept and
 * decline, and the public ones, all of them or only those whose area is in
 * view. The list and the "in view" switch live in the address.
 */
export function InvestigationsPanel() {
  useDocumentTitle("Investigations");
  const session = useSession();
  const id = useId();
  const [params, setParams] = useSearchParams();
  const asked = params.get(LIST_PARAM);
  const list: ListId = isList(asked) ? asked : session.ready ? "mine" : "public";
  // With no list asked for, which one opens depends on who is signed in, so nothing is asked until that's known.
  const waiting = !isList(asked) && session.status === "loading";
  const inView = params.get(IN_VIEW_PARAM) === "1";
  const bounds = useViewAreaStore((state) => state.bounds);
  const settled = useDebounced(inView && bounds ? bboxParam(bounds) : null, 400);
  // Behind a button, so the lists come first, above the fold of a phone's half-open sheet.
  const [starting, setStarting] = useState(false);

  function change(next: Record<string, string | null>): void {
    setParams(
      (current) => {
        for (const [key, value] of Object.entries(next)) {
          if (value === null) current.delete(key);
          else current.set(key, value);
        }
        return current;
      },
      { replace: true },
    );
  }

  return (
    <PanelFrame panelKey={INVESTIGATIONS_PATH} title="Investigations">
      <div className="fc-inv">
        <p className="fc-inv__intro">
          An investigation is a notebook tied to the map: findings, records, views and notes for one piece of work.
        </p>
        {starting ? (
          <StartForm onCancel={() => setStarting(false)} />
        ) : (
          <Button size="sm" icon={<Plus size={15} aria-hidden />} onClick={() => setStarting(true)}>
            Start an investigation
          </Button>
        )}
        <Tabs
          label="Which investigations"
          idPrefix={id}
          value={list}
          onChange={(next) => change({ [LIST_PARAM]: next })}
          tabs={LISTS.map((scope) => ({ id: scope, label: TITLES[scope] }))}
        />
        <TabPanel idPrefix={id} id={list}>
          <div className="fc-inv__list-body">
            {list === "public" ? (
              <Switch
                label="Only those whose area is in view"
                hint="An investigation's area is the part of the map it's about."
                checked={inView}
                onChange={(checked) => change({ [IN_VIEW_PARAM]: checked ? "1" : null })}
              />
            ) : null}
            {waiting ? (
              <div role="status" className="fc-inv-loading">
                <span className="fc-visually-hidden">Loading the investigations</span>
                <Skeleton lines={2} />
              </div>
            ) : (
              <List scope={list} bbox={list === "public" ? settled : null} />
            )}
          </div>
        </TabPanel>
      </div>
    </PanelFrame>
  );
}
