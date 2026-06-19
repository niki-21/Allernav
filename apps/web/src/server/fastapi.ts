import type { PlaceMenu } from "../lib/types.ts";

type BackendMenuItem = {
  name?: unknown;
  description?: unknown;
  price?: unknown;
  confirmed_allergens?: unknown;
  inferred_risks?: unknown;
  likely_safe_for?: unknown;
  likely_risky_for?: unknown;
};

type BackendMenuSection = {
  title?: unknown;
  items?: unknown;
};

type BackendPlaceMenu = {
  source_url?: unknown;
  source_fetched_at?: unknown;
  status?: unknown;
  sections?: unknown;
};

export interface RefreshMenuContext {
  restaurantName?: string | null;
  websiteUrl?: string | null;
}

function cleanBaseUrl(value: string | undefined): string | null {
  if (!value?.trim()) {
    return null;
  }
  try {
    const url = new URL(value);
    return url.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

export function getFastApiBaseUrl(): string | null {
  return (
    cleanBaseUrl(process.env.FASTAPI_API_BASE_URL) ??
    cleanBaseUrl(process.env.NEXT_PUBLIC_FASTAPI_API_BASE_URL) ??
    cleanBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL)
  );
}

export function buildFastApiUrl(path: string): string | null {
  const baseUrl = getFastApiBaseUrl();
  if (!baseUrl) {
    return null;
  }
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function allergenArray(value: unknown): PlaceMenu["sections"][number]["items"][number]["likely_risky_for"] {
  return stringArray(value) as PlaceMenu["sections"][number]["items"][number]["likely_risky_for"];
}

export function normalizeBackendMenu(raw: unknown): PlaceMenu | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }

  const menu = raw as BackendPlaceMenu;
  const sections = Array.isArray(menu.sections)
    ? menu.sections
        .map((section): PlaceMenu["sections"][number] | null => {
          if (!section || typeof section !== "object") {
            return null;
          }
          const typedSection = section as BackendMenuSection;
          const title = stringValue(typedSection.title) ?? "Menu";
          const items = Array.isArray(typedSection.items)
            ? typedSection.items
                .map((item): PlaceMenu["sections"][number]["items"][number] | null => {
                  if (!item || typeof item !== "object") {
                    return null;
                  }
                  const typedItem = item as BackendMenuItem;
                  const name = stringValue(typedItem.name);
                  if (!name) {
                    return null;
                  }
                  return {
                    name,
                    description: stringValue(typedItem.description),
                    price: stringValue(typedItem.price),
                    likely_safe_for: allergenArray(typedItem.likely_safe_for),
                    likely_risky_for: [
                      ...allergenArray(typedItem.likely_risky_for),
                      ...allergenArray(typedItem.confirmed_allergens),
                      ...allergenArray(typedItem.inferred_risks),
                    ],
                  };
                })
                .filter((item): item is PlaceMenu["sections"][number]["items"][number] => item !== null)
            : [];
          return items.length > 0 ? { title, items } : null;
        })
        .filter((section): section is PlaceMenu["sections"][number] => section !== null)
    : [];

  if (sections.length === 0) {
    return null;
  }

  return {
    source_url: stringValue(menu.source_url),
    sections,
  };
}

export async function fetchBackendPlaceMenu(placeId: string): Promise<PlaceMenu | null> {
  const url = buildFastApiUrl(`/api/places/${encodeURIComponent(placeId)}/menu`);
  if (!url) {
    return null;
  }

  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return normalizeBackendMenu(await response.json());
  } catch {
    return null;
  }
}
