import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function GET(_request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  return NextResponse.json({
    place_id: placeId,
    source_url: null,
    source_fetched_at: null,
    status: "missing",
    sections: [],
  });
}
