import { NextResponse } from "next/server";

import { fetchApifyReviews } from "../../../../../server/apifyReviews.ts";

export const runtime = "nodejs";

export async function POST(_request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  const now = new Date().toISOString();

  if (!process.env.APIFY_TOKEN?.trim()) {
    return NextResponse.json({
      id: `skipped-${placeId}`,
      place_id: placeId,
      status: "skipped",
      message: "Apify review expansion is not configured. Set APIFY_TOKEN to enable expanded review ingestion.",
      reviews_count: 0,
      reviews: [],
      created_at: now,
      completed_at: now,
    });
  }

  try {
    const reviews = await fetchApifyReviews(placeId);
    return NextResponse.json({
      id: `complete-${placeId}`,
      place_id: placeId,
      status: "complete",
      message: `Captured ${reviews.length} expanded review${reviews.length === 1 ? "" : "s"} from Apify.`,
      reviews_count: reviews.length,
      reviews,
      created_at: now,
      completed_at: new Date().toISOString(),
    });
  } catch (error) {
    return NextResponse.json(
      {
        id: `failed-${placeId}`,
        place_id: placeId,
        status: "failed",
        message: error instanceof Error ? error.message : "Apify review ingestion failed.",
        reviews_count: 0,
        reviews: [],
        created_at: now,
        completed_at: new Date().toISOString(),
      },
      { status: 502 },
    );
  }
}
