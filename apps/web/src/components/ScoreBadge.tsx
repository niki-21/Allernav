import type { PlaceScoreSummary, Verdict } from "@/lib/types";

const VERDICT_COPY: Record<Verdict, string> = {
  good_fit: "More Evidence",
  use_caution: "Use Caution",
  high_risk: "Risk Signals",
};

const LIMITED_COPY: Record<Verdict, string> = {
  good_fit: "Menu Signal",
  use_caution: "Low Evidence",
  high_risk: "Risk Signals",
};

export default function ScoreBadge({ summary }: { summary: PlaceScoreSummary }) {
  const badgeCopy = summary.meaningful_evidence ? VERDICT_COPY[summary.fit_verdict] : LIMITED_COPY[summary.fit_verdict];

  return (
    <div className={`score-badge ${summary.fit_verdict} ${summary.meaningful_evidence ? "" : "limited"}`.trim()}>
      <div className="score-badge-value">{summary.fit_score}</div>
      <div className="score-badge-copy">
        <span>Evidence</span>
        <strong>{badgeCopy}</strong>
      </div>
    </div>
  );
}
