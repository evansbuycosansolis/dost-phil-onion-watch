"use client";

import { useEffect, useMemo, useRef } from "react";

import type { LonLatPoint } from "../lib/geospatial";

type Props = {
  title: string;
  vertices: LonLatPoint[];
  onChange: (next: LonLatPoint[]) => void;
};

type LeafletModule = typeof import("leaflet");

type LeafletMapInstance = {
  remove: () => void;
  setView: (center: [number, number], zoom: number) => void;
  fitBounds: (bounds: unknown, options?: unknown) => void;
  eachLayer: (fn: (layer: unknown) => void) => void;
  removeLayer: (layer: unknown) => void;
  on: (eventName: string, handler: (event: { latlng: { lat: number; lng: number } }) => void) => void;
};

const defaultCenter: [number, number] = [16.0, 121.0];

export function GeospatialPolygonMap({ title, vertices, onChange }: Props) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const leafletRef = useRef<LeafletModule | null>(null);
  const instanceRef = useRef<LeafletMapInstance | null>(null);
  const layerGroupRef = useRef<{
    clearLayers: () => void;
    addTo: (map: LeafletMapInstance) => void;
  } | null>(null);

  const positions = useMemo(() => vertices.map((point) => [point.lat, point.lng] as [number, number]), [vertices]);

  useEffect(() => {
    let cancelled = false;

    async function ensureMap() {
      if (!mapRef.current || instanceRef.current) {
        return;
      }
      const L = await import("leaflet");
      if (cancelled || !mapRef.current) {
        return;
      }

      leafletRef.current = L;
      const map = L.map(mapRef.current, {
        center: defaultCenter,
        zoom: 13,
        scrollWheelZoom: true,
      }) as unknown as LeafletMapInstance;

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map as never);

      const layerGroup = L.layerGroup();
      layerGroup.addTo(map as never);

      const handleIcon = L.divIcon({
        className: "aoi-map-handle-wrapper",
        html: '<span class="aoi-map-handle"></span>',
        iconSize: [16, 16],
        iconAnchor: [8, 8],
      });

      map.on("click", (event: { latlng: { lat: number; lng: number } }) => {
        onChange([
          ...vertices,
          {
            lng: Number(event.latlng.lng.toFixed(6)),
            lat: Number(event.latlng.lat.toFixed(6)),
          },
        ]);
      });

      instanceRef.current = map;
      layerGroupRef.current = layerGroup as unknown as { clearLayers: () => void; addTo: (map: LeafletMapInstance) => void };

      renderGeometry(L, map, layerGroup, handleIcon, vertices, onChange);
    }

    void ensureMap();

    return () => {
      cancelled = true;
      if (instanceRef.current) {
        instanceRef.current.remove();
        instanceRef.current = null;
        layerGroupRef.current = null;
      }
    };
  }, [onChange, vertices]);

  useEffect(() => {
    const L = leafletRef.current;
    const map = instanceRef.current;
    const layerGroup = layerGroupRef.current;
    if (!L || !map || !layerGroup) {
      return;
    }

    const handleIcon = L.divIcon({
      className: "aoi-map-handle-wrapper",
      html: '<span class="aoi-map-handle"></span>',
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    });

    renderGeometry(L, map, layerGroup, handleIcon, vertices, onChange);
  }, [onChange, positions, vertices]);

  return (
    <div className="overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm">
      <div ref={mapRef} aria-label={`${title} polygon preview`} className="h-[320px] w-full" />
      <div className="border-t border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
        {title}: click map to add vertices, drag handles to reshape.
      </div>
    </div>
  );
}

function renderGeometry(
  L: LeafletModule,
  map: LeafletMapInstance,
  layerGroup: { clearLayers: () => void },
  handleIcon: unknown,
  vertices: LonLatPoint[],
  onChange: (next: LonLatPoint[]) => void,
) {
  layerGroup.clearLayers();

  const positions = vertices.map((point) => [point.lat, point.lng] as [number, number]);

  if (positions.length === 0) {
    map.setView(defaultCenter, 13);
    return;
  }

  if (positions.length === 1) {
    map.setView(positions[0], 15);
  } else {
    const bounds = L.latLngBounds(positions);
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 16 });
  }

  if (positions.length >= 2) {
    L.polyline(positions, { color: "#2563eb", weight: 2 }).addTo(layerGroup as never);
  }
  if (positions.length >= 3) {
    L.polygon(positions, { color: "#0f172a", weight: 2, fillOpacity: 0.15 }).addTo(layerGroup as never);
  }

  positions.forEach((position, index) => {
    const marker = L.marker(position, {
      draggable: true,
      icon: handleIcon as never,
    }).addTo(layerGroup as never);

    marker.on("dragend", () => {
      const nextLatLng = marker.getLatLng() as { lat: number; lng: number };
      onChange(
        vertices.map((point, pointIndex) =>
          pointIndex === index
            ? { lng: Number(nextLatLng.lng.toFixed(6)), lat: Number(nextLatLng.lat.toFixed(6)) }
            : point,
        ),
      );
    });
  });
}
