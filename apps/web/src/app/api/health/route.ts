import { NextResponse } from "next/server";

export const runtime = "nodejs";

function hasEnv(name: string): boolean {
  return Boolean(process.env[name]?.trim());
}

export async function GET() {
  const googleServerConfigured = hasEnv("GOOGLE_MAPS_API_KEY") || hasEnv("GOOGLE_PLACES_API_KEY");
  const googleClientConfigured = hasEnv("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY");
  const openaiConfigured = hasEnv("OPENAI_API_KEY");

  return NextResponse.json({
    ok: googleServerConfigured && googleClientConfigured,
    service: "AllerNav",
    description: "Agentic AI Dining Safety Assistant",
    environment: {
      google_places_server: googleServerConfigured,
      google_maps_client: googleClientConfigured,
      openai_recommendations: openaiConfigured,
    },
  });
}
