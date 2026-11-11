import { Attribution, safeHref } from "../../map/attribution.js";
import type { SourceRef } from "./api.js";

/** The licence's name, as a link to its terms when it has a web address. */
function Licence({ source }: { source: SourceRef }) {
  const licenceUrl = safeHref(source.licence_url);
  return licenceUrl ? (
    <a href={licenceUrl} target="_blank" rel="noopener noreferrer external">
      {source.licence}
    </a>
  ) : (
    source.licence
  );
}

/**
 * Who published a record and on what terms, as its licence requires it be
 * shown (Decision 0004). The attribution may carry links. They are kept only
 * when they are web addresses, like every attribution on the map.
 *
 * The compact form is the source's name and its licence, for a list of
 * records or the search box's results. The full credit is on each record's
 * page.
 */
export function SourceCredit({ source, compact = false }: { source: SourceRef; compact?: boolean }) {
  if (compact) {
    return (
      <span className="fc-source-credit fc-source-credit--compact">
        {source.name} · <Licence source={source} />
      </span>
    );
  }
  return (
    <div className="fc-source-credit">
      <p>
        <strong>{source.name}</strong>, published by {source.publisher}.
      </p>
      <p>
        Licence: <Licence source={source} />
      </p>
      <p className="fc-source-credit__attribution">
        <Attribution html={source.attribution} />
      </p>
    </div>
  );
}
