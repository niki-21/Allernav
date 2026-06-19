import { NextResponse } from "next/server";

export const runtime = "nodejs";

const savedPlaces = new Set<string>();

function payload() {
  return {
    authenticated: false,
    saved_places: Array.from(savedPlaces),
  };
}

export async function POST(_request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  savedPlaces.add(placeId);
  return NextResponse.json(payload());
}

export async function DELETE(_request: Request, context: { params: Promise<{ placeId: string }> }) {
  const { placeId } = await context.params;
  savedPlaces.delete(placeId);
  return NextResponse.json(payload());
}
