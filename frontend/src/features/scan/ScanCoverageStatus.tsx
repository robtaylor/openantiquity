import { type ScanCoverageSummary, useScanCoverage } from "./useScanOnMap.js";
import { squaresWords } from "./words.js";
import "./scan.css";

/** What the scan coverage layer can say about the view, in a sentence, or null when there is nothing to say. */
export function coverageSentence(summary: ScanCoverageSummary): string | null {
  switch (summary.status) {
    case "off":
    case "failed":
      // A failure has the layer panel's own notice and "Try again".
      return null;
    case "wide":
      return "Zoom in to see scan coverage. This view is too wide to ask about all at once.";
    case "loading":
      return "Looking up who has scanned here…";
    case "ready":
      return summary.scanned === 0
        ? "Nobody has scanned a square around here yet."
        : `${squaresWords(summary.scanned)} around here ${summary.scanned === 1 ? "has" : "have"} been looked over. The darker the square, the more people have.`;
  }
}

/** The scan coverage layer's line under its switch, in the layer panel and while scanning. */
export function ScanCoverageStatus() {
  const summary = useScanCoverage((state) => state.summary);
  const sentence = coverageSentence(summary);
  return (
    <p className="fc-scan-coverage" role="status" data-status={summary.status}>
      {sentence}
    </p>
  );
}
