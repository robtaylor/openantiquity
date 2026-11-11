import type { CSSProperties } from "react";
import type { Meta, RecordCategory } from "../../api/meta.js";
import { COLOURS } from "../../ui/tokens.js";

/** A category from the vocabulary, or a stand-in for one it doesn't list yet. */
export function categoryOf(meta: Meta, id: string): RecordCategory {
  return (
    meta.vocab.record_categories.find((category) => category.id === id) ?? { id, label: id, colour: COLOURS.textMuted }
  );
}

/** The small square a record is drawn with on the map, in its category's colour. */
export function CategorySwatch({ colour, live = false }: { colour: string; live?: boolean }) {
  return (
    <span
      className={live ? "fc-record-swatch fc-record-swatch--live" : "fc-record-swatch"}
      style={{ "--swatch": colour } as CSSProperties}
      aria-hidden="true"
    />
  );
}

/** The category's square and its name, so the colour never has to speak for itself. */
export function CategoryMark({ meta, category }: { meta: Meta; category: string }) {
  const found = categoryOf(meta, category);
  return (
    <span className="fc-record-category">
      <CategorySwatch colour={found.colour} />
      {found.label}
    </span>
  );
}
