import { type InfiniteData, useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Radar } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { toast, useToastStore } from "../../ui/toastStore.js";
import { useFocusLater } from "../../ui/useFocusLater.js";
import type { Viewer } from "../finding/describe.js";
import { useSignedInFirst } from "../finding/feedback.js";
import type { FindingDetail } from "../finding/types.js";
import { AddMention } from "./AddMention.js";
import { addMention, deleteMention, fetchMentions, retryOnceIfTransient } from "./api.js";
import { type MentionFailure, mentionFailure } from "./describe.js";
import { mentionKeys } from "./keys.js";
import { MentionCard } from "./MentionCard.js";
import { RECENT_MENTIONS_PATH } from "./paths.js";
import type { Mention, MentionIn, MentionPage, MentionPreview } from "./types.js";

type Pages = InfiniteData<MentionPage, string | null>;

const ADD_BUTTON_ID = "fc-mention-add-button";

/** The list item that holds a mention, which takes focus once it is saved, or when the one above it goes. */
function itemId(mentionId: number): string {
  return `fc-mention-${mentionId}`;
}

export function useFindingMentions(publicId: string) {
  return useInfiniteQuery({
    queryKey: mentionKeys.forFinding(publicId),
    queryFn: ({ pageParam, signal }) => fetchMentions(publicId, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: retryOnceIfTransient,
  });
}

/**
 * Change the mentions in the cache at once, page by page, and get back a
 * function that puts them back. `first` changes the first page, where a new
 * mention goes because the list is newest first; `each` changes every page.
 */
function useOptimisticMentions(publicId: string) {
  const client = useQueryClient();
  return (change: { first?: (items: Mention[]) => Mention[]; each?: (items: Mention[]) => Mention[] }) => {
    const key = mentionKeys.forFinding(publicId);
    const before = client.getQueryData<Pages>(key);
    if (before) {
      client.setQueryData<Pages>(key, {
        ...before,
        pages: before.pages.map((page, index) => {
          let items = change.each ? change.each(page.items) : page.items;
          if (index === 0 && change.first) items = change.first(items);
          return { ...page, items };
        }),
      });
    }
    return () => {
      if (before) client.setQueryData(key, before);
    };
  };
}

/** A stand-in for a mention being saved, from what the preview found. */
function pendingMention(body: MentionIn, preview: MentionPreview | null, viewer: Viewer, displayName: string): Mention {
  return {
    id: -Date.now(),
    kind: body.kind ?? preview?.kind ?? "article",
    url: body.url,
    canonical_url: preview?.canonical_url ?? body.url,
    provider: preview?.provider ?? null,
    title: preview?.title ?? null,
    author_name: preview?.author_name ?? null,
    thumbnail_url: preview?.thumbnail_url ?? null,
    published_at: preview?.published_at ?? null,
    start_seconds: body.start_seconds ?? null,
    note: body.note ?? null,
    auto_detected: false,
    added_by: { handle: viewer.handle ?? "", display_name: displayName, role: viewer.role ?? "member" },
    created_at: new Date().toISOString(),
    hidden: false,
  };
}

export interface MentionsSectionProps {
  meta: Meta;
  finding: FindingDetail;
  viewer: Viewer;
  displayName: string;
  /** Mentions can be added: the finding isn't withdrawn, and the person may contribute or will once signed in. */
  mayAdd: boolean;
}

/**
 * The videos, articles, podcasts and papers that discuss a finding, newest
 * first, and adding one. A new mention shows at once and is taken back,
 * with a toast and the form as it was, if the server refuses it. Whoever
 * added a mention can remove it.
 */
export function MentionsSection({ meta, finding, viewer, displayName, mayAdd }: MentionsSectionProps) {
  const { public_id: publicId } = finding;
  const client = useQueryClient();
  const mentions = useFindingMentions(publicId);
  const optimistic = useOptimisticMentions(publicId);
  const signedInFirst = useSignedInFirst();
  const [adding, setAdding] = useState(false);
  /** Said once a mention is saved or removed, for anyone who can't see the list change. */
  const [news, setNews] = useState("");
  const focusLater = useFocusLater();
  /** The toast that said the last try failed, which a new try takes away. */
  const failedToast = useRef<number | null>(null);

  const refreshRecent = () => void client.invalidateQueries({ queryKey: mentionKeys.recent });
  const addButton = () => document.getElementById(ADD_BUTTON_ID);

  async function open(): Promise<void> {
    if (await signedInFirst()) {
      setNews("");
      setAdding(true);
    }
  }

  function close(): void {
    setAdding(false);
    focusLater(addButton);
  }

  async function save(body: MentionIn, preview: MentionPreview | null): Promise<MentionFailure | null> {
    if (failedToast.current !== null) useToastStore.getState().dismiss(failedToast.current);
    failedToast.current = null;
    const placeholder = pendingMention(body, preview, viewer, displayName);
    const undo = optimistic({ first: (items) => [placeholder, ...items] });
    try {
      const saved = await addMention(publicId, body);
      optimistic({ each: (items) => items.map((mention) => (mention.id === placeholder.id ? saved : mention)) });
      refreshRecent();
      setAdding(false);
      setNews("Your mention is added, at the top of the list.");
      // The new mention is where the person's attention goes, at the top of the list, which may be out of sight.
      focusLater(() => document.getElementById(itemId(saved.id)), { scroll: true });
      return null;
    } catch (error) {
      undo();
      const failure = mentionFailure(error);
      failedToast.current = toast(`Your mention couldn't be added. ${failure.message}`, { kind: "error" });
      return failure;
    }
  }

  async function remove(mention: Mention): Promise<void> {
    // Focus goes to the mention that takes its place, or the one before it, or else to adding one.
    const ids = all.map((entry) => entry.id);
    const at = ids.indexOf(mention.id);
    const next = ids[at + 1] ?? ids[at - 1];
    focusLater(() => (next === undefined ? addButton() : document.getElementById(itemId(next))));
    const undo = optimistic({ each: (items) => items.filter((entry) => entry.id !== mention.id) });
    setNews("The mention is removed.");
    try {
      await deleteMention(mention.id);
      refreshRecent();
    } catch (error) {
      undo();
      setNews("");
      toast(`That mention couldn't be removed. ${mentionFailure(error).message}`, { kind: "error" });
    }
  }

  const all = mentions.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section className="fc-finding__section" aria-labelledby="fc-mentions-title" id="fc-mentions">
      <div className="fc-finding__section-head">
        <h3 id="fc-mentions-title">Mentions</h3>
        <Link className="fc-mentions-link" to={RECENT_MENTIONS_PATH}>
          Recent mentions everywhere
        </Link>
      </div>
      <p className="fc-finding__hint">Videos, articles, podcasts and papers that talk about it.</p>
      {mentions.isPending ? (
        <Skeleton lines={2} />
      ) : mentions.isError ? (
        <div className="fc-finding__inline-error" role="alert">
          <p>The mentions couldn't be loaded. {mentions.error.message}</p>
          <Button size="sm" onClick={() => void mentions.refetch()}>
            Try again
          </Button>
        </div>
      ) : all.length === 0 ? (
        <p className="fc-muted fc-mention__empty">
          <Radar size={15} aria-hidden /> Nobody has said where it was talked about yet. A video that links to this page
          in its description is added by itself.
        </p>
      ) : (
        <ul className="fc-mentions" aria-label="Mentions of this finding">
          {all.map((mention) => (
            <li key={mention.id} id={itemId(mention.id)} tabIndex={-1} className="fc-mentions__item">
              <MentionCard
                meta={meta}
                mention={mention}
                pending={mention.id < 0}
                own={mention.added_by !== null && viewer.handle !== null && mention.added_by.handle === viewer.handle}
                onRemove={() => void remove(mention)}
              />
            </li>
          ))}
        </ul>
      )}
      {mentions.hasNextPage ? (
        <Button size="sm" disabled={mentions.isFetchingNextPage} onClick={() => void mentions.fetchNextPage()}>
          {mentions.isFetchingNextPage ? "Loading…" : "Show older mentions"}
        </Button>
      ) : null}
      <p className="fc-visually-hidden" role="status">
        {news}
      </p>
      {mayAdd ? (
        adding ? (
          <AddMention meta={meta} onSave={save} onCancel={close} />
        ) : (
          <Button id={ADD_BUTTON_ID} icon={<Plus size={16} aria-hidden />} onClick={() => void open()}>
            Add a mention
          </Button>
        )
      ) : null}
    </section>
  );
}
