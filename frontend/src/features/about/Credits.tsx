import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import { isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { Attribution, safeHref } from "../../map/attribution.js";
import { Button } from "../../ui/Button.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { aboutKeys, fetchLiveSources } from "./api.js";
import { type Credit, creditCount, creditGroups, searchCredits } from "./creditList.js";

/** A link to another site, or just its words when the address isn't a web address. */
function OutLink({ address, children }: { address: string; children: string }) {
  const href = safeHref(address);
  if (!href) return <>{children}</>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <ExternalLink size={12} aria-hidden className="fc-about__external" />
      <span className="fc-visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}

export function CreditItem({ credit }: { credit: Credit }) {
  return (
    <li className="fc-about__credit">
      <strong className="fc-about__credit-name">{credit.name}</strong>
      {credit.publisher ? <span className="fc-about__muted">{credit.publisher}</span> : null}
      {credit.licence ? (
        <span>
          Licence:{" "}
          {credit.licenceUrl ? <OutLink address={credit.licenceUrl}>{credit.licence}</OutLink> : credit.licence}
        </span>
      ) : null}
      {credit.attribution ? (
        <span className="fc-about__credit-line">
          <Attribution html={credit.attribution} />
        </span>
      ) : null}
      {credit.homepage && safeHref(credit.homepage) ? <OutLink address={credit.homepage}>Their website</OutLink> : null}
    </li>
  );
}

/**
 * Every source of data the API lists, with its licence and credit, grouped by
 * kind and searchable. The live sources are asked for separately, so the
 * rest shows at once and a failure there is said in its own place.
 */
export function Credits({ meta }: { meta: Meta }) {
  const [search, setSearch] = useState("");
  const deferred = useDeferredValue(search);
  const live = useQuery({
    queryKey: aboutKeys.liveSources,
    queryFn: ({ signal }) => fetchLiveSources(signal),
    staleTime: Number.POSITIVE_INFINITY,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });
  const groups = useMemo(() => creditGroups(meta, live.data ?? []), [meta, live.data]);
  const shown = useMemo(() => searchCredits(groups, deferred), [groups, deferred]);
  const total = creditCount(groups);
  const found = creditCount(shown);
  const searching = deferred.trim() !== "";

  return (
    <div className="fc-about__credits">
      <Field label="Search the sources" hint="By name, publisher or licence.">
        {(control) => (
          <input
            {...control}
            className="fc-input"
            type="search"
            value={search}
            autoComplete="off"
            onChange={(event) => setSearch(event.target.value)}
          />
        )}
      </Field>
      <p className="fc-about__muted" role="status">
        {searching
          ? found === 0
            ? `Nothing matches “${deferred.trim()}”.`
            : `${found} of ${total} sources match.`
          : `${total} sources.`}
      </p>
      {searching && found === 0 ? (
        <Button size="sm" onClick={() => setSearch("")}>
          Clear the search
        </Button>
      ) : null}
      {shown.map((group) => (
        // Closed to start with, so the kinds of data can be scanned, and open while searching, so matches show.
        <details key={`${group.id}-${searching}`} className="fc-about__group" open={searching}>
          <summary className="fc-about__group-title">
            {group.title} <span className="fc-about__muted">({group.credits.length})</span>
          </summary>
          <p className="fc-about__muted">{group.about}</p>
          <ul className="fc-about__credit-list">
            {group.credits.map((credit) => (
              <CreditItem key={credit.key} credit={credit} />
            ))}
          </ul>
        </details>
      ))}
      {live.isPending ? (
        <div role="status" className="fc-about__status">
          <span className="fc-visually-hidden">Asking which services your browser looks things up from</span>
          <Skeleton lines={2} />
        </div>
      ) : null}
      {live.isError ? (
        <div className="fc-about__status" role="alert">
          <p>The list of services your browser looks things up from didn't load.</p>
          <Button size="sm" onClick={() => void live.refetch()}>
            Try again
          </Button>
        </div>
      ) : null}
    </div>
  );
}
