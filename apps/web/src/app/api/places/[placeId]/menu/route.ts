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
      source_fetched_at: menu.source_fetched_at ?? null,
      status: menu.status ?? "complete",
      content_type: menu.content_type ?? null,
      document_url: menu.document_url ?? null,
      document_urls: menu.document_urls ?? [],
      menu_version: menu.menu_version ?? null,
      extraction_method: menu.extraction_method ?? null,
      page_count: menu.page_count ?? null,
      extraction_confidence: menu.extraction_confidence ?? null,
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
