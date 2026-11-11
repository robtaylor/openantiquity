import { useInfiniteQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { FeatureIcon } from "../../ui/featureIcons.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { TierBadge } from "../../ui/TierBadge.js";
import { fetchRecordFindings, type LinkedFinding, recordKeys } from "./api.js";

/** A step or state by its id, labelled from the vocabulary, or by its id when the vocabulary lacks it. */
function labelled(list: ReadonlyArray<{ id: string; label: string }>, id: string): { id: string; label: string } {
  return list.find((item) => item.id === id) ?? { id, label: id };
}

function FindingItem({ finding, meta }: { finding: LinkedFinding; meta: Meta }) {
  const featureClass = labelled(meta.vocab.feature_classes, finding.feature_class);
  return (
    <li className="fc-linked-finding">
      <Link className="fc-linked-finding__link" to={`/f/${encodeURIComponent(finding.public_id)}`}>
        <FeatureIcon classId={finding.feature_class} size={20} />
        <span className="fc-linked-finding__text">
          <span className="fc-linked-finding__title">{finding.title}</span>
          <span className="fc-linked-finding__class">{featureClass.label}</span>
        </span>
      </Link>
      <TierBadge
        size="sm"
        tier={labelled(meta.vocab.tiers, finding.tier)}
        state={labelled(meta.vocab.states, finding.state)}
      />
    </li>
  );
}

/**
 * The findings whose evidence links this record. The server lists only those
 * the viewer may see exactly, since naming the record would place a finding
 * as closely as the record is placed, so the list can differ between people.
 */
export function LinkedFindings({ recordId, meta }: { recordId: number; meta: Meta }) {
  const query = useInfiniteQuery({
    queryKey: recordKeys.findings(recordId),
    queryFn: ({ pageParam, signal }) => fetchRecordFindings(recordId, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? null,
    staleTime: 60_000,
    retry: (failures, error) => failures < 1 && isTransient(error),
  });
  const findings = query.data?.pages.flatMap((page) => page.items) ?? [];

  let body: ReactNode;
  if (query.isError && !query.data) {
    body = (
      <p className="fc-muted fc-record__small" role="status">
        The linked findings couldn't be loaded.{" "}
        <Button size="sm" variant="ghost" onClick={() => void query.refetch()}>
          Try again
        </Button>
      </p>
    );
  } else if (!query.data) {
    body = (
      <div role="status">
        <span className="fc-visually-hidden">Loading the linked findings</span>
        <Skeleton lines={2} />
      </div>
    );
  } else if (findings.length === 0) {
    body = (
      <p className="fc-muted fc-record__small">
        No finding has been linked to this record yet. When someone marks a finding here, they can link it from the
        finding's page.
      </p>
    );
  } else {
    body = (
      <>
        <ul className="fc-linked-findings">
          {findings.map((finding) => (
            <FindingItem key={finding.public_id} finding={finding} meta={meta} />
          ))}
        </ul>
        {query.hasNextPage ? (
          <Button
            size="sm"
            variant="ghost"
            disabled={query.isFetchingNextPage}
            onClick={() => void query.fetchNextPage()}
          >
            {query.isFetchingNextPage ? "Loading…" : "Show more"}
          </Button>
        ) : null}
      </>
    );
  }

  return (
    <section className="fc-record__section" aria-labelledby="record-findings">
      <h3 className="fc-record__heading" id="record-findings">
        Findings linked to it
      </h3>
      {body}
    </section>
  );
}
