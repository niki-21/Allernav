import type { PlaceScoreSummary, Verdict } from "@/lib/types";

const VERDICT_COPY: Record<Verdict, string> = {
  good_fit: "Good Fit",
  use_caution: "Use Caution",
  high_risk: "High Risk",
};

export default function ScoreBadge({ summary }: { summary: PlaceScoreSummary }) {
  return (
    <div className={`score-badge ${summary.verdict}`}>
      <div className="score-badge-value">{summary.score}</div>
      <div className="score-badge-copy">
        <span>Allergy Fit</span>
        <strong>{VERDICT_COPY[summary.verdict]}</strong>
      </div>
    </div>
  );
}

