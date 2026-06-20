import { NextResponse } from "next/server";

import { GooglePlacesError } from "../../../../server/googlePlaces.ts";
import { getPlaceDetailsService, isAllergyTag } from "../../../../server/service.ts";

export const runtime = "nodejs";

export async function GET(request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  const { searchParams } = new URL(request.url);
  const rawAllergens = searchParams.getAll("allergens");

  if (rawAllergens.some((value) => !isAllergyTag(value))) {
    return NextResponse.json({ detail: "Unsupported allergen value." }, { status: 400 });
  }
  const allergens = rawAllergens.filter(isAllergyTag);

  try {
    const response = await getPlaceDetailsService(placeId, allergens);
    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof GooglePlacesError) {
      return NextResponse.json({ detail: error.message }, { status: 502 });
    }
    return NextResponse.json(
      {
        detail: error instanceof Error ? error.message : "Could not load place details.",
      },
      { status: 400 },
    );
  }
}
