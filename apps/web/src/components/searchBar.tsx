"use client";

import { useDeferredValue, useEffect, useState } from "react";

import type { LatLng } from "@/lib/types";

interface Suggestion {
  text: string;
}

interface SearchBarProps {
  query: string;
  onQueryChange: (value: string) => void;
  onSearch: (query: string) => void;
  searchCenter: LatLng;
  isSearching: boolean;
}

const GENERIC_SEARCH_TERMS = ["near", "restaurant", "restaurants", "food", "dining", "lunch", "dinner", "cafe", "coffee"];

function shouldFetchSuggestions(query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (normalized.length < 3) {
    return false;
  }

  const wordCount = normalized.split(/\s+/).filter(Boolean).length;
  if (wordCount > 3) {
    return false;
  }

  return !GENERIC_SEARCH_TERMS.some((term) => normalized.includes(term));
}

export default function SearchBar({
  query,
  onQueryChange,
  onSearch,
  searchCenter,
  isSearching,
}: SearchBarProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    const trimmed = deferredQuery.trim();
    if (!apiKey || !shouldFetchSuggestions(trimmed)) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch("https://places.googleapis.com/v1/places:autocomplete", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": apiKey,
            "X-Goog-FieldMask": "suggestions.placePrediction.text",
          },
          body: JSON.stringify({
            input: trimmed,
            includedPrimaryTypes: ["restaurant"],
            includedRegionCodes: ["us"],
            locationBias: {
              circle: {
                center: { latitude: searchCenter.lat, longitude: searchCenter.lng },
                radius: 10000.0,
              },
            },
          }),
        });

        if (!response.ok) {
          setSuggestions([]);
          setShowSuggestions(false);
          return;
        }

        const data = (await response.json()) as {
          suggestions?: Array<{ placePrediction?: { text?: { text?: string } } }>;
        };
        const nextSuggestions =
          data.suggestions
            ?.map((item) => item.placePrediction?.text?.text?.trim())
            .filter((item): item is string => Boolean(item)) ?? [];

        setSuggestions(nextSuggestions.map((text) => ({ text })));
        setShowSuggestions(nextSuggestions.length > 0);
      } catch {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    }, 280);

    return () => window.clearTimeout(timer);
  }, [deferredQuery, searchCenter.lat, searchCenter.lng]);

  const submitSearch = (value: string) => {
    const nextQuery = value.trim();
    if (!nextQuery) {
      return;
    }
    setShowSuggestions(false);
    onSearch(nextQuery);
  };

  return (
    <div className="search-shell">
      <div className="search-bar">
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          onFocus={() => setShowSuggestions(suggestions.length > 0)}
          onBlur={() => {
            window.setTimeout(() => setShowSuggestions(false), 120);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              submitSearch(query);
            }
            if (event.key === "Escape") {
              setShowSuggestions(false);
            }
          }}
          className="search-input"
          placeholder="Search College Park restaurants, cafes, dining halls, or takeout"
        />
        <button type="button" className="search-submit" onClick={() => submitSearch(query)}>
          {isSearching ? "Searching..." : "Search"}
        </button>
      </div>

      <p className="search-caption">Try “late night food”, “sushi”, “coffee”, or a specific restaurant near campus.</p>

      {showSuggestions && suggestions.length > 0 && (
        <div className="autocomplete-panel">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion.text}
              type="button"
              className="autocomplete-item"
              onClick={() => {
                onQueryChange(suggestion.text);
                submitSearch(suggestion.text);
              }}
            >
              {suggestion.text}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
