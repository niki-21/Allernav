import type {
  AllergyTag,
  ImpactDirection,
  PlaceScoreSummary,
  ReviewEvidence,
  SignalType,
  Verdict,
} from "../lib/types.ts";
import type { GooglePlaceDetails } from "./googlePlaces.ts";

const ALLERGY_LABELS: Record<AllergyTag, string> = {
  peanut: "peanut",
  tree_nut: "tree nut",
  dairy: "dairy",
  egg: "egg",
  shellfish: "shellfish",
  fish: "fish",
  soy: "soy",
  sesame: "sesame",
  wheat_gluten: "wheat/gluten",
};

const ALLERGY_SYNONYMS: Record<AllergyTag, string[]> = {
  peanut: ["peanut", "peanuts", "peanut oil"],
  tree_nut: ["tree nut", "tree nuts", "almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut"],
  dairy: ["dairy", "milk", "butter", "cheese", "cream", "lactose"],
  egg: ["egg", "eggs", "egg wash"],
  shellfish: ["shellfish", "shrimp", "prawn", "lobster", "crab", "scallop"],
  fish: ["fish", "salmon", "tuna", "anchovy", "cod"],
  soy: ["soy", "soybean", "soy sauce", "tofu", "edamame"],
  sesame: ["sesame", "tahini"],
  wheat_gluten: ["gluten", "wheat", "celiac", "gluten free", "gluten-free"],
};

const GENERIC_ALLERGY_TERMS = [
  "allergy",
  "allergic",
  "allergen",
  "cross contact",
  "cross-contact",
  "cross contamination",
  "cross-contamination",
  "separate fryer",
  "dedicated fryer",
];

const NEGATIVE_OVERRIDES = [
  "not allergy friendly",
  "not allergy-friendly",
  "no allergy menu",
  "staff did not understand",
  "staff didn't understand",
  "could not guarantee",
  "couldn't guarantee",
  "shared fryer",
  "same fryer",
  "had a reaction",
  "got sick",
];

interface SignalConfig {
  signalType: SignalType;
  impact: ImpactDirection;
  label: string;
  phrases: string[];
  baseWeight: number;
  requiresAllergyContext?: boolean;
}

interface DetectedSignal {
  signalType: SignalType;
  impact: ImpactDirection;
  label: string;
  matchedPhrase: string;
  matchedAllergens: AllergyTag[];
  weight: number;
}

const POSITIVE_SIGNALS: SignalConfig[] = [
  {
    signalType: "accommodation",
    impact: "positive",
    label: "Strong allergy accommodations",
    phrases: [
      "allergy friendly",
      "allergy-friendly",
      "felt safe",
      "safe for my allergy",
      "safe for allergies",
      "accommodating",
      "took my allergy seriously",
      "careful with my allergy",
      "dedicated fryer",
      "separate fryer",
      "separate prep",
    ],
    baseWeight: 1.2,
    requiresAllergyContext: true,
  },
  {
    signalType: "staff_knowledge",
    impact: "positive",
    label: "Knowledgeable staff",
    phrases: [
      "staff understood",
      "server understood",
      "manager understood",
      "knowledgeable about allergies",
      "answered all my questions",
      "double checked",
      "checked with the kitchen",
      "reassured me",
    ],
    baseWeight: 1,
    requiresAllergyContext: true,
  },
  {
    signalType: "menu_labeling",
    impact: "positive",
    label: "Clear menu labeling",
    phrases: [
      "allergy menu",
      "clearly labeled",
      "labeled allergens",
      "marked gluten free",
      "marked gluten-free",
      "gluten free options",
      "gluten-free options",
    ],
    baseWeight: 0.9,
    requiresAllergyContext: true,
  },
];

const NEGATIVE_SIGNALS: SignalConfig[] = [
  {
    signalType: "uncertainty",
    impact: "negative",
    label: "Explicitly not allergy-friendly",
    phrases: ["not allergy friendly", "not allergy-friendly"],
    baseWeight: 1.7,
    requiresAllergyContext: true,
  },
  {
    signalType: "reaction_report",
    impact: "negative",
    label: "Reported allergic reaction",
    phrases: ["had a reaction", "got sick", "anaphylaxis", "epi pen", "epipen", "hives", "threw up", "vomited", "itchy after eating"],
    baseWeight: 2.2,
    requiresAllergyContext: true,
  },
  {
    signalType: "cross_contact_risk",
    impact: "negative",
    label: "Cross-contact risk mentioned",
    phrases: [
      "cross contamination",
      "cross-contamination",
      "cross contact",
      "cross-contact",
      "shared fryer",
      "same fryer",
      "not safe",
      "unsafe",
      "contaminated",
    ],
    baseWeight: 1.6,
    requiresAllergyContext: true,
  },
  {
    signalType: "uncertainty",
    impact: "negative",
    label: "Uncertain allergy handling",
    phrases: [
      "didn't know",
      "did not know",
      "not sure",
      "uncertain",
      "couldn't answer",
      "could not answer",
      "couldn't guarantee",
      "could not guarantee",
      "wouldn't recommend",
      "be careful",
    ],
    baseWeight: 1.1,
    requiresAllergyContext: true,
  },
];

function normalizeText(text: string): string {
  return text.toLowerCase().replace(/\s+/g, " ").trim();
}

function findPhrase(text: string, phrases: string[]): string | null {
  return phrases.find((phrase) => text.includes(phrase)) ?? null;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function termMatches(text: string, term: string): boolean {
  const normalizedTerm = term.toLowerCase().trim();
  if (!normalizedTerm) {
    return false;
  }
  const pattern = normalizedTerm.includes(" ")
    ? escapeRegex(normalizedTerm).replace(/\s+/g, "\\s+")
    : escapeRegex(normalizedTerm);
  return new RegExp(`(^|[^a-z0-9])${pattern}([^a-z0-9]|$)`, "i").test(text);
}

function findAllergens(text: string, selectedAllergens: AllergyTag[]): AllergyTag[] {
  return selectedAllergens.filter((allergen) => ALLERGY_SYNONYMS[allergen].some((term) => termMatches(text, term)));
}

function buildExcerpt(text: string, phrase: string, maxChars = 170): string {
  if (!phrase) {
    return text.slice(0, maxChars).trim();
  }

  const lowerText = text.toLowerCase();
  const index = lowerText.indexOf(phrase);
  if (index === -1) {
    return text.slice(0, maxChars).trim();
  }

  const start = Math.max(0, index - 55);
  const end = Math.min(text.length, index + phrase.length + 85);
  let excerpt = text.slice(start, end).trim();

  if (start > 0) {
    excerpt = `...${excerpt}`;
  }
  if (end < text.length) {
    excerpt = `${excerpt}...`;
  }

  return excerpt;
}

function buildSignal(
  config: SignalConfig,
  matchedPhrase: string,
  matchedAllergens: AllergyTag[],
  genericAllergyContext: boolean,
  rating?: number | null,
  publishTime?: string | null,
): DetectedSignal {
  const specificityMultiplier = matchedAllergens.length > 0 ? 1.35 : genericAllergyContext ? 0.78 : 0;

  let ratingMultiplier = 1;
  if (typeof rating === "number") {
    if (config.impact === "positive") {
      ratingMultiplier = rating >= 4 ? 1.08 : 0.92;
    } else {
      ratingMultiplier = rating <= 2 ? 1.12 : 1;
    }
  }

  let recencyMultiplier = 1;
  if (publishTime) {
    const publishedAt = Date.parse(publishTime);
    if (!Number.isNaN(publishedAt)) {
      const ageDays = Math.floor((Date.now() - publishedAt) / (1000 * 60 * 60 * 24));
      if (ageDays <= 365) {
        recencyMultiplier = 1.08;
      } else if (ageDays > 365 * 3) {
        recencyMultiplier = 0.9;
      }
    }
  }

  return {
    signalType: config.signalType,
    impact: config.impact,
    label: config.label,
    matchedPhrase,
    matchedAllergens,
    weight: config.baseWeight * specificityMultiplier * ratingMultiplier * recencyMultiplier,
  };
}

function detectSignals(
  reviewText: string,
  rating: number | null | undefined,
  publishTime: string | null | undefined,
  selectedAllergens: AllergyTag[],
): DetectedSignal[] {
  const normalized = normalizeText(reviewText);
  const matchedAllergens = findAllergens(normalized, selectedAllergens);
  const genericAllergyContext = GENERIC_ALLERGY_TERMS.some((term) => termMatches(normalized, term));
  const signals: DetectedSignal[] = [];

  for (const config of NEGATIVE_SIGNALS) {
    const phrase = findPhrase(normalized, config.phrases);
    if (!phrase) {
      continue;
    }
    if (config.requiresAllergyContext && !genericAllergyContext && matchedAllergens.length === 0) {
      continue;
    }

    if (
      config.signalType === "uncertainty" &&
      signals.some((signal) => signal.signalType === "reaction_report" || signal.signalType === "cross_contact_risk")
    ) {
      continue;
    }

    signals.push(buildSignal(config, phrase, matchedAllergens, genericAllergyContext, rating, publishTime));
  }

  for (const config of POSITIVE_SIGNALS) {
    const phrase = findPhrase(normalized, config.phrases);
    if (!phrase || NEGATIVE_OVERRIDES.some((override) => normalized.includes(override))) {
      continue;
    }
    if (config.requiresAllergyContext && !genericAllergyContext && matchedAllergens.length === 0) {
      continue;
    }

    signals.push(buildSignal(config, phrase, matchedAllergens, genericAllergyContext, rating, publishTime));
  }

  if (signals.length === 0 && genericAllergyContext && matchedAllergens.length > 0) {
    signals.push(
      buildSignal(
        {
          signalType: "uncertainty",
          impact: "negative",
          label: "Allergy mentioned without clear safeguards",
          phrases: ["allergy"],
          baseWeight: 0.6,
        },
        "allergy",
        matchedAllergens,
        genericAllergyContext,
        rating,
        publishTime,
      ),
    );
  }

  const deduped = new Map<string, DetectedSignal>();
  for (const signal of signals) {
    const key = `${signal.signalType}:${signal.impact}:${signal.matchedPhrase}`;
    const current = deduped.get(key);
    if (!current || signal.weight > current.weight) {
      deduped.set(key, signal);
    }
  }

  return Array.from(deduped.values());
}

function computeScore({
  rating,
  positiveTotal,
  negativeTotal,
  evidenceCount,
}: {
  rating?: number | null;
  positiveTotal: number;
  negativeTotal: number;
  evidenceCount: number;
}): number {
  const baseline = evidenceCount === 0 ? 48 : 52;
  const ratingAdjustment =
    typeof rating === "number" ? Math.max(-4, Math.min(4, Math.round((rating - 3.5) * 2))) : 0;

  const rawScore = baseline + positiveTotal * 14 - negativeTotal * 12 + ratingAdjustment;
  return Math.max(0, Math.min(100, Math.round(rawScore)));
}

function computeConfidence(evidenceCount: number, specificMentions: number): number {
  if (evidenceCount === 0) {
    return 0.18;
  }

  return Math.min(0.97, 0.22 + evidenceCount * 0.1 + specificMentions * 0.06);
}

function deriveVerdict(score: number, confidence: number, evidenceCount: number, severeNegative: boolean): Verdict {
  if (evidenceCount === 0) {
    return "use_caution";
  }
  if (severeNegative || score <= 32) {
    return "high_risk";
  }
  if (score >= 72 && confidence >= 0.42) {
    return "good_fit";
  }
  return "use_caution";
}

function buildExplanation(
  summary: PlaceScoreSummary,
  selectedAllergens: AllergyTag[],
  evidence: ReviewEvidence[],
): string {
  const allergenNames = selectedAllergens.map((allergen) => ALLERGY_LABELS[allergen]).join(", ");

  if (!summary.meaningful_evidence || evidence.length === 0) {
    return `There is very little review evidence about ${allergenNames} here, so Allernav keeps this rating cautious.`;
  }

  const positive = evidence.filter((item) => item.impact === "positive").length;
  const negative = evidence.filter((item) => item.impact === "negative").length;

  if (summary.verdict === "good_fit") {
    return `Review evidence for ${allergenNames} trends positive, with ${positive} reassuring signals and ${negative} risk notes.`;
  }
  if (summary.verdict === "high_risk") {
    return `Reviews include meaningful risk signals for ${allergenNames}, including direct warnings or reaction reports.`;
  }
  return `Reviews for ${allergenNames} are mixed or limited, so this place is better treated with caution.`;
}

export function analyzePlace(
  place: Pick<GooglePlaceDetails, "rating" | "reviews">,
  allergens: AllergyTag[],
): {
  summary: PlaceScoreSummary;
  evidence: ReviewEvidence[];
  explanation: string;
} {
  const selectedAllergens = Array.from(new Set<AllergyTag>(allergens));
  if (selectedAllergens.length === 0) {
    const score = Math.max(0, Math.min(100, Math.round(((place.rating ?? 0) / 5) * 100)));
    const verdict: PlaceScoreSummary["verdict"] = score >= 75 ? "good_fit" : "use_caution";
    return {
      summary: {
        score,
        verdict,
        confidence: place.rating != null ? 0.8 : 0.35,
        fit_score: score,
        fit_verdict: verdict,
        evidence_confidence: place.rating != null ? 0.8 : 0.35,
        positive_signals: [],
        negative_signals: [],
        evidence_count: 0,
        meaningful_evidence: false,
        evidence_status: "general",
        evidence_summary: "General restaurant signals",
      },
      evidence: [],
      explanation: "No allergies selected. This restaurant match uses its Google rating and popularity.",
    };
  }
  const evidenceItems: ReviewEvidence[] = [];
  const positiveCounter = new Map<string, number>();
  const negativeCounter = new Map<string, number>();
  let positiveTotal = 0;
  let negativeTotal = 0;
  let specificMentions = 0;
  let severeNegative = false;

  for (const review of place.reviews) {
    const reviewText = review.text.trim();
    if (!reviewText) {
      continue;
    }

    const detectedSignals = detectSignals(reviewText, review.rating, review.publish_time, selectedAllergens);
    for (const signal of detectedSignals) {
      const evidence: ReviewEvidence = {
        review_id: review.review_id,
        author_name: review.author_name ?? null,
        rating: review.rating ?? null,
        text: reviewText,
        matched_allergens: signal.matchedAllergens,
        signal_type: signal.signalType,
        impact: signal.impact,
        excerpt: buildExcerpt(reviewText, signal.matchedPhrase),
        matched_phrase: signal.matchedPhrase,
        signal_label: signal.label,
        tone: signal.impact === "positive" ? "reassuring" : "risk_note",
        is_allergy_relevant:
          signal.matchedAllergens.length > 0 ||
          GENERIC_ALLERGY_TERMS.some((term) => termMatches(normalizeText(reviewText), term)),
        weight: Math.round(signal.weight * 100) / 100,
        publish_time: review.publish_time ?? null,
      };

      evidenceItems.push(evidence);
      if (signal.impact === "positive") {
        positiveTotal += signal.weight;
        positiveCounter.set(signal.label, (positiveCounter.get(signal.label) ?? 0) + 1);
      } else {
        negativeTotal += signal.weight;
        negativeCounter.set(signal.label, (negativeCounter.get(signal.label) ?? 0) + 1);
      }

      if (signal.matchedAllergens.length > 0) {
        specificMentions += 1;
      }

      if (signal.signalType === "reaction_report" && signal.impact === "negative") {
        severeNegative = true;
      }
    }
  }

  evidenceItems.sort((a, b) => b.weight - a.weight);
  const trimmedEvidence = evidenceItems.slice(0, 8);
  const evidenceCount = trimmedEvidence.length;
  const confidence = computeConfidence(evidenceCount, specificMentions);
  const score = computeScore({
    rating: place.rating,
    positiveTotal,
    negativeTotal,
    evidenceCount,
  });
  const meaningfulEvidence = trimmedEvidence.some((item) => item.is_allergy_relevant);
  const verdict = deriveVerdict(score, confidence, evidenceCount, severeNegative);
  const summary: PlaceScoreSummary = {
    score,
    verdict,
    confidence: Math.round(confidence * 100) / 100,
    fit_score: score,
    fit_verdict: verdict,
    evidence_confidence: Math.round(confidence * 100) / 100,
    positive_signals: Array.from(positiveCounter.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([label]) => label),
    negative_signals: Array.from(negativeCounter.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([label]) => label),
    evidence_count: evidenceCount,
    meaningful_evidence: meaningfulEvidence,
    evidence_status: meaningfulEvidence ? "meaningful" : "limited",
    evidence_summary: meaningfulEvidence
      ? `${evidenceCount} allergy-aware review signal${evidenceCount === 1 ? "" : "s"}`
      : "Not enough allergy-specific review evidence",
  };

  return {
    summary,
    evidence: trimmedEvidence,
    explanation: buildExplanation(summary, selectedAllergens, trimmedEvidence),
  };
}
