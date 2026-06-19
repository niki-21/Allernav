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
import { askRestaurant, fetchPlaceDetails, refreshPlaceMenu, searchPlaces } from "@/lib/api";
import { rankPlaces, shouldShowSearchAreaButton } from "@/lib/placeRanking";
import { applyPlaceDetailError, applyPlaceDetailSuccess, seedPlaceDetailsState } from "@/lib/placeState";
import type { AllergyTag, AskRestaurantResponse, LatLng, MenuRefreshJob, PlaceDetailState, PlaceSummary } from "@/lib/types";

const DEFAULT_CENTER: LatLng = { lat: 40.741895, lng: -73.989308 };
const DEFAULT_QUERY = "";

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
  const [locationStatus, setLocationStatus] = useState<"idle" | "locating" | "denied">("idle");
  const [menuRefreshJobs, setMenuRefreshJobs] = useState<Record<string, MenuRefreshJob>>({});
  const [refreshingPlaceId, setRefreshingPlaceId] = useState<string | null>(null);
  const [askResponses, setAskResponses] = useState<Record<string, AskRestaurantResponse>>({});
  const [askingPlaceId, setAskingPlaceId] = useState<string | null>(null);
  const initialized = useRef(false);
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

  const selectedAllergenKey = useMemo(() => selectedAllergens.join("|"), [selectedAllergens]);
  const canSearchArea = useMemo(() => shouldShowSearchAreaButton(searchCenter, mapCenter), [mapCenter, searchCenter]);
  const selectedAllergenSummary = useMemo(
    () =>
      selectedAllergens
        .map((allergen) => allergen.replace("_", " "))
        .map((allergen) => allergen.charAt(0).toUpperCase() + allergen.slice(1))
        .join(", "),
    [selectedAllergens],
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
    if (!profileReady || !places.length) {
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
  }, [hydratePlaces, places, profileReady, selectedAllergens, selectedAllergenKey]);

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

  const selectNativePlace = (place: PlaceSummary) => {
    setPlaces((current) => [place, ...current.filter((item) => item.id !== place.id)]);
    setSelectedPlaceId(place.id);
    setMapFocusPlaceId(place.id);
    setSearchTargetPlaceId(place.id);
    setDetailStates((current) => ({ ...current, [place.id]: { status: "loading" } }));
    const sequence = ++requestSequence.current;
    void hydratePlaces([place], selectedAllergens, sequence);
  };

  const useCurrentLocation = () => {
    if (!navigator.geolocation) {
      setLocationStatus("denied");
      return;
    }

    setLocationStatus("locating");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const center = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        };
        setLocationStatus("idle");
        setSearchCenter(center);
        setMapCenter(center);
        const nextQuery = query.trim() || "restaurants";
        setQuery(nextQuery);
        void runSearch(nextQuery, center, selectedAllergens, { focusTopResult: true });
      },
      () => setLocationStatus("denied"),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  const refreshSelectedMenu = async () => {
    if (!selectedPlaceId) {
      return;
    }
    setRefreshingPlaceId(selectedPlaceId);
    try {
      const job = await refreshPlaceMenu(selectedPlaceId);
      setMenuRefreshJobs((current) => ({ ...current, [selectedPlaceId]: job }));
    } catch (error) {
      setMenuRefreshJobs((current) => ({
        ...current,
        [selectedPlaceId]: {
          id: `failed-${selectedPlaceId}`,
          place_id: selectedPlaceId,
          status: "failed",
          message: error instanceof Error ? error.message : "Menu refresh failed.",
          created_at: new Date().toISOString(),
        },
      }));
    } finally {
      setRefreshingPlaceId(null);
    }
  };

  const askAboutSelectedPlace = async () => {
    if (!selectedPlaceId || !selectedPlace) {
      return;
    }
    setAskingPlaceId(selectedPlaceId);
    try {
      const response = await askRestaurant(selectedPlaceId, selectedPlace.name, selectedAllergens);
      setAskResponses((current) => ({ ...current, [selectedPlaceId]: response }));
    } finally {
      setAskingPlaceId(null);
    }
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
          onNativePlaceSelect={selectNativePlace}
          onMapCenterChange={setMapCenter}
        />
      </div>

      <div className="search-slot">
        <SearchBar
          query={query}
          onQueryChange={setQuery}
          onSearch={(nextQuery) => {
            setQuery(nextQuery);
            void runSearch(nextQuery, mapCenter, selectedAllergens, { focusTopResult: true });
          }}
          searchCenter={mapCenter}
          isSearching={isSearching}
        />
      </div>

      <button type="button" className="location-button" onClick={useCurrentLocation}>
        {locationStatus === "locating" ? "Locating..." : "Use my location"}
      </button>

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
        <section className="glass-panel results-panel map-drawer">
          <details className="drawer-filter" open>
            <summary>
              <span>Allergies</span>
              <strong>{selectedAllergenSummary || "None selected"}</strong>
            </summary>
            <AllergyProfilePicker selectedAllergens={selectedAllergens} onToggle={toggleAllergen} />
          </details>

          {searchError && <p className="panel-error">{searchError}</p>}

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

            {!rankedPlaces.length && !searchError && (
              <p className="empty-results">
                Search for restaurants or use your location to find nearby places.
                {locationStatus === "denied" ? " Location permission was not available." : ""}
              </p>
            )}
          </div>
        </section>

        {selectedPlaceId && (
        <section className="glass-panel details-panel place-sheet">
          <TrustPanel
            place={selectedPlace}
            detailState={selectedPlaceId ? detailStates[selectedPlaceId] : undefined}
            menuRefreshJob={selectedPlaceId ? menuRefreshJobs[selectedPlaceId] : null}
            askResponse={selectedPlaceId ? askResponses[selectedPlaceId] : null}
            isRefreshingMenu={refreshingPlaceId === selectedPlaceId}
            isAskingRestaurant={askingPlaceId === selectedPlaceId}
            onRefreshMenu={refreshSelectedMenu}
            onAskRestaurant={askAboutSelectedPlace}
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
        )}
      </div>
    </main>
  );
}
