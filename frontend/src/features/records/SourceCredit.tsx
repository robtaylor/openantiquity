import { Attribution, safeHref } from "../../map/attribution.js";
import type { SourceRef } from "./api.js";

/**
 * Who published a record and on what terms, as its licence requires it be
 * shown (Decision 0004). The attribution may carry links. They are kept only
 * when they are web addresses, like every attribution on the map.
 */
export function SourceCredit({ source, compact = false }: { source: SourceRef; compact?: boolean }) {
  const licenceUrl = safeHref(source.licence_url);
  const licence = licenceUrl ? (
    <a href={licenceUrl} target="_blank" rel="noopener noreferrer external">
      {source.licence}
    </a>
  ) : (
    source.licence
  );
  if (compact) {
    return (
      <span className="fc-source-credit fc-source-credit--compact">
        {source.name} · {licence}
      </span>
    );
  }
  return (
    <div className="fc-source-credit">
      <p>
        <strong>{source.name}</strong>, published by {source.publisher}.
      </p>
      <p>Licence: {licence}</p>
      <p className="fc-source-credit__attribution">
        <Attribution html={source.attribution} />
      </p>
    </div>
  );
}
