import type { GooglePlaceReview } from "./googlePlaces.ts";

const DEFAULT_APIFY_BASE_URL = "https://api.apify.com/v2";
const DEFAULT_APIFY_REVIEWS_ACTOR = "kaix~google-maps-reviews-scraper";

interface CacheEntry {
  expiresAt: number;
  reviews: GooglePlaceReview[];
}

type ApifyReview = {
  id?: unknown;
  reviewId?: unknown;
  review_id?: unknown;
  reviewUrl?: unknown;
  review_url?: unknown;
  url?: unknown;
  text?: unknown;
  reviewText?: unknown;
  review_text?: unknown;
  originalText?: unknown;
  translatedText?: unknown;
  rating?: unknown;
  stars?: unknown;
  reviewRating?: unknown;
  review_rating?: unknown;
  timestamp?: unknown;
  review_timestamp?: unknown;
  publishedAtDate?: unknown;
  publishedAt?: unknown;
  reviewDate?: unknown;
  date?: unknown;
  review_datetime_utc?: unknown;
  authorName?: unknown;
  reviewerName?: unknown;
  userName?: unknown;
  name?: unknown;
  author_title?: unknown;
  author_name?: unknown;
  autor_name?: unknown;
  relativePublishTimeDescription?: unknown;
  relativeDate?: unknown;
  relative_publish_time?: unknown;
};

const reviewCache = new Map<string, CacheEntry>();

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function reviewsLimit(): number {
  const parsed = Number(process.env.APIFY_REVIEWS_LIMIT ?? "100");
  if (!Number.isFinite(parsed)) {
    return 100;
  }
  return Math.max(1, Math.min(500, Math.trunc(parsed)));
}

function cacheTtlMs(): number {
  const parsed = Number(process.env.APIFY_REVIEWS_CACHE_TTL_HOURS ?? "168");
  const hours = Number.isFinite(parsed) ? Math.max(1, parsed) : 168;
  return hours * 60 * 60 * 1000;
}

function requestTimeoutMs(): number {
  const parsed = Number(process.env.APIFY_WEB_TIMEOUT_SECONDS ?? process.env.APIFY_TIMEOUT_SECONDS ?? "8");
  if (!Number.isFinite(parsed)) {
    return 8000;
  }
  return Math.max(1000, Math.min(12_000, Math.trunc(parsed * 1000)));
}

function firstString(review: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = stringValue(review[key]);
    if (value) {
      return value;
    }
  }
  return null;
}

function firstValue(review: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    const value = review[key];
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return null;
}

function parsePublishTime(review: ApifyReview): string | null {
  const timestamp = numberValue(firstValue(review as Record<string, unknown>, ["timestamp", "review_timestamp"]));
  if (timestamp !== null) {
    const seconds = timestamp > 10_000_000_000 ? timestamp / 1000 : timestamp;
    return new Date(seconds * 1000).toISOString();
  }

  const rawDate = firstString(review as Record<string, unknown>, [
    "publishedAtDate",
    "publishedAt",
    "reviewDate",
    "date",
    "review_datetime_utc",
  ]);
  if (!rawDate) {
    return null;
  }
  const parsed = Date.parse(rawDate);
  return Number.isNaN(parsed) ? rawDate : new Date(parsed).toISOString();
}

function flattenReviews(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) {
    return payload.flatMap((item) => flattenReviews(item));
  }
  if (payload && typeof payload === "object") {
    const typedPayload = payload as Record<string, unknown>;
    if (
      firstString(typedPayload, ["text", "reviewText", "review_text", "originalText", "translatedText"])
    ) {
      return [typedPayload];
    }
    const nestedKeys = ["reviews", "reviewsData", "reviews_data", "userReviews", "data", "items"];
    return nestedKeys.flatMap((key) => {
      const value = typedPayload[key];
      return Array.isArray(value) ? flattenReviews(value) : [];
    });
  }
  return [];
}

function googleMapsPlaceUrl(placeId: string): string {
  return `https://www.google.com/maps/place/?q=place_id:${encodeURIComponent(placeId)}`;
}

function actorPath(): string {
  const actor = process.env.APIFY_REVIEWS_ACTOR?.trim() || DEFAULT_APIFY_REVIEWS_ACTOR;
  return encodeURIComponent(actor.replace("/", "~"));
}

function buildApifyInput(placeId: string): Record<string, unknown> {
  const input: Record<string, unknown> = {
    urls: [googleMapsPlaceUrl(placeId)],
    maxReviews: reviewsLimit(),
    sort: process.env.APIFY_REVIEWS_SORT?.trim() || "newest",
    language: process.env.APIFY_LANGUAGE?.trim() || "en",
    region: process.env.APIFY_REGION?.trim() || "US",
    proxyConfiguration: { useApifyProxy: true },
  };
  const searchQuery = process.env.APIFY_REVIEWS_SEARCH_QUERY?.trim();
  if (searchQuery) {
    input.searchQuery = searchQuery;
  }
  const newerThan = process.env.APIFY_REVIEWS_NEWER_THAN?.trim();
  if (newerThan) {
    input.reviewsNewerThan = newerThan;
  }
  const olderThan = process.env.APIFY_REVIEWS_OLDER_THAN?.trim();
  if (olderThan) {
    input.reviewsOlderThan = olderThan;
  }
  return input;
}

export function normalizeApifyReviews(payload: unknown): GooglePlaceReview[] {
  const reviews: GooglePlaceReview[] = [];
  const seen = new Set<string>();

  for (const rawReview of flattenReviews(payload)) {
    const text = firstString(rawReview, ["text", "reviewText", "review_text", "originalText", "translatedText"]);
    if (!text) {
      continue;
    }
    const reviewId =
      firstString(rawReview, ["reviewId", "review_id", "id", "reviewUrl", "review_url", "url"]) ??
      `apify-${reviews.length}`;
    if (seen.has(reviewId)) {
      continue;
    }
    seen.add(reviewId);
    reviews.push({
      review_id: reviewId,
      author_name: firstString(rawReview, [
        "authorName",
        "reviewerName",
        "userName",
        "name",
        "author_title",
        "autor_name",
        "author_name",
      ]),
      rating: numberValue(firstValue(rawReview, ["rating", "stars", "reviewRating", "review_rating"])),
      text,
      publish_time: parsePublishTime(rawReview as ApifyReview),
      relative_publish_time: firstString(rawReview, [
        "relativePublishTimeDescription",
        "relativeDate",
        "relative_publish_time",
      ]),
    });
  }

  return reviews;
}

export async function fetchApifyReviews(placeId: string): Promise<GooglePlaceReview[]> {
  const token = process.env.APIFY_TOKEN?.trim();
  if (!token) {
    return [];
  }

  const cached = reviewCache.get(placeId);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.reviews;
  }

  const baseUrl = process.env.APIFY_API_BASE_URL?.trim() || DEFAULT_APIFY_BASE_URL;
  const url = new URL(`${baseUrl.replace(/\/$/, "")}/actors/${actorPath()}/run-sync-get-dataset-items`);
  url.searchParams.set("token", token);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), requestTimeoutMs());
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildApifyInput(placeId)),
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      return [];
    }
    const reviews = normalizeApifyReviews(await response.json());
    reviewCache.set(placeId, {
      expiresAt: Date.now() + cacheTtlMs(),
      reviews,
    });
    return reviews;
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}
