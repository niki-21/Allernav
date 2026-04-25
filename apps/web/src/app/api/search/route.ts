import { NextResponse } from "next/server";

import { GooglePlacesError } from "../../../server/googlePlaces.ts";
import { isAllergyTag, searchPlacesService, type SearchRequestPayload } from "../../../server/service.ts";

export const runtime = "nodejs";

function isValidCenter(value: unknown): value is { lat: number; lng: number } {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { lat?: unknown }).lat === "number" &&
    Number.isFinite((value as { lat: number }).lat) &&
    typeof (value as { lng?: unknown }).lng === "number" &&
    Number.isFinite((value as { lng: number }).lng)
  );
}

function parseSearchPayload(input: unknown): SearchRequestPayload {
  if (typeof input !== "object" || input === null) {
    throw new Error("Request body must be a JSON object.");
  }

  const payload = input as {
    query?: unknown;
    center?: unknown;
    allergens?: unknown;
    max_results?: unknown;
    maxResults?: unknown;
  };

  if (payload.query !== undefined && typeof payload.query !== "string") {
    throw new Error("query must be a string.");
  }

  if (payload.center !== undefined && payload.center !== null && !isValidCenter(payload.center)) {
    throw new Error("center must include numeric lat and lng values.");
  }

  let allergens: SearchRequestPayload["allergens"];
  if (payload.allergens !== undefined) {
    if (
      !Array.isArray(payload.allergens) ||
      !payload.allergens.every((item) => typeof item === "string" && isAllergyTag(item))
    ) {
      throw new Error("allergens must be an array of supported allergy tags.");
    }
    allergens = payload.allergens;
  }

  const maxResults = payload.maxResults ?? payload.max_results;
  if (maxResults !== undefined && (typeof maxResults !== "number" || !Number.isFinite(maxResults))) {
    throw new Error("max_results must be a number.");
  }

  return {
    query: payload.query,
    center: payload.center ?? undefined,
    allergens,
    maxResults: maxResults as number | undefined,
  };
}

export async function POST(request: Request) {
  let input: unknown;

  try {
    input = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body." }, { status: 400 });
  }

  try {
    const payload = parseSearchPayload(input);
    const response = await searchPlacesService(payload);
    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof GooglePlacesError) {
      return NextResponse.json({ detail: error.message }, { status: 502 });
    }
    return NextResponse.json(
      {
        detail: error instanceof Error ? error.message : "Search failed.",
      },
      { status: 400 },
    );
  }
}
