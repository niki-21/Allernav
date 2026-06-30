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
import {
  analyzeRestaurant,
  askNearbyPlaces,
  askRestaurant,
  fetchMenuRefreshJob,
  fetchPlaceDetails,
  fetchPlaceMenu,
  menuScanErrorMessage,
  nearbyRagErrorMessage,
  refreshPlaceMenu,
  searchPlaces,
} from "@/lib/api";
import { rankPlaces, shouldShowSearchAreaButton } from "@/lib/placeRanking";
import { applyPlaceDetailError, applyPlaceDetailSuccess, seedPlaceDetailsState } from "@/lib/placeState";
import type {
  AllergyTag,
  AskRestaurantResponse,
  LatLng,
  NearbySuggestionResponse,
  MenuRefreshJob,
  PlaceDetailState,
  PlaceMenu,
  PlaceSummary,
} from "@/lib/types";

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
  const [askResponses, setAskResponses] = useState<Record<string, AskRestaurantResponse>>({});
  const [askingPlaceId, setAskingPlaceId] = useState<string | null>(null);
  const [nearbyQuestion, setNearbyQuestion] = useState("Suggest nearby places to evaluate for my allergies");
  const [nearbyAnswer, setNearbyAnswer] = useState<NearbySuggestionResponse | null>(null);
  const [nearbyAskState, setNearbyAskState] = useState<"idle" | "loading" | "error">("idle");
  const [nearbyAskError, setNearbyAskError] = useState<string | null>(null);
  const [menuLoadingPlaceIds, setMenuLoadingPlaceIds] = useState<Set<string>>(() => new Set());
  const [menuRefreshJobs, setMenuRefreshJobs] = useState<Record<string, MenuRefreshJob>>({});
  const initialized = useRef(false);
  const hydratedAllergenKey = useRef<string | null>(null);
  const requestSequence = useRef(0);
  const menuRefreshAttempts = useRef<Set<string>>(new Set());
  const agentAnalysisAttempts = useRef<Set<string>>(new Set());
  const [profileReady, setProfileReady] = useState(false);

  const runMenuRefresh = useCallback(
    async (details: Extract<PlaceDetailState, { status: "ready" }>["data"]) => {
      const startedAt = new Date().toISOString();
      setMenuLoadingPlaceIds((current) => new Set(current).add(details.id));
      setMenuRefreshJobs((current) => ({
        ...current,
        [details.id]: {
          id: `running-${details.id}`,
          place_id: details.id,
          status: "running",
          message: "Menu scan is still running.",
          item_count: 0,
          trace: [
            {
              id: "request",
              label: "Start menu discovery",
              status: "running",
              detail: "Menu scan started.",
            },
          ],
          created_at: startedAt,
        },
      }));

      try {
        let job = await refreshPlaceMenu(details.id, {
          placeName: details.name,
          websiteUrl: details.website_uri,
        });
        setMenuRefreshJobs((current) => ({ ...current, [details.id]: job }));
        const terminalStatuses = new Set(["complete", "failed", "needs_background_refresh"]);
        for (let attempt = 0; attempt < 90 && !terminalStatuses.has(job.status); attempt += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 2_000));
          job = await fetchMenuRefreshJob(job.id);
          setMenuRefreshJobs((current) => ({ ...current, [details.id]: job }));
        }
        if (!terminalStatuses.has(job.status)) {
          job = {
            ...job,
            status: "needs_background_refresh",
            message: "Menu scan is still running.",
          };
          setMenuRefreshJobs((current) => ({ ...current, [details.id]: job }));
        }
        let refreshedMenu: PlaceMenu | null = null;
        for (let attempt = 0; attempt < 6; attempt += 1) {
          refreshedMenu = await fetchPlaceMenu(details.id, selectedAllergens);
          if (refreshedMenu || job.status !== "complete") {
            break;
          }
          await new Promise((resolve) => window.setTimeout(resolve, 2_000));
        }
        if (refreshedMenu) {
          setDetailStates((current) => {
            const currentState = current[details.id];
            if (!currentState || currentState.status !== "ready") {
              return current;
            }
            return {
              ...current,
              [details.id]: {
                status: "ready",
                data: { ...currentState.data, menu: refreshedMenu },
              },
            };
          });
          void fetchPlaceDetails(details.id, selectedAllergens)
            .then((refreshedDetails) => {
              setDetailStates((current) => {
                const currentState = current[details.id];
                if (!currentState || currentState.status !== "ready") {
                  return current;
                }
                return applyPlaceDetailSuccess(current, details.id, {
                  ...refreshedDetails,
                  agent_recommendation:
                    currentState.data.agent_recommendation ?? refreshedDetails.agent_recommendation,
                });
              });
            })
            .catch(() => undefined);
        }
        if (job.status === "complete" && ["pending", "running"].includes(job.indexing_status ?? "")) {
          void (async () => {
            for (let attempt = 0; attempt < 30; attempt += 1) {
              await new Promise((resolve) => window.setTimeout(resolve, 2_000));
              try {
                const indexJob = await fetchMenuRefreshJob(job.id);
                setMenuRefreshJobs((current) => ({ ...current, [details.id]: indexJob }));
                if (!["pending", "running"].includes(indexJob.indexing_status ?? "")) {
                  break;
                }
              } catch {
                break;
              }
            }
          })();
        }
      } catch (error) {
        const completedAt = new Date().toISOString();
        const message = menuScanErrorMessage(error);
        setMenuRefreshJobs((current) => ({
          ...current,
          [details.id]: {
            id: `failed-${details.id}`,
            place_id: details.id,
            status: "failed",
            message,
            item_count: 0,
            trace: [
              {
                id: "request",
                label: "Run menu discovery",
                status: "failed",
                detail: message,
              },
            ],
            created_at: startedAt,
            completed_at: completedAt,
          },
        }));
      } finally {
        setMenuLoadingPlaceIds((current) => {
          const next = new Set(current);
          next.delete(details.id);
          return next;
        });
      }
    },
    [selectedAllergens],
  );

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

  useEffect(() => {
    if (!selectedPlaceId) {
      return;
    }

    const detailState = detailStates[selectedPlaceId];
    if (!detailState || detailState.status !== "ready") {
      return;
    }

    const details = detailState.data;
    const menuItemCount =
      details.menu?.sections.reduce((count, section) => count + section.items.length, 0) ?? 0;

    if (!details.menu && details.website_uri && !menuRefreshAttempts.current.has(details.id)) {
      menuRefreshAttempts.current.add(details.id);
      void runMenuRefresh(details);
      return;
    }

    const agentKey = `${details.id}:${selectedAllergenKey}:${menuItemCount}`;
    if (details.agent_recommendation || agentAnalysisAttempts.current.has(agentKey)) {
      return;
    }

    agentAnalysisAttempts.current.add(agentKey);
    void (async () => {
      try {
        const recommendation = await analyzeRestaurant(
          details.id,
          details.name,
          selectedAllergens,
          details.website_uri,
        );
        setDetailStates((current) => {
          const currentState = current[details.id];
          if (!currentState || currentState.status !== "ready") {
            return current;
          }
          return {
            ...current,
            [details.id]: {
              status: "ready",
              data: {
                ...currentState.data,
                agent_recommendation: recommendation,
              },
            },
          };
        });
      } catch {
        // If FastAPI or LangSmith tracing is not configured, the place panel should still work.
      }
    })();
  }, [detailStates, runMenuRefresh, selectedAllergens, selectedAllergenKey, selectedPlaceId]);

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

  const askNearby = async () => {
    const question = nearbyQuestion.trim();
    if (!question) {
      return;
    }
    setNearbyAskState("loading");
    setNearbyAskError(null);
    try {
      const response = await askNearbyPlaces(
        question,
        mapCenter,
        selectedAllergens,
        rankedPlaces.slice(0, 8),
      );
      setNearbyAnswer(response);
      const suggestedPlaces = response.places.map((suggestion) => suggestion.place);
      if (suggestedPlaces.length > 0) {
        const firstSuggestion = suggestedPlaces[0];
        const existingIds = new Set(places.map((place) => place.id));
        const newPlaces = suggestedPlaces.filter((place) => !existingIds.has(place.id));
        if (newPlaces.length > 0) {
          startTransition(() => {
            setPlaces((current) => [...newPlaces, ...current]);
            setDetailStates((current) => ({
              ...current,
              ...Object.fromEntries(newPlaces.map((place) => [place.id, { status: "loading" as const }])),
            }));
          });
          const sequence = ++requestSequence.current;
          void hydratePlaces(newPlaces, selectedAllergens, sequence);
        }
        setSelectedPlaceId((current) => current ?? firstSuggestion.id);
        setMapFocusPlaceId(firstSuggestion.id);
        setSearchTargetPlaceId(firstSuggestion.id);
        setSearchCenter(firstSuggestion.location);
        setMapCenter(firstSuggestion.location);
      }
    } catch (error) {
      setNearbyAskState("error");
      setNearbyAskError(nearbyRagErrorMessage(error));
      return;
    }
    setNearbyAskState("idle");
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

          <section className="nearby-rag-panel">
            <div className="nearby-rag-header">
              <div>
                <span>Agentic RAG</span>
                <strong>Ask AllerNav</strong>
              </div>
              <small>{rankedPlaces.length ? `${Math.min(8, rankedPlaces.length)} visible candidates` : "current map area"}</small>
            </div>
            <form
              className="nearby-rag-form"
              onSubmit={(event) => {
                event.preventDefault();
                void askNearby();
              }}
            >
              <textarea
                value={nearbyQuestion}
                onChange={(event) => setNearbyQuestion(event.target.value)}
                rows={2}
                aria-label="Ask AllerNav for nearby restaurant suggestions"
              />
              <button type="submit" disabled={nearbyAskState === "loading"}>
                {nearbyAskState === "loading" ? "Checking..." : "Ask"}
              </button>
            </form>
            {nearbyAskError && <p className="panel-error">{nearbyAskError}</p>}
            {nearbyAnswer && (
              <div className="nearby-rag-answer">
                <p>{nearbyAnswer.answer}</p>
                {nearbyAnswer.places.length > 0 && (
                  <div className="nearby-rag-suggestions">
                    {nearbyAnswer.places.map((suggestion) => (
                      <button
                        type="button"
                        key={suggestion.place.id}
                        onClick={() => selectPlace(suggestion.place.id)}
                        className="nearby-rag-chip"
                      >
                        <strong>{suggestion.place.name}</strong>
                        <span>
                          {suggestion.menu_item_count} menu items · {suggestion.evidence_count} cited fragments
                        </span>
                        <small>{suggestion.reason}</small>
                      </button>
                    ))}
                  </div>
                )}
                <small>
                  Retrieval: {nearbyAnswer.retrieval_mode.replaceAll("_", " ")} · {nearbyAnswer.evidence.length} cited
                  fragments
                </small>
                {nearbyAnswer.evidence.length > 0 && (
                  <div className="nearby-rag-citations">
                    {nearbyAnswer.evidence.slice(0, 3).map((item, index) => (
                      <article key={item.id} className="nearby-rag-citation">
                        <strong>[E{index + 1}] {item.citation_label}</strong>
                        <p>{item.citation_text}</p>
                        <span>{item.retrieval_mode} · {Math.round(item.confidence * 100)}% confidence</span>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

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
                Search for restaurants, use your location, or ask AllerNav to suggest places in the current map area.
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
            askResponse={selectedPlaceId ? askResponses[selectedPlaceId] : null}
            isAskingRestaurant={askingPlaceId === selectedPlaceId}
            isMenuLoading={selectedPlaceId ? menuLoadingPlaceIds.has(selectedPlaceId) : false}
            menuRefreshJob={selectedPlaceId ? menuRefreshJobs[selectedPlaceId] : undefined}
            onRefreshMenu={() => {
              if (!selectedPlaceId) {
                return;
              }
              const detailState = detailStates[selectedPlaceId];
              if (!detailState || detailState.status !== "ready") {
                return;
              }
              menuRefreshAttempts.current.add(selectedPlaceId);
              void runMenuRefresh(detailState.data);
            }}
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
