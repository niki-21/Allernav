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
      message: "FastAPI menu ingestion is not configured. Set FASTAPI_API_BASE_URL to enable menu ingestion.",
      created_at: now,
      completed_at: now,
    });
  }

  const incomingUrl = new URL(request.url);
  const payload = (await request.json().catch(() => ({}))) as {
    restaurant_name?: string | null;
    website_url?: string | null;
    force_refresh?: boolean;
  };
  const url = new URL(backendUrl);
  const restaurantName = payload.restaurant_name ?? incomingUrl.searchParams.get("restaurant_name");
  const websiteUrl = payload.website_url ?? incomingUrl.searchParams.get("website_url");
  const forceRefresh = payload.force_refresh ?? incomingUrl.searchParams.get("force_refresh") === "true";

  if (restaurantName) {
    url.searchParams.set("restaurant_name", restaurantName);
  }
  if (websiteUrl) {
    url.searchParams.set("website_url", websiteUrl);
  }
  if (forceRefresh) {
    url.searchParams.set("force_refresh", "true");
  }

  try {
    const response = await fetch(url, {
      method: "POST",
      cache: "no-store",
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      return NextResponse.json(
        body ?? { detail: "FastAPI menu ingestion failed." },
        { status: response.status },
      );
    }
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        id: `failed-${placeId}`,
        place_id: placeId,
        status: "failed",
        message: error instanceof Error
          ? `FastAPI menu ingestion failed: ${error.message}. Check FASTAPI_API_BASE_URL and the API deployment.`
          : "FastAPI menu ingestion failed. Check FASTAPI_API_BASE_URL and the API deployment.",
        created_at: now,
        completed_at: now,
      },
      { status: 502 },
    );
  }
}
