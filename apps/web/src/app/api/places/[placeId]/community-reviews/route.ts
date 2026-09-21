import { NextResponse } from "next/server";

import { getCommunityReviews, saveCommunityReview } from "../../../../../server/platform.ts";

export const runtime = "nodejs";

export async function GET(_request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;

  return NextResponse.json({
    reviews: await getCommunityReviews(placeId),
    submission_requires_login_for_points: true,
    verification_model: "allernav_account_plus_visit_context",
  });
}

export async function POST(request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  try {
    const result = await saveCommunityReview(placeId, await request.json());
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Review could not be saved." },
      { status: 400 },
    );
  }
}
