import { NextResponse } from "next/server";

import { DEFAULT_ALLERGENS } from "@/lib/allergens";

export const runtime = "nodejs";

let profile = {
  authenticated: false,
  profile: {
    allergens: DEFAULT_ALLERGENS,
    sensitivity: "careful",
    prep_preference: "verify",
  },
  saved_places: [] as string[],
};

export async function GET() {
  return NextResponse.json(profile);
}

export async function PUT(request: Request) {
  const nextProfile = await request.json();
  profile = {
    ...profile,
    profile: {
      ...profile.profile,
      ...nextProfile,
    },
  };
  return NextResponse.json(profile);
}
