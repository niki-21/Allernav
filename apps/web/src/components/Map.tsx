"use client";

import { GoogleMap, InfoWindow, Marker, useJsApiLoader } from "@react-google-maps/api";
import { useEffect, useMemo, useState } from "react";

import type { LatLng, PlaceDetailState, PlaceSummary } from "@/lib/types";

interface MapProps {
  places: PlaceSummary[];
  details: Record<string, PlaceDetailState>;
  selectedPlaceId: string | null;
  searchCenter: LatLng;
  onPlaceSelect: (placeId: string | null) => void;
  onMapCenterChange: (center: LatLng) => void;
}

const DEFAULT_CENTER = { lat: 40.741895, lng: -73.989308 };

const MAP_STYLES: google.maps.MapTypeStyle[] = [
  { featureType: "administrative", elementType: "labels.text.fill", stylers: [{ color: "#6d635d" }] },
  { featureType: "landscape", elementType: "geometry", stylers: [{ color: "#f4efe8" }] },
  { featureType: "poi", elementType: "geometry", stylers: [{ color: "#eadfce" }] },
  { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#d7e4d0" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#ffffff" }] },
  { featureType: "road", elementType: "labels.text.fill", stylers: [{ color: "#8b8079" }] },
  { featureType: "transit", elementType: "labels.text.fill", stylers: [{ color: "#8b8079" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#cadbe5" }] },
];

function getMarkerColor(detailState?: PlaceDetailState): string {
  if (!detailState || detailState.status === "loading") {
    return "#7d8ea3";
  }
  if (detailState.status === "error") {
    return "#b99277";
  }

  switch (detailState.data.score_summary.verdict) {
    case "good_fit":
      return "#2e8b57";
    case "high_risk":
      return "#b63f2c";
    default:
      return "#cf8d2e";
  }
}

export default function Map({
  places,
  details,
  selectedPlaceId,
  searchCenter,
  onPlaceSelect,
  onMapCenterChange,
}: MapProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";
  const { isLoaded } = useJsApiLoader({
    googleMapsApiKey: apiKey,
  });
  const [map, setMap] = useState<google.maps.Map | null>(null);

  useEffect(() => {
    if (!map) {
      return;
    }
    map.panTo(searchCenter);
  }, [map, searchCenter]);

  const selectedPlace = useMemo(
    () => places.find((place) => place.id === selectedPlaceId) ?? null,
    [places, selectedPlaceId],
  );

  if (!apiKey) {
    return <div className="map-loading">Add `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` to render the map.</div>;
  }

  if (!isLoaded) {
    return <div className="map-loading">Loading map…</div>;
  }

  return (
    <GoogleMap
      mapContainerStyle={{ width: "100%", height: "100%" }}
      center={searchCenter ?? DEFAULT_CENTER}
      zoom={14}
      onLoad={(instance) => {
        setMap(instance);
        instance.setOptions({
          disableDefaultUI: true,
          zoomControl: true,
          streetViewControl: false,
          fullscreenControl: false,
          mapTypeControl: false,
          styles: MAP_STYLES,
          gestureHandling: "greedy",
        });
      }}
      onIdle={() => {
        if (!map) {
          return;
        }
        const center = map.getCenter();
        if (!center) {
          return;
        }
        onMapCenterChange({ lat: center.lat(), lng: center.lng() });
      }}
    >
      {places.map((place) => (
        <Marker
          key={place.id}
          position={place.location}
          onClick={() => onPlaceSelect(place.id)}
          icon={{
            path: google.maps.SymbolPath.CIRCLE,
            scale: selectedPlaceId === place.id ? 10 : 8,
            fillColor: getMarkerColor(details[place.id]),
            fillOpacity: 1,
            strokeColor: "#fffaf4",
            strokeWeight: 2,
          }}
        />
      ))}

      {selectedPlace && (
        <InfoWindow position={selectedPlace.location} onCloseClick={() => onPlaceSelect(null)}>
          <div className="map-info-window">
            <strong>{selectedPlace.name}</strong>
            <p>{selectedPlace.address ?? "Address unavailable"}</p>
            {details[selectedPlace.id]?.status === "ready" ? (
              <span className="map-pill">
                Allergy Fit {details[selectedPlace.id].data.score_summary.score} ·{" "}
                {details[selectedPlace.id].data.score_summary.evidence_count} signals
              </span>
            ) : (
              <span className="map-pill">Scoring in progress</span>
            )}
          </div>
        </InfoWindow>
      )}
    </GoogleMap>
  );
}
