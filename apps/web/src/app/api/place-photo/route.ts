import { NextResponse } from "next/server";

export const runtime = "nodejs";

function getApiKey(): string | null {
  return (
    process.env.GOOGLE_MAPS_API_KEY?.trim() ||
    process.env.GOOGLE_PLACES_API_KEY?.trim() ||
    process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY?.trim() ||
    null
  );
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const name = searchParams.get("name")?.trim();
  const maxWidthPx = searchParams.get("maxWidthPx")?.trim() || "900";
  const apiKey = getApiKey();

  if (!name || !apiKey) {
    return NextResponse.json({ detail: "Missing photo name or Google Places key." }, { status: 400 });
  }

  const mediaUrl = new URL(`https://places.googleapis.com/v1/${name}/media`);
  mediaUrl.searchParams.set("key", apiKey);
  mediaUrl.searchParams.set("maxWidthPx", maxWidthPx);
  mediaUrl.searchParams.set("skipHttpRedirect", "true");

  const response = await fetch(mediaUrl, { cache: "no-store" });
  if (!response.ok) {
    return NextResponse.json({ detail: "Could not load place photo." }, { status: 502 });
  }

  const payload = (await response.json()) as { photoUri?: string };
  if (!payload.photoUri) {
    return NextResponse.json({ detail: "Photo URI unavailable." }, { status: 502 });
  }

  return NextResponse.redirect(payload.photoUri, 302);
}
