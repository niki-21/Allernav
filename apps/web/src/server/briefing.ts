import type {
  PlaceDecisionBrief,
  PlaceMenu,
  PlaceScoreSummary,
  RecommendedMenuItem,
  ReviewEvidence,
} from "../lib/types.ts";

function uniqueValues(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function hasSignal(evidence: ReviewEvidence[], signalType: ReviewEvidence["signal_type"]): boolean {
  return evidence.some((item) => item.signal_type === signalType);
}

function buildCautionFlags(
  summary: PlaceScoreSummary,
  evidence: ReviewEvidence[],
  menu: PlaceMenu | null,
): string[] {
  const flags: string[] = [];

  if (!summary.meaningful_evidence) {
    flags.push("Low allergy-specific evidence");
  }
  if (summary.evidence_confidence < 0.45) {
    flags.push("Confidence is still limited");
  }
  if (!menu || menu.sections.length === 0) {
    flags.push("No menu snapshot found");
  }
  if (hasSignal(evidence, "cross_contact_risk")) {
    flags.push("Cross-contact mentioned in reviews");
  }
  if (hasSignal(evidence, "uncertainty")) {
    flags.push("Staff certainty looked mixed");
  }
  if (hasSignal(evidence, "reaction_report")) {
    flags.push("Reaction reports were found");
  }

  return uniqueValues(flags).slice(0, 4);
}

export function buildDecisionBrief(
  summary: PlaceScoreSummary,
  evidence: ReviewEvidence[],
  menu: PlaceMenu | null,
  recommendedItems: RecommendedMenuItem[],
): PlaceDecisionBrief {
  const positiveCount = evidence.filter((item) => item.impact === "positive").length;
  const negativeCount = evidence.filter((item) => item.impact === "negative").length;
  const cautionFlags = buildCautionFlags(summary, evidence, menu);

  let headline = `Low-confidence read`;
  let summaryText = `There is not enough allergy-specific evidence to rank this place with confidence.`;
  let recommendedAction = `Use this as a backup option and verify ingredients and prep details before ordering.`;

  if (!summary.meaningful_evidence && menu && menu.sections.length > 0) {
    headline = recommendedItems.length > 0 ? "Menu-led read" : "Harder fit from the menu";
    summaryText =
      recommendedItems.length > 0
        ? "No allergy-specific reviews showed up, so this read is mostly coming from the local menu snapshot."
        : "No allergy-specific reviews showed up, and the menu snapshot still looks harder to navigate for this allergy set.";
    recommendedAction =
      recommendedItems.length > 0
        ? "Use one of the simpler items below as a starting point, then confirm prep."
        : "Treat this as a tougher fit unless staff can clearly walk through ingredients and prep.";
  }

  if (summary.fit_verdict === "good_fit" && summary.meaningful_evidence) {
    headline = `One of the stronger current matches`;
    summaryText = `${positiveCount} reassuring signal${positiveCount === 1 ? "" : "s"} and ${negativeCount} risk note${negativeCount === 1 ? "" : "s"} were found in the review scan.`;
    recommendedAction = `Start here, but still confirm current prep flow, shared oil, and any substitutions before ordering.`;
  } else if (summary.fit_verdict === "high_risk") {
    headline = `Risk signals outweigh reassurance here`;
    summaryText = summary.meaningful_evidence
      ? `The available evidence leans more risky than reassuring.`
      : `Even with limited reviews, the available signals lean risky for this allergy set.`;
    recommendedAction = `Choose another option first if you can. Only continue if the restaurant can clearly explain a safer prep path.`;
  } else if (summary.meaningful_evidence) {
    headline = `Possible fit, but verify before ordering`;
    summaryText = `The review scan found mixed evidence: ${positiveCount} reassuring signal${positiveCount === 1 ? "" : "s"} and ${negativeCount} caution note${negativeCount === 1 ? "" : "s"}.`;
    recommendedAction = `Treat this as a maybe, and verify cross-contact, fryer use, and ingredient handling before committing.`;
  }

  return {
    headline,
    summary: summaryText,
    recommended_action: recommendedAction,
    caution_flags: cautionFlags,
  };
}
