import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(_request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  const now = new Date().toISOString();

  return NextResponse.json({
    id: crypto.randomUUID(),
    place_id: placeId,
    status: "queued",
    message:
      "Menu refresh queued. AllerNav will check compliant public menu sources and update this place when ready.",
    created_at: now,
    completed_at: null,
  });
}
