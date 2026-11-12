import { useInfiniteQuery } from "@tanstack/react-query";
import { Check, ImageOff, Unplug, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { isTransient } from "../../api/client.js";
import { Avatar } from "../../ui/Avatar.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { toast } from "../../ui/toastStore.js";
import { formatDate } from "../finding/describe.js";
import { toastFailure } from "../finding/feedback.js";
import { moderationKeys } from "../moderation/keys.js";
import { ReasonDialog } from "../moderation/ReasonDialog.js";
import { profilePath } from "../people/api.js";
import { approvePhoto, fetchPhotoQueue, type QueuedMedia, refusePhoto } from "./api.js";
import { Photo } from "./Photo.js";
import "./photos.css";

function sizeWords(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function PhotoCard({ item, onApprove, onRefuse }: { item: QueuedMedia; onApprove: () => void; onRefuse: () => void }) {
  return (
    <li className="fc-photo-card">
      <Photo
        src={item.url}
        alt={`Photo uploaded by ${item.uploader.display_name}`}
        unavailable="The photo couldn't be loaded. It may have been hidden, or its uploader may have left."
      />
      <p className="fc-photo-card__meta">
        <Avatar name={item.uploader.display_name} handle={item.uploader.handle} size={20} />{" "}
        <Link to={profilePath(item.uploader.handle)}>{item.uploader.display_name}</Link> uploaded it on{" "}
        {formatDate(item.created_at)}
        {item.width && item.height ? ` · ${item.width} × ${item.height}` : ""} · {sizeWords(item.bytes)}
      </p>
      <p className="fc-photo-card__meta">
        {item.findings.length > 0 ? "Added to " : "It isn't on a finding yet."}
        {item.findings.map((publicId, index) => (
          <span key={publicId}>
            {index > 0 ? ", " : null}
            <Link to={`/f/${encodeURIComponent(publicId)}`}>finding {publicId}</Link>
          </span>
        ))}
      </p>
      <div className="fc-photo-card__actions">
        <Button variant="primary" size="sm" icon={<Check size={15} aria-hidden />} onClick={onApprove}>
          Approve
        </Button>
        <Button variant="danger" size="sm" icon={<X size={15} aria-hidden />} onClick={onRefuse}>
          Refuse
        </Button>
      </div>
    </li>
  );
}

/**
 * Photos waiting for approval, oldest first, for trusted members and
 * moderators (Decision 0009). Nobody sees their own here. Approving shows a
 * photo to everyone who may see its finding; refusing deletes its file and
 * needs a reason for the log. Both take the photo off the list at once and
 * put it back with a toast if the server refuses.
 */
export function PhotoQueue() {
  const query = useInfiniteQuery({
    queryKey: moderationKeys.photos,
    queryFn: ({ pageParam, signal }) => fetchPhotoQueue(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? null,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });
  const [decided, setDecided] = useState<ReadonlySet<number>>(new Set());
  const [refusing, setRefusing] = useState<QueuedMedia | null>(null);
  const items = (query.data?.pages.flatMap((page) => page.items) ?? []).filter((item) => !decided.has(item.id));

  const mark = (id: number, gone: boolean) =>
    setDecided((before) => {
      const next = new Set(before);
      if (gone) next.add(id);
      else next.delete(id);
      return next;
    });

  async function decide(item: QueuedMedia, act: () => Promise<unknown>, done: string, failed: string): Promise<void> {
    mark(item.id, true);
    try {
      await act();
      toast(done, { kind: "success" });
    } catch (error) {
      mark(item.id, false);
      toastFailure(failed, error);
    }
  }

  if (query.isPending) {
    return (
      <div role="status" className="fc-mod__loading">
        <span className="fc-visually-hidden">Loading the photos waiting for approval</span>
        <Skeleton height={160} />
        <Skeleton lines={2} />
      </div>
    );
  }
  if (query.isError && items.length === 0) {
    return (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="The photos couldn't be loaded"
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

  return (
    <>
      <p className="fc-mod__hint">
        A photo shows to other people only once someone here approves it. Check that it shows the place, not a person, a
        home or a find, and that nothing in it could lead someone to dig or detect.
      </p>
      {items.length === 0 ? (
        <EmptyState icon={<ImageOff size={22} />} title="No photos are waiting">
          <p>
            When someone adds a photo to a finding, it waits here until it is approved. Your own go to someone else.
          </p>
        </EmptyState>
      ) : (
        <ul className="fc-photo-queue" aria-label="Photos waiting for approval">
          {items.map((item) => (
            <PhotoCard
              key={item.id}
              item={item}
              onApprove={() =>
                void decide(
                  item,
                  () => approvePhoto(item.id),
                  "Approved. Everyone who may see its finding can see it now.",
                  "The photo couldn't be approved.",
                )
              }
              onRefuse={() => setRefusing(item)}
            />
          ))}
        </ul>
      )}
      {query.hasNextPage ? (
        <div className="fc-mod__more">
          <Button disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            {query.isFetchingNextPage ? "Loading…" : "Show more"}
          </Button>
        </div>
      ) : null}
      {refusing ? (
        <ReasonDialog
          title="Refuse this photo?"
          confirmLabel="Refuse it"
          danger
          onConfirm={(reason) =>
            void decide(
              refusing,
              () => refusePhoto(refusing.id, reason),
              "Refused. Its file is deleted, and the same file can't be added again.",
              "The photo couldn't be refused.",
            )
          }
          onClose={() => setRefusing(null)}
        >
          <p>Its file is deleted, and the same file can't be uploaded again. Nobody else will see it.</p>
        </ReasonDialog>
      ) : null}
    </>
  );
}
