import type { CommunityReview, PlatformUserProfile } from "../lib/types.ts";

export function getPlatformViewer(): {
  auth_enabled: boolean;
  viewer: PlatformUserProfile | null;
} {
  return {
    auth_enabled: Boolean(process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID?.trim()),
    viewer: null,
  };
}

export function getCommunityReviews(_placeId: string): CommunityReview[] {
  return [];
}
