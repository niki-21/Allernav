import { NextResponse } from "next/server";

import { formatAllergenLabel } from "@/lib/allergens";
import type { AllergyTag } from "@/lib/types";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  const payload = (await request.json().catch(() => ({}))) as {
    place_name?: string;
    allergens?: AllergyTag[];
    question?: string;
  };
  const allergens = Array.isArray(payload.allergens) ? payload.allergens : [];
  const allergenText = allergens.map(formatAllergenLabel).join(", ") || "my selected allergens";
  const placeName = payload.place_name || "this restaurant";
  const suggestedScript =
    payload.question ||
    `Hi, I am checking whether ${placeName} can accommodate ${allergenText}. Can you confirm ingredients, shared fryer or prep surfaces, and whether staff can prevent cross-contact?`;

  return NextResponse.json({
    id: crypto.randomUUID(),
    status: "queued",
    message:
      "Question request saved. Outbound restaurant messaging can be enabled after account and contact workflows are connected.",
    suggested_script: suggestedScript,
    place_id: placeId,
  });
}
