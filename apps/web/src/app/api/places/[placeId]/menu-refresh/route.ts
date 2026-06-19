import { NextResponse } from "next/server";

import { buildFastApiUrl } from "../../../../../server/fastapi.ts";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  const backendUrl = buildFastApiUrl(`/api/places/${encodeURIComponent(placeId)}/menu-refresh`);
  const now = new Date().toISOString();

  if (!backendUrl) {
    return NextResponse.json({
      id: `failed-${placeId}`,
      place_id: placeId,
      status: "failed",
      message: "FastAPI menu ingestion is not configured. Set FASTAPI_API_BASE_URL to enable menu refresh.",
      created_at: now,
      completed_at: now,
    });
  }

  const payload = (await request.json().catch(() => ({}))) as {
    restaurant_name?: string | null;
    website_url?: string | null;
  };
  const url = new URL(backendUrl);
  if (payload.restaurant_name) {
    url.searchParams.set("restaurant_name", payload.restaurant_name);
  }
  if (payload.website_url) {
    url.searchParams.set("website_url", payload.website_url);
  }

  try {
    const response = await fetch(url, {
      method: "POST",
      cache: "no-store",
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      return NextResponse.json(
        body ?? { detail: "FastAPI menu refresh failed." },
        { status: response.status },
      );
    }
    return NextResponse.json(body);
  } catch (error) {
    return NextResponse.json(
      {
        id: `failed-${placeId}`,
        place_id: placeId,
        status: "failed",
        message: error instanceof Error ? error.message : "FastAPI menu refresh failed.",
        created_at: now,
        completed_at: now,
      },
      { status: 502 },
    );
  }
}
