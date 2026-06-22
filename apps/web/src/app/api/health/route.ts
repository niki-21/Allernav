import { NextResponse } from "next/server";

export const runtime = "nodejs";

function hasEnv(name: string): boolean {
  return Boolean(process.env[name]?.trim());
}

export async function GET() {
  const googleServerConfigured = hasEnv("GOOGLE_MAPS_API_KEY") || hasEnv("GOOGLE_PLACES_API_KEY");
  const googleClientConfigured = hasEnv("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY");
  const geminiConfigured = hasEnv("GEMINI_API_KEY");
  const supabaseUrlConfigured = hasEnv("SUPABASE_URL") || hasEnv("NEXT_PUBLIC_SUPABASE_URL");
  const supabasePublicKeyConfigured =
    hasEnv("SUPABASE_ANON_KEY") ||
    hasEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY") ||
    hasEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY");
  const supabaseServiceConfigured = hasEnv("SUPABASE_SERVICE_ROLE_KEY");
  const fastApiConfigured =
    hasEnv("FASTAPI_API_BASE_URL") ||
    hasEnv("NEXT_PUBLIC_FASTAPI_API_BASE_URL") ||
    hasEnv("NEXT_PUBLIC_API_BASE_URL");

  return NextResponse.json({
    ok: googleServerConfigured && googleClientConfigured,
    service: "AllerNav",
    description: "Agentic AI Dining Safety Assistant",
    environment: {
      google_places_server: googleServerConfigured,
      google_maps_client: googleClientConfigured,
      gemini_recommendations: geminiConfigured,
      supabase_public: supabaseUrlConfigured && supabasePublicKeyConfigured,
      supabase_service: supabaseUrlConfigured && supabaseServiceConfigured,
      fastapi_agent_backend: fastApiConfigured,
    },
  });
}
