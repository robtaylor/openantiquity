import { type InfiniteData, useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, CornerDownRight, MessageSquare, Trash2 } from "lucide-react";
import { useState } from "react";
import { Avatar } from "../../ui/Avatar.js";
import { Button } from "../../ui/Button.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { addComment, deleteComment, fetchComments, setFollowing } from "./api.js";
import { formatDate, type Viewer } from "./describe.js";
import { toastFailure, useSignedInFirst } from "./feedback.js";
import { findingPageKeys } from "./keys.js";
import type { Comment, CommentPage, FindingDetail } from "./types.js";
import { useOptimisticFinding } from "./useFinding.js";

type Pages = InfiniteData<CommentPage, string | null>;

function useComments(publicId: string) {
  return useInfiniteQuery({
    queryKey: findingPageKeys.comments(publicId),
    queryFn: ({ pageParam, signal }) => fetchComments(publicId, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

/** Change the comments in the cache at once, and get back a function that puts them back. */
function useOptimisticComments(publicId: string) {
  const client = useQueryClient();
  return (change: (comments: Comment[]) => Comment[]): (() => void) => {
    const key = findingPageKeys.comments(publicId);
    const before = client.getQueryData<Pages>(key);
    if (before) {
      const all = change(before.pages.flatMap((page) => page.items));
      // Everything goes on the last page, which keeps the order and the cursors right.
      const kept = before.pages.slice(0, -1).reduce((count, page) => count + page.items.length, 0);
      client.setQueryData<Pages>(key, {
        ...before,
        pages: before.pages.map((page, index) =>
          index === before.pages.length - 1 ? { ...page, items: all.slice(kept) } : page,
        ),
      });
    }
    return () => {
      if (before) client.setQueryData(key, before);
    };
  };
}

function CommentForm({
  label,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  label: string;
  submitLabel: string;
  onSubmit: (body: string) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [body, setBody] = useState("");
  return (
    <form
      className="fc-comment-form"
      onSubmit={(event) => {
        event.preventDefault();
        const text = body.trim();
        if (!text) return;
        // Cleared at once, and given back if the comment couldn't be posted.
        setBody("");
        void onSubmit(text).then((posted) => {
          if (!posted) setBody(text);
        });
      }}
    >
      <Field label={label}>
        {(control) => (
          <textarea
            {...control}
            className="fc-input"
            rows={2}
            maxLength={5000}
            value={body}
            onChange={(event) => setBody(event.target.value)}
          />
        )}
      </Field>
      <div className="fc-comment-form__actions">
        {onCancel ? (
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
        <Button size="sm" type="submit" variant="primary" disabled={body.trim() === ""}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

export interface DiscussionProps {
  finding: FindingDetail;
  viewer: Viewer;
  displayName: string;
}

/**
 * The discussion on a finding: comments, oldest first so the newest is last,
 * with replies, removing your own, and following the finding. Anyone can
 * read it. Acting asks a signed-out person to sign in first. Posting,
 * removing and following show at once and are put back, with a toast, if
 * the server refuses.
 */
export function Discussion({ finding, viewer, displayName }: DiscussionProps) {
  const { public_id: publicId } = finding;
  const comments = useComments(publicId);
  const ready = useSignedInFirst();
  const optimisticComments = useOptimisticComments(publicId);
  const optimisticFinding = useOptimisticFinding(publicId);
  const [replyTo, setReplyTo] = useState<number | null>(null);

  async function post(body: string, parentId: number | null): Promise<boolean> {
    if (!(await ready())) return false;
    const placeholder: Comment = {
      id: -Date.now(),
      parent_id: parentId,
      author: { handle: viewer.handle ?? "", display_name: displayName, role: viewer.role ?? "member" },
      body,
      created_at: new Date().toISOString(),
      edited_at: null,
      deleted: false,
    };
    const undo = optimisticComments((all) => [...all, placeholder]);
    setReplyTo(null);
    try {
      const saved = await addComment(publicId, body, parentId);
      optimisticComments((all) => all.map((comment) => (comment.id === placeholder.id ? saved : comment)));
      return true;
    } catch (error) {
      undo();
      toastFailure("Your comment couldn't be posted.", error);
      return false;
    }
  }

  async function remove(comment: Comment): Promise<void> {
    const undo = optimisticComments((all) =>
      all.map((entry) => (entry.id === comment.id ? { ...entry, deleted: true, body: null, author: null } : entry)),
    );
    try {
      await deleteComment(comment.id);
    } catch (error) {
      undo();
      toastFailure("Your comment couldn't be removed.", error);
    }
  }

  async function toggleFollow(): Promise<void> {
    if (!(await ready())) return;
    const next = !finding.following;
    const undo = optimisticFinding((current) => ({ ...current, following: next }));
    try {
      await setFollowing(publicId, next);
    } catch (error) {
      undo();
      toastFailure("That didn't work.", error);
    }
  }

  const all = comments.data?.pages.flatMap((page) => page.items) ?? [];
  const top = all.filter(
    (comment) => comment.parent_id === null || !all.some((parent) => parent.id === comment.parent_id),
  );
  const repliesTo = (id: number) => all.filter((comment) => comment.parent_id === id);

  function renderComment(comment: Comment) {
    const own = comment.author !== null && viewer.handle !== null && comment.author.handle === viewer.handle;
    return (
      <li key={comment.id} className="fc-comment" aria-busy={comment.id < 0 || undefined}>
        {comment.deleted || comment.author === null ? (
          <p className="fc-muted">This comment was removed.</p>
        ) : (
          <>
            <p className="fc-comment__by">
              <Avatar
                name={comment.author.display_name}
                handle={comment.author.handle}
                src={comment.author.avatar_url ?? undefined}
                size={22}
              />
              <strong>{comment.author.display_name}</strong>
              <span className="fc-muted">{comment.id < 0 ? "Posting…" : formatDate(comment.created_at)}</span>
            </p>
            <p className="fc-comment__body">{comment.body}</p>
            {comment.id > 0 ? (
              <div className="fc-comment__actions">
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<CornerDownRight size={14} aria-hidden />}
                  onClick={() => setReplyTo(comment.id)}
                >
                  Reply
                </Button>
                {own ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Trash2 size={14} aria-hidden />}
                    onClick={() => void remove(comment)}
                  >
                    Remove
                  </Button>
                ) : null}
              </div>
            ) : null}
          </>
        )}
        {replyTo === comment.id ? (
          <CommentForm
            label={`Reply to ${comment.author?.display_name ?? "this comment"}`}
            submitLabel="Reply"
            onSubmit={(body) => post(body, comment.id)}
            onCancel={() => setReplyTo(null)}
          />
        ) : null}
        {repliesTo(comment.id).length > 0 ? (
          <ul className="fc-comments fc-comments--replies">{repliesTo(comment.id).map(renderComment)}</ul>
        ) : null}
      </li>
    );
  }

  return (
    <section className="fc-finding__section" aria-labelledby="fc-discussion-title">
      <div className="fc-finding__section-head">
        <h3 id="fc-discussion-title">Discussion</h3>
        <Button
          size="sm"
          variant={finding.following ? "secondary" : "ghost"}
          aria-pressed={finding.following}
          icon={finding.following ? <BellOff size={15} aria-hidden /> : <Bell size={15} aria-hidden />}
          onClick={() => void toggleFollow()}
        >
          {finding.following ? "Unfollow" : "Follow"}
        </Button>
      </div>
      <p className="fc-finding__hint">
        {finding.following
          ? "You're following it, so you'll hear when it moves or someone comments."
          : "Follow it to hear when it moves or someone comments."}
      </p>
      {comments.isPending ? (
        <Skeleton lines={3} />
      ) : comments.isError ? (
        <div className="fc-finding__inline-error" role="alert">
          <p>The discussion couldn't be loaded. {comments.error.message}</p>
          <Button size="sm" onClick={() => void comments.refetch()}>
            Try again
          </Button>
        </div>
      ) : top.length === 0 ? (
        <p className="fc-muted">
          <MessageSquare size={15} aria-hidden /> No comments yet. Ask a question or say what you see.
        </p>
      ) : (
        <ul className="fc-comments">{top.map(renderComment)}</ul>
      )}
      {comments.hasNextPage ? (
        <Button size="sm" disabled={comments.isFetchingNextPage} onClick={() => void comments.fetchNextPage()}>
          {comments.isFetchingNextPage ? "Loading…" : "Show later comments"}
        </Button>
      ) : null}
      <CommentForm label="Add a comment" submitLabel="Post" onSubmit={(body) => post(body, null)} />
    </section>
  );
}
