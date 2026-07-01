import { NextResponse } from "next/server";

import { buildFastApiUrl } from "../../../../../server/fastapi.ts";

export const runtime = "nodejs";

function sanitizedUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    url.username = "";
    url.password = "";
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return null;
  }
}

function sanitizedError(value: unknown): string {
  const raw = value instanceof Error ? `${value.name}: ${value.message}` : String(value || "Unknown upstream error");
  return raw
    .replace(/(["']?\b(?:api[_-]?key|token|secret|password|authorization)["']?\s*[:=]\s*["']?)([^"',;\s}]+)/gi, "$1[redacted]")
    .replace(/https?:\/\/[^\s]+/g, (match) => sanitizedUrl(match) ?? "[redacted-url]")
    .replace(/\s+/g, " ")
    .slice(0, 500);
}

function failedProxyJob(placeId: string, now: string, detail: string) {
  return {
    id: `failed-${placeId}`,
    place_id: placeId,
    status: "failed",
    message: detail,
    trace: [{
      id: "menu_ingestion_error",
      label: "Run menu discovery",
      status: "failed",
      provider: "nextjs_proxy",
      detail,
    }],
    created_at: now,
    completed_at: now,
  };
}

export async function POST(request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  const backendUrl = buildFastApiUrl(`/api/places/${encodeURIComponent(placeId)}/menu-refresh`);
  const now = new Date().toISOString();

  if (!backendUrl) {
    return NextResponse.json(failedProxyJob(
      placeId,
      now,
      "Menu scanning API is not configured. Set FASTAPI_API_BASE_URL on the web deployment.",
    ));
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

  console.info("[menu-refresh] request", {
    placeId,
    restaurant_name: restaurantName,
    website_url: sanitizedUrl(websiteUrl),
    force_refresh: forceRefresh,
  });

  try {
    const response = await fetch(url, {
      method: "POST",
      cache: "no-store",
    });
    const rawBody = await response.text();
    let body: unknown = null;
    try {
      body = rawBody ? JSON.parse(rawBody) as unknown : null;
    } catch {
      body = null;
    }
    console.info("[menu-refresh] response", {
      placeId,
      status: response.status,
      job_status: body && typeof body === "object" && "status" in body ? body.status : null,
    });
    if (!response.ok) {
      if (body && typeof body === "object") {
        return NextResponse.json(body, { status: response.status });
      }
      const detail = sanitizedError(rawBody || `FastAPI returned HTTP ${response.status}.`);
      return NextResponse.json(
        failedProxyJob(placeId, now, detail),
        { status: response.status },
      );
    }
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    const detail = sanitizedError(error);
    console.error("[menu-refresh] request failed", {
      placeId,
      restaurant_name: restaurantName,
      website_url: sanitizedUrl(websiteUrl),
      force_refresh: forceRefresh,
      error: detail,
    });
    return NextResponse.json(
      failedProxyJob(placeId, now, detail),
      { status: 502 },
    );
  }
}
