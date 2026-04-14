"use client";

import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";

import AllergyProfilePicker from "@/components/AllergyProfilePicker";
import Map from "@/components/Map";
import PlaceCard from "@/components/PlaceCard";
import SearchBar from "@/components/searchBar";
import TrustPanel from "@/components/TrustPanel";
import { ALLERGY_PROFILE_STORAGE_KEY, DEFAULT_ALLERGENS } from "@/lib/allergens";
import { fetchPlaceDetails, searchPlaces } from "@/lib/api";
import { applyPlaceDetailError, applyPlaceDetailSuccess, seedPlaceDetailsState } from "@/lib/placeState";
import type { AllergyTag, LatLng, PlaceDetailState, PlaceSummary } from "@/lib/types";

const DEFAULT_CENTER: LatLng = { lat: 40.741895, lng: -73.989308 };
const DEFAULT_QUERY = "restaurants";

function distanceBetween(a: LatLng, b: LatLng): number {
  const latDiff = a.lat - b.lat;
  const lngDiff = a.lng - b.lng;
  return Math.sqrt(latDiff * latDiff + lngDiff * lngDiff);
}

export default function Home() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [places, setPlaces] = useState<PlaceSummary[]>([]);
  const [detailStates, setDetailStates] = useState<Record<string, PlaceDetailState>>({});
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null);
  const [selectedAllergens, setSelectedAllergens] = useState<AllergyTag[]>(DEFAULT_ALLERGENS);
  const [searchCenter, setSearchCenter] = useState<LatLng>(DEFAULT_CENTER);
  const [mapCenter, setMapCenter] = useState<LatLng>(DEFAULT_CENTER);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
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
    } finally {
      initialized.current = true;
      setProfileReady(true);
    }
  }, []);

  useEffect(() => {
    if (!initialized.current) {
      return;
    }
    window.localStorage.setItem(ALLERGY_PROFILE_STORAGE_KEY, JSON.stringify(selectedAllergens));
  }, [selectedAllergens]);

  const selectedPlace = useMemo(
    () => places.find((place) => place.id === selectedPlaceId) ?? null,
    [places, selectedPlaceId],
  );

  const hydratedCount = useMemo(
    () => Object.values(detailStates).filter((item) => item.status === "ready").length,
    [detailStates],
  );
  const selectedAllergenKey = useMemo(() => selectedAllergens.join("|"), [selectedAllergens]);

  const canSearchArea = useMemo(
    () => distanceBetween(searchCenter, mapCenter) > 0.01,
    [mapCenter, searchCenter],
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

  const runSearch = useCallback(async (nextQuery: string, nextCenter: LatLng, allergens: AllergyTag[]) => {
    const sequence = ++requestSequence.current;
    setIsSearching(true);
    setSearchError(null);

    try {
      const response = await searchPlaces(nextQuery, nextCenter, allergens);
      if (sequence !== requestSequence.current) {
        return;
      }

      startTransition(() => {
        setPlaces(response.places);
        setSelectedPlaceId(response.places[0]?.id ?? null);
        setSearchCenter(response.center);
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
  }, [hydratePlaces]);

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

  return (
    <main className="app-shell">
      <div className="map-layer">
        <Map
          places={places}
          details={detailStates}
          selectedPlaceId={selectedPlaceId}
          searchCenter={searchCenter}
          onPlaceSelect={setSelectedPlaceId}
          onMapCenterChange={setMapCenter}
        />
      </div>

      <div className="search-slot">
        <SearchBar
          query={query}
          onQueryChange={setQuery}
          onSearch={(nextQuery) => {
            setQuery(nextQuery);
            void runSearch(nextQuery, mapCenter, selectedAllergens);
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
              <p className="panel-eyebrow">Allernav</p>
              <h1>Find places that fit your allergy profile.</h1>
            </div>
            <span className="panel-stat">
              {hydratedCount}/{places.length} trust views ready
            </span>
          </div>

          <div className="panel-subhead">
            <p>Pick one or more allergens and compare places by review-backed safety signals.</p>
            <AllergyProfilePicker selectedAllergens={selectedAllergens} onToggle={toggleAllergen} />
          </div>

          {searchError && <p className="panel-error">{searchError}</p>}

          <div className="results-scroll">
            {places.map((place) => (
              <PlaceCard
                key={place.id}
                place={place}
                detailState={detailStates[place.id]}
                selected={place.id === selectedPlaceId}
                onSelect={() => setSelectedPlaceId(place.id)}
              />
            ))}

            {!places.length && !searchError && <p className="empty-results">No places found for this search yet.</p>}
          </div>
        </section>

        <section className="glass-panel details-panel">
          <TrustPanel
            place={selectedPlace}
            detailState={selectedPlaceId ? detailStates[selectedPlaceId] : undefined}
            selectedAllergens={selectedAllergens}
            onRetry={() => {
              if (!selectedPlaceId) {
                return;
              }
              setDetailStates((current) => ({ ...current, [selectedPlaceId]: { status: "loading" } }));
              void hydratePlaces(
                places.filter((place) => place.id === selectedPlaceId),
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
