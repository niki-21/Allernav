import { NextResponse } from "next/server";

import { fetchBackendPlaceMenu } from "../../../../../server/fastapi.ts";

export const runtime = "nodejs";

export async function GET(_request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  const menu = await fetchBackendPlaceMenu(placeId);
  if (menu) {
    return NextResponse.json({
      place_id: placeId,
      source_url: menu.source_url ?? null,
      source_fetched_at: null,
      status: "complete",
      sections: menu.sections,
    });
  }

  return NextResponse.json({
    place_id: placeId,
    source_url: null,
    source_fetched_at: null,
    status: "missing",
    sections: [],
  });
}
