import { NextResponse } from "next/server";

import { getPlatformViewer } from "../../../../server/platform.ts";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json(getPlatformViewer());
}
