import type { AllergyTag, CommunityReview, PlatformUserProfile } from "../lib/types.ts";

const memoryReviews = new Map<string, CommunityReview[]>();

function supabaseRestConfig(): { url: string; serviceRoleKey: string } | null {
  const rawUrl = process.env.SUPABASE_URL?.trim() || process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!rawUrl || !key) {
    return null;
  }
  const url = rawUrl.endsWith("/rest/v1") ? rawUrl.slice(0, -"/rest/v1".length) : rawUrl.replace(/\/$/, "");
  return { url, serviceRoleKey: key };
}

async function supabaseRequest(path: string, init: RequestInit): Promise<unknown | null> {
  const config = supabaseRestConfig();
  if (!config) {
    return null;
  }
  const response = await fetch(`${config.url}${path}`, {
    ...init,
    headers: {
      apikey: config.serviceRoleKey,
      Authorization: `Bearer ${config.serviceRoleKey}`,
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    return null;
  }
  const text = await response.text();
  return text ? JSON.parse(text) : {};
}

function normalizeCommunityReview(raw: unknown): CommunityReview | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const value = raw as Record<string, unknown>;
  const id = typeof value.id === "string" ? value.id : null;
  const authorName = typeof value.author_name === "string" ? value.author_name : null;
  const body = typeof value.body === "string" ? value.body : null;
  const createdAt = typeof value.created_at === "string" ? value.created_at : new Date().toISOString();
  if (!id || !authorName || !body) {
    return null;
  }
  const verificationStatus =
    value.verification_status === "verified_visit" || value.verification_status === "signed_in"
      ? value.verification_status
      : "unverified";
  return {
    id,
    author_name: authorName,
    body,
    rating: typeof value.rating === "number" ? value.rating : null,
    allergens: Array.isArray(value.allergens) ? (value.allergens.filter((item) => typeof item === "string") as AllergyTag[]) : [],
    helpful_count: typeof value.helpful_count === "number" ? value.helpful_count : 0,
    points_awarded: typeof value.points_awarded === "number" ? value.points_awarded : 0,
    created_at: createdAt,
    verification_status: verificationStatus,
  };
}

function fallbackReviews(placeId: string): CommunityReview[] {
  return memoryReviews.get(placeId) ?? [];
}

export function getPlatformViewer(): {
  auth_enabled: boolean;
  viewer: PlatformUserProfile | null;
} {
  return {
    auth_enabled: Boolean(process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID?.trim()),
    viewer: null,
  };
}

export async function getCommunityReviews(placeId: string): Promise<CommunityReview[]> {
  const query = new URLSearchParams({
    place_id: `eq.${placeId}`,
    select: "id,author_name,body,rating,allergens,helpful_count,points_awarded,created_at,verification_status",
    order: "created_at.desc",
    limit: "20",
  });
  const payload = await supabaseRequest(`/rest/v1/community_reviews?${query.toString()}`, {
    method: "GET",
  });
  if (Array.isArray(payload)) {
    return payload.map(normalizeCommunityReview).filter((review): review is CommunityReview => review !== null);
  }
  return fallbackReviews(placeId);
}

export async function saveCommunityReview(
  placeId: string,
  payload: {
    author_name?: unknown;
    body?: unknown;
    rating?: unknown;
    allergens?: unknown;
    reviewer_id?: unknown;
  },
): Promise<{ review: CommunityReview; points_awarded: number; points_requires_login: boolean; persisted: boolean }> {
  const authorName = typeof payload.author_name === "string" && payload.author_name.trim()
    ? payload.author_name.trim().slice(0, 80)
    : "AllerNav diner";
  const body = typeof payload.body === "string" ? payload.body.trim().slice(0, 1200) : "";
  if (body.length < 12) {
    throw new Error("Add a little more detail about the allergy experience.");
  }
  const rating = typeof payload.rating === "number" && Number.isFinite(payload.rating)
    ? Math.max(1, Math.min(5, Math.trunc(payload.rating)))
    : null;
  const allergens = Array.isArray(payload.allergens)
    ? (payload.allergens.filter((item): item is AllergyTag => typeof item === "string") as AllergyTag[])
    : [];
  const reviewerId = typeof payload.reviewer_id === "string" && payload.reviewer_id.trim()
    ? payload.reviewer_id.trim()
    : null;
  const pointsAwarded = reviewerId ? 10 + Math.min(5, allergens.length) : 0;
  const createdAt = new Date().toISOString();
  const review: CommunityReview = {
    id: crypto.randomUUID(),
    author_name: authorName,
    body,
    rating,
    allergens,
    helpful_count: 0,
    points_awarded: pointsAwarded,
    created_at: createdAt,
    verification_status: reviewerId ? "signed_in" : "unverified",
  };
  const row = {
    ...review,
    place_id: placeId,
    reviewer_id: reviewerId,
  };
  const saved = await supabaseRequest("/rest/v1/community_reviews", {
    method: "POST",
    headers: { Prefer: "return=representation" },
    body: JSON.stringify([row]),
  });
  if (Array.isArray(saved)) {
    const savedReview = normalizeCommunityReview(saved[0]) ?? review;
    return {
      review: savedReview,
      points_awarded: savedReview.points_awarded ?? pointsAwarded,
      points_requires_login: !reviewerId,
      persisted: true,
    };
  }
  memoryReviews.set(placeId, [review, ...fallbackReviews(placeId)]);
  return {
    review,
    points_awarded: pointsAwarded,
    points_requires_login: !reviewerId,
    persisted: false,
  };
}
