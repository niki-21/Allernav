import { NextResponse } from "next/server";

import { getCommunityReviews } from "../../../../../server/platform.ts";

export const runtime = "nodejs";

export async function GET(_request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;

  return NextResponse.json({
    reviews: getCommunityReviews(placeId),
    submission_requires_google_sign_in: true,
    verification_model: "auth_plus_visit_proof",
  });
}
