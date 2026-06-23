import { NextResponse } from "next/server";

import { buildFastApiUrl } from "../../../../server/fastapi.ts";

export const runtime = "nodejs";

function timeoutMs(): number {
  const parsed = Number(process.env.FASTAPI_RAG_TIMEOUT_MS ?? "20000");
  if (!Number.isFinite(parsed)) {
    return 20000;
  }
  return Math.max(1000, Math.min(30_000, Math.trunc(parsed)));
}

async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs());
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(request: Request) {
  const backendUrl = buildFastApiUrl("/api/rag/nearby-suggestions");
  if (!backendUrl) {
    return NextResponse.json(
      {
        detail: "FastAPI RAG backend is not configured. Set FASTAPI_API_BASE_URL to enable nearby suggestions.",
      },
      { status: 503 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body." }, { status: 400 });
  }

  try {
    const response = await fetchWithTimeout(backendUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => null);
    return NextResponse.json(payload ?? { detail: "FastAPI nearby RAG returned no JSON." }, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: error instanceof Error ? error.message : "FastAPI nearby RAG timed out or failed.",
      },
      { status: 502 },
    );
  }
}
