"use client";

import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";

import AllergyProfilePicker from "@/components/AllergyProfilePicker";
import Map from "@/components/Map";
import PlaceCard from "@/components/PlaceCard";
import SearchBar from "@/components/searchBar";
import TrustPanel from "@/components/TrustPanel";
import {
  ALLERGY_PROFILE_STORAGE_KEY,
  DEFAULT_ALLERGENS,
} from "@/lib/allergens";
import { fetchPlaceDetails, searchPlaces } from "@/lib/api";
import { rankPlaces, shouldShowSearchAreaButton } from "@/lib/placeRanking";
import { applyPlaceDetailError, applyPlaceDetailSuccess, seedPlaceDetailsState } from "@/lib/placeState";
import type { AllergyTag, LatLng, PlaceDetailState, PlaceSummary } from "@/lib/types";

const DEFAULT_CENTER: LatLng = { lat: 38.9869, lng: -76.9426 };
const DEFAULT_QUERY = "restaurants near University of Maryland";

const QUICK_SEARCHES: Array<{
  label: string;
  query: string;
}> = [
  { label: "Quick lunch", query: "quick lunch near UMD" },
  { label: "Study break cafe", query: "coffee and cafe near UMD" },
  { label: "Sit-down dinner", query: "sit down dinner near College Park" },
  { label: "Late-night food", query: "late night food near College Park" },
];

export default function Home() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [places, setPlaces] = useState<PlaceSummary[]>([]);
  const [detailStates, setDetailStates] = useState<Record<string, PlaceDetailState>>({});
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null);
  const [mapFocusPlaceId, setMapFocusPlaceId] = useState<string | null>(null);
  const [selectedAllergens, setSelectedAllergens] = useState<AllergyTag[]>(DEFAULT_ALLERGENS);
  const [searchCenter, setSearchCenter] = useState<LatLng>(DEFAULT_CENTER);
  const [mapCenter, setMapCenter] = useState<LatLng>(DEFAULT_CENTER);
  const [searchTargetPlaceId, setSearchTargetPlaceId] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [activeQuickStartLabel, setActiveQuickStartLabel] = useState<string | null>(null);
  const initialized = useRef(false);
  const bootstrappedSearch = useRef(false);
  const hydratedAllergenKey = useRef<string | null>(null);
  const requestSequence = useRef(0);
  const [profileReady, setProfileReady] = useState(false);

  useEffect(() => {
    const raw = window.localStorage.getItem(ALLERGY_PROFILE_STORAGE_KEY);
    if (!raw) {
      initialized.current = true;
      setProfileReady(true);
      return;
    }

    try {
      const parsed = JSON.parse(raw) as AllergyTag[];
      if (Array.isArray(parsed) && parsed.length > 0) {
        setSelectedAllergens(parsed);
      }
    } catch {
      window.localStorage.removeItem(ALLERGY_PROFILE_STORAGE_KEY);
    }

    initialized.current = true;
    setProfileReady(true);
  }, []);

  useEffect(() => {
    if (!initialized.current) {
      return;
    }
    window.localStorage.setItem(ALLERGY_PROFILE_STORAGE_KEY, JSON.stringify(selectedAllergens));
  }, [selectedAllergens]);

  const rankedPlaces = useMemo(() => rankPlaces(places, detailStates), [detailStates, places]);

  const selectedPlace = useMemo(
    () => rankedPlaces.find((place) => place.id === selectedPlaceId) ?? null,
    [rankedPlaces, selectedPlaceId],
  );

  const hydratedCount = useMemo(
    () => Object.values(detailStates).filter((item) => item.status === "ready").length,
    [detailStates],
  );
  const selectedAllergenKey = useMemo(() => selectedAllergens.join("|"), [selectedAllergens]);
  const canSearchArea = useMemo(() => shouldShowSearchAreaButton(searchCenter, mapCenter), [mapCenter, searchCenter]);
  const selectedAllergenSummary = useMemo(
    () => `${selectedAllergens.length} allergen${selectedAllergens.length === 1 ? "" : "s"} selected`,
    [selectedAllergens.length],
  );

  const hydratePlaces = useCallback(async (nextPlaces: PlaceSummary[], allergens: AllergyTag[], sequence: number) => {
    await Promise.allSettled(
      nextPlaces.map(async (place) => {
        try {
          const details = await fetchPlaceDetails(place.id, allergens);
          if (sequence !== requestSequence.current) {
            return;
          }
          setDetailStates((current) => applyPlaceDetailSuccess(current, place.id, details));
        } catch (error) {
          if (sequence !== requestSequence.current) {
            return;
          }
          setDetailStates((current) =>
            applyPlaceDetailError(
              current,
              place.id,
              error instanceof Error ? error.message : "We could not score this place yet.",
            ),
          );
        }
      }),
    );
  }, []);

  const runSearch = useCallback(
    async (
      nextQuery: string,
      nextCenter: LatLng,
      allergens: AllergyTag[],
      options: {
        focusTopResult?: boolean;
      } = {},
    ) => {
      const sequence = ++requestSequence.current;
      setIsSearching(true);
      setSearchError(null);

      try {
        const response = await searchPlaces(nextQuery, nextCenter, allergens);
        if (sequence !== requestSequence.current) {
          return;
        }

        const firstPlace = response.places[0] ?? null;
        const focusedCenter = options.focusTopResult && firstPlace ? firstPlace.location : response.center;

        startTransition(() => {
          setPlaces(response.places);
          setSelectedPlaceId(firstPlace?.id ?? null);
          setMapFocusPlaceId(options.focusTopResult ? firstPlace?.id ?? null : null);
          setSearchTargetPlaceId(options.focusTopResult ? firstPlace?.id ?? null : null);
          setSearchCenter(focusedCenter);
          setMapCenter(focusedCenter);
          setDetailStates(seedPlaceDetailsState(response.places.map((place) => place.id)));
        });

        void hydratePlaces(response.places, allergens, sequence);
      } catch (error) {
        if (sequence !== requestSequence.current) {
          return;
        }
        setSearchError(error instanceof Error ? error.message : "Search failed.");
      } finally {
        if (sequence === requestSequence.current) {
          setIsSearching(false);
        }
      }
    },
    [hydratePlaces],
  );

  useEffect(() => {
    if (!profileReady || bootstrappedSearch.current) {
      return;
    }
    bootstrappedSearch.current = true;
    void runSearch(DEFAULT_QUERY, DEFAULT_CENTER, selectedAllergens);
  }, [profileReady, runSearch, selectedAllergens]);

  useEffect(() => {
    if (!bootstrappedSearch.current || !places.length) {
      return;
    }
    if (hydratedAllergenKey.current === null) {
      hydratedAllergenKey.current = selectedAllergenKey;
      return;
    }
    if (hydratedAllergenKey.current === selectedAllergenKey) {
      return;
    }
    hydratedAllergenKey.current = selectedAllergenKey;

    const sequence = ++requestSequence.current;
    setDetailStates(seedPlaceDetailsState(places.map((place) => place.id)));
    void hydratePlaces(places, selectedAllergens, sequence);
  }, [hydratePlaces, places, selectedAllergens, selectedAllergenKey]);

  const toggleAllergen = (allergen: AllergyTag) => {
    setSelectedAllergens((current) => {
      if (current.includes(allergen)) {
        return current.length === 1 ? current : current.filter((value) => value !== allergen);
      }
      return [...current, allergen];
    });
  };

  const selectPlace = (placeId: string | null) => {
    setSelectedPlaceId(placeId);
    setMapFocusPlaceId(placeId);
  };

  const runPresetSearch = (preset: { query: string; label: string }) => {
    setActiveQuickStartLabel(preset.label);
    setQuery(preset.query);
    void runSearch(preset.query, mapCenter, selectedAllergens, { focusTopResult: true });
  };

  return (
    <main className="app-shell">
      <div className="map-layer">
        <Map
          places={places}
          details={detailStates}
          selectedPlaceId={selectedPlaceId}
          mapFocusPlaceId={mapFocusPlaceId}
          searchCenter={searchCenter}
          searchTargetPlaceId={searchTargetPlaceId}
          onPlaceSelect={selectPlace}
          onMapCenterChange={setMapCenter}
        />
      </div>

      <div className="search-slot">
        <SearchBar
          query={query}
          onQueryChange={setQuery}
          onSearch={(nextQuery) => {
            setActiveQuickStartLabel(null);
            setQuery(nextQuery);
            void runSearch(nextQuery, mapCenter, selectedAllergens, { focusTopResult: true });
          }}
          searchCenter={mapCenter}
          isSearching={isSearching}
        />
      </div>

      {canSearchArea && (
        <button
          type="button"
          className="area-button"
          onClick={() => void runSearch(query, mapCenter, selectedAllergens)}
        >
          Search this area
        </button>
      )}

      <div className="side-panels">
        <section className="glass-panel results-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">AllerNav Campus</p>
              <h1>AI support for safer dining decisions around campus.</h1>
            </div>
            <span className="panel-stat">{hydratedCount}/{rankedPlaces.length} AI briefs ready</span>
          </div>

          <div className="hero-copy">
            <p>
              Pick your allergens, use a quick start, and compare nearby spots with AI scoring that reacts to your
              selected profile.
            </p>
          </div>

          <div className="profile-card">
            <div className="profile-card-header">
              <div>
                <p className="detail-section-title">Allergy filters</p>
                <h2 className="profile-card-title">{selectedAllergenSummary}</h2>
              </div>
              <span className="detail-pill">No account required</span>
            </div>

            <div className="profile-section">
              <p className="profile-section-label">Allergens</p>
              <AllergyProfilePicker selectedAllergens={selectedAllergens} onToggle={toggleAllergen} />
            </div>
          </div>

          <div className="panel-subhead quick-search-panel">
            <div>
              <p className="detail-section-title">Campus quick starts</p>
              <p>Jump into common campus scenarios and compare how each place scores for your selected allergens.</p>
            </div>
            <div className="quick-search-row">
              {QUICK_SEARCHES.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="quick-search-chip"
                  onClick={() => runPresetSearch(preset)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          {searchError && <p className="panel-error">{searchError}</p>}

          <div className="results-section-header">
            <div>
              <p className="detail-section-title">Best current matches</p>
              <p>Ranked for your allergens using reviews first, then menu snapshots when reviews are thin.</p>
            </div>
            <span className="detail-pill">{activeQuickStartLabel ?? "Campus scan"}</span>
          </div>

          <div className="results-scroll">
            {rankedPlaces.map((place) => (
              <div key={place.id} className="place-card-shell">
                <PlaceCard
                  place={place}
                  detailState={detailStates[place.id]}
                  selected={place.id === selectedPlaceId}
                  onSelect={() => selectPlace(place.id)}
                />
              </div>
            ))}

            {!rankedPlaces.length && !searchError && <p className="empty-results">No places found for this search yet.</p>}
          </div>
        </section>

        <section className="glass-panel details-panel">
          <TrustPanel
            place={selectedPlace}
            detailState={selectedPlaceId ? detailStates[selectedPlaceId] : undefined}
            onRetry={() => {
              if (!selectedPlaceId) {
                return;
              }
              setDetailStates((current) => ({ ...current, [selectedPlaceId]: { status: "loading" } }));
              void hydratePlaces(
                rankedPlaces.filter((place) => place.id === selectedPlaceId),
                selectedAllergens,
                requestSequence.current,
              );
            }}
          />
        </section>
      </div>
    </main>
  );
}
