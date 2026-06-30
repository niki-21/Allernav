import type {
  AllergyTag,
  MenuItem,
  PlaceMenu,
  RecommendedMenuItem,
  ReviewEvidence,
} from "../lib/types.ts";

const ALLERGEN_LABELS: Record<AllergyTag, string> = {
  peanut: "peanut",
  tree_nut: "tree nut",
  dairy: "dairy",
  egg: "egg",
  shellfish: "shellfish",
  fish: "fish",
  soy: "soy",
  sesame: "sesame",
  wheat_gluten: "gluten",
};

const ALLERGEN_TERMS: Record<AllergyTag, string[]> = {
  peanut: ["peanut", "peanuts", "satay", "groundnut"],
  tree_nut: ["almond", "walnut", "pecan", "cashew", "hazelnut", "pistachio", "nut", "nuts"],
  dairy: ["milk", "butter", "cream", "cheese", "yogurt"],
  egg: ["egg", "eggs", "mayo", "mayonnaise", "aioli"],
  shellfish: ["shrimp", "prawn", "crab", "lobster", "shellfish", "scallop"],
  fish: ["fish", "salmon", "tuna", "anchovy", "cod", "tilapia"],
  soy: ["soy", "tofu", "edamame", "soy sauce", "miso"],
  sesame: ["sesame", "tahini"],
  wheat_gluten: ["wheat", "gluten", "breaded", "bun", "soy sauce", "pasta", "noodle"],
};

function itemText(name: string, description?: string | null): string {
  return `${name} ${description ?? ""}`.toLowerCase();
}

function inferRisk(allergens: AllergyTag[], name: string, description?: string | null): AllergyTag[] {
  const haystack = itemText(name, description);
  return allergens.filter((allergen) => ALLERGEN_TERMS[allergen].some((term) => haystack.includes(term)));
}

function explicitRisk(allergens: AllergyTag[], item: MenuItem): AllergyTag[] {
  return allergens.filter((allergen) => item.likely_risky_for.includes(allergen));
}

function detectSharedPrepRisk(name: string, description?: string | null): boolean {
  const haystack = itemText(name, description);
  return /fried|crispy|tempura|shared|sampler|combo|tabletop|bbq|barbecue|fryer/.test(haystack);
}

function isEligibleRecommendation(item: MenuItem, allergens: AllergyTag[]): boolean {
  if (item.risk_label) {
    return item.risk_label === "possible_lower_risk";
  }
  const riskyAllergens = Array.from(
    new Set([...inferRisk(allergens, item.name, item.description), ...explicitRisk(allergens, item)]),
  );

  if (riskyAllergens.length > 0) {
    return false;
  }

  if (detectSharedPrepRisk(item.name, item.description)) {
    return false;
  }

  const crossContactPenalty = 0;
  return lowerRiskItemScore(item.name, item.description) - crossContactPenalty >= 0;
}

function lowerRiskItemScore(name: string, description?: string | null): number {
  const haystack = itemText(name, description);
  let score = 0;

  if (/grilled|roasted|baked|broiled/.test(haystack)) {
    score += 3;
  }
  if (/chicken|rice|salad|vegetable|veggie|bowl|steak/.test(haystack)) {
    score += 2;
  }
  if (/fried|crispy|tempura|alfredo|creamy|shrimp|peanut|sesame/.test(haystack)) {
    score -= 2;
  }

  return score;
}

function buildRecommendationCaution(evidence: ReviewEvidence[]): string {
  if (evidence.some((item) => item.signal_type === "reaction_report")) {
    return "Past reviews mention reactions, so verify ingredients and prep before ordering.";
  }

  if (evidence.some((item) => item.signal_type === "cross_contact_risk")) {
    return "Reviews mention cross-contact risk here, so verify dedicated prep.";
  }

  if (evidence.some((item) => item.signal_type === "uncertainty")) {
    return "Staff certainty looked mixed in reviews, so double-check prep details.";
  }

  return "";
}

function buildItemCaution(item: MenuItem, evidence: ReviewEvidence[]): string {
  if (detectSharedPrepRisk(item.name, item.description)) {
    return "Shared grill or fryer prep may still create cross-contact.";
  }

  return buildRecommendationCaution(evidence);
}

function allergenPhrase(allergens: AllergyTag[]): string {
  return allergens.map((allergen) => ALLERGEN_LABELS[allergen]).join(" / ");
}

function buildRecommendationReason(item: MenuItem, allergens: AllergyTag[], score: number): string {
  const haystack = itemText(item.name, item.description);
  const allergenText = allergenPhrase(allergens);

  if (/cold brew|coffee|tea|lemonade|drink/.test(haystack)) {
    return `Plain drink-style option with fewer obvious ${allergenText} flags.`;
  }
  if (/salad|greens/.test(haystack)) {
    return `Simple salad-style item with no listed ${allergenText} terms.`;
  }
  if (/rice|bowl/.test(haystack)) {
    return `Bowl-style item with fewer obvious ${allergenText} terms.`;
  }
  if (score > 0) {
    return `Simpler ingredient wording with no listed ${allergenText} terms.`;
  }

  return `No listed ${allergenText} terms were detected in this item.`;
}

function heuristicRecommendationsWithEvidence(
  menu: PlaceMenu,
  allergens: AllergyTag[],
  evidence: ReviewEvidence[],
): RecommendedMenuItem[] {
  return menu.sections
    .flatMap((section) =>
      section.items.map((item) => {
        const riskyAllergens = Array.from(
          new Set([...inferRisk(allergens, item.name, item.description), ...explicitRisk(allergens, item)]),
        );
        const crossContactPenalty = detectSharedPrepRisk(item.name, item.description) ? 2 : 0;
        const score = lowerRiskItemScore(item.name, item.description) - crossContactPenalty;
        return {
          item,
          sectionTitle: section.title,
          riskyAllergens,
          score,
        };
      }),
    )
    .filter((entry) => isEligibleRecommendation(entry.item, allergens) && entry.score >= 0)
    .sort((left, right) => right.score - left.score || left.item.name.localeCompare(right.item.name))
    .slice(0, 3)
    .map((entry) => ({
      name: entry.item.name,
      section_title: entry.sectionTitle,
      reason: buildRecommendationReason(entry.item, allergens, entry.score),
      caution: buildItemCaution(entry.item, evidence) || null,
      source: "heuristic" as const,
    }));
}

function extractGeminiText(payload: Record<string, unknown>): string | null {
  const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
  for (const candidate of candidates) {
    const content = (candidate as { content?: { parts?: unknown[] } })?.content;
    const parts = Array.isArray(content?.parts) ? content.parts : [];
    const text = parts
      .map((part) => ((part as { text?: unknown }).text && typeof (part as { text: unknown }).text === "string" ? (part as { text: string }).text : ""))
      .join("")
      .trim();
    if (text) {
      return text.replace(/^```json\s*/i, "").replace(/```$/i, "").trim();
    }
  }
  return null;
}

async function geminiRecommendations(
  placeName: string,
  allergens: AllergyTag[],
  menu: PlaceMenu,
  evidence: ReviewEvidence[],
): Promise<RecommendedMenuItem[] | null> {
  const apiKey = process.env.GEMINI_API_KEY?.trim();
  if (!apiKey) {
    return null;
  }

  const model = process.env.GEMINI_MODEL?.trim() || "gemini-3.5-flash";
  const prompt = JSON.stringify({
    task:
      "Recommend up to 3 existing menu items to verify for a diner with allergies. Do not call any item safe. Separate confirmed ingredients, inferred risks, and unknowns in the reasoning.",
    place_name: placeName,
    selected_allergens: allergens,
    evidence: evidence.slice(0, 4).map((item) => ({
      signal_label: item.signal_label,
      impact: item.impact,
      matched_allergens: item.matched_allergens,
      excerpt: item.excerpt,
    })),
    menu,
    output_schema: {
      recommendations: [
        {
          name: "existing menu item name",
          section_title: "menu section title",
          reason: "one sentence; say verify with staff when inferred",
          caution: "required when information is inferred or unknown",
        },
      ],
    },
  });

  const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey,
    },
    body: JSON.stringify({
      contents: [
        {
          role: "user",
          parts: [
            {
              text:
                "You recommend restaurant menu items for people with food allergies. Only recommend items that exist in the provided menu. Reply with strict JSON only.\n\n" +
                prompt,
            },
          ],
        },
      ],
      generationConfig: {
        responseMimeType: "application/json",
      },
    }),
  });

  if (!response.ok) {
    return null;
  }

  const payload = (await response.json()) as Record<string, unknown>;
  const outputText = extractGeminiText(payload);
  if (!outputText) {
    return null;
  }

  try {
    const parsed = JSON.parse(outputText) as {
      recommendations?: Array<{
        name: string;
        section_title?: string | null;
        reason: string;
        caution?: string | null;
      }>;
    };

    if (!Array.isArray(parsed.recommendations)) {
      return null;
    }

    const validNames = new Set(menu.sections.flatMap((section) => section.items.map((item) => item.name)));
    const itemsByName = new Map(menu.sections.flatMap((section) => section.items.map((item) => [item.name, item] as const)));

    return parsed.recommendations
      .filter((item) => validNames.has(item.name))
      .filter((item) => {
        const menuItem = itemsByName.get(item.name);
        return menuItem ? isEligibleRecommendation(menuItem, allergens) : false;
      })
      .map((item) => ({
        name: item.name,
        section_title: item.section_title ?? null,
        reason: item.reason,
        caution: item.caution ?? null,
        source: "llm" as const,
      }));
  } catch {
    return null;
  }
}

export async function recommendMenuItems(
  placeName: string,
  allergens: AllergyTag[],
  menu: PlaceMenu | null,
  evidence: ReviewEvidence[],
): Promise<RecommendedMenuItem[]> {
  if (!menu || menu.sections.length === 0) {
    return [];
  }

  try {
    const llm = await geminiRecommendations(placeName, allergens, menu, evidence);
    if (llm && llm.length > 0) {
      return llm;
    }
  } catch {
    // Fall back to heuristic recommendations when the LLM is unavailable.
  }

  return heuristicRecommendationsWithEvidence(menu, allergens, evidence);
}
