import { NextResponse } from "next/server";

import { getAuthenticatedReviewer, getReviewerPoints } from "../../../../server/platform.ts";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const accessToken = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ?? null;
  const reviewer = await getAuthenticatedReviewer(accessToken);
  if (!reviewer) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }
  return NextResponse.json({ reviewer, total_points: await getReviewerPoints(reviewer.id) });
}
