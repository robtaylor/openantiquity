import { useQuery } from "@tanstack/react-query";
import { Landmark } from "lucide-react";
import type { Meta } from "../../../api/meta.js";
import { Button } from "../../../ui/Button.js";
import { fetchSuggestedRecords } from "../api.js";
import { distanceWords, labelOf } from "../describe.js";
import { findingPageKeys } from "../keys.js";

/** How many suggestions the card shows. The record form lists them all. */
const SHOWN = 3;

/**
 * "Is it one of these?" (DESIGN.md, "Findings"): the heritage records the
 * server suggests for this finding, each with its source and distance, and
 * one button to link it. Matching a known record is a good result.
 */
export function RecordSuggestions({
  meta,
  publicId,
  onLink,
}: {
  meta: Meta;
  publicId: string;
  onLink: (recordId: number) => void;
}) {
  const suggestions = useQuery({
    queryKey: findingPageKeys.suggestions(publicId),
    queryFn: ({ signal }) => fetchSuggestedRecords(publicId, signal),
    staleTime: 60_000,
  });
  const items = suggestions.data?.items.slice(0, SHOWN) ?? [];
  if (items.length === 0) return null;
  return (
    <section className="fc-finding__section fc-suggestions" aria-labelledby="fc-suggestions-title">
      <h3 id="fc-suggestions-title">Is it one of these?</h3>
      <p className="fc-finding__hint">
        Heritage records near it. If it's already recorded, linking it is a good result: it shows a sharp eye.
      </p>
      <ul className="fc-record-list">
        {items.map((record) => (
          <li key={record.id} className="fc-suggestion">
            <Landmark size={18} aria-hidden />
            <span className="fc-suggestion__text">
              <span className="fc-record-choice__name">{record.name}</span>
              <span className="fc-record-choice__meta">
                {record.source.name} · {labelOf(meta.vocab.record_categories, record.category)} ·{" "}
                {distanceWords(record.distance_m)}
              </span>
            </span>
            <Button size="sm" onClick={() => onLink(record.id)} aria-label={`Link ${record.name}`}>
              Link it
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
