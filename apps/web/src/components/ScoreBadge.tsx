import type { PlaceScoreSummary, Verdict } from "@/lib/types";

const VERDICT_COPY: Record<Verdict, string> = {
  good_fit: "Good Fit",
  use_caution: "Use Caution",
  high_risk: "High Risk",
};

const LIMITED_COPY: Record<Verdict, string> = {
  good_fit: "Menu-led",
  use_caution: "Low Evidence",
  high_risk: "Menu Risk",
};

export default function ScoreBadge({ summary }: { summary: PlaceScoreSummary }) {
  const badgeCopy = summary.meaningful_evidence ? VERDICT_COPY[summary.fit_verdict] : LIMITED_COPY[summary.fit_verdict];

  return (
    <div className={`score-badge ${summary.fit_verdict} ${summary.meaningful_evidence ? "" : "limited"}`.trim()}>
      <div className="score-badge-value">{summary.fit_score}</div>
      <div className="score-badge-copy">
        <span>AI Fit</span>
        <strong>{badgeCopy}</strong>
      </div>
    </div>
  );
}
