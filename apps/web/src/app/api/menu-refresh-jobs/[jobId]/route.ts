import { NextResponse } from "next/server";

import { buildFastApiUrl } from "../../../../server/fastapi.ts";

export const runtime = "nodejs";

export async function GET(_request: Request, context: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await context.params;
  const backendUrl = buildFastApiUrl(`/api/menu-refresh-jobs/${encodeURIComponent(jobId)}`);
  if (!backendUrl) {
    return NextResponse.json({ detail: "FastAPI menu ingestion is not configured." }, { status: 503 });
  }
  try {
    const response = await fetch(backendUrl, { cache: "no-store" });
    const body = await response.json().catch(() => null);
    return NextResponse.json(body ?? { detail: "Menu refresh job returned no JSON." }, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: error instanceof Error ? error.message : "Could not read menu refresh job." },
      { status: 502 },
    );
  }
}
