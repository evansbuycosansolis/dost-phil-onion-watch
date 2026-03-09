"use client";

import dynamic from "next/dynamic";

import type { LonLatPoint } from "../lib/geospatial";
import { defaultPolygonVertices, polygonSummary, verticesToPolygonGeojson } from "../lib/geospatial";

type Props = {
  title: string;
  vertices: LonLatPoint[];
  onChange: (next: LonLatPoint[]) => void;
  errors: string[];
};

type PolygonMapProps = Pick<Props, "title" | "vertices" | "onChange">;

const GeospatialPolygonMap = dynamic<PolygonMapProps>(
  () => import("./geospatial-polygon-map").then((mod) => mod.default),
  {
    ssr: false,
    loading: () => <div className="h-[320px] animate-pulse rounded-lg border border-slate-300 bg-slate-100" />,
  },
);

export function GeospatialPolygonEditor({ title, vertices, onChange, errors }: Props) {
  const summary = polygonSummary(vertices);
  const closedPreview = verticesToPolygonGeojson(vertices);

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
          <p className="text-xs text-slate-600">Use the map to add vertices and drag handles on the basemap to reshape the AOI polygon.</p>
        </div>
        <div className="text-right text-xs text-slate-600">
          <div>Vertices: {summary.vertexCount}</div>
          <div>BBox: {summary.bboxLabel}</div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <div>
          <GeospatialPolygonMap title={title} vertices={vertices} onChange={onChange} />

          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              aria-label={`${title}: reset polygon`}
              onClick={() => onChange(defaultPolygonVertices())}
              className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white"
            >
              Reset polygon
            </button>
            <button
              type="button"
              aria-label={`${title}: add point`}
              onClick={() => {
                const last = vertices[vertices.length - 1] ?? { lng: 121.0, lat: 16.0 };
                onChange([...vertices, { lng: Number((last.lng + 0.005).toFixed(6)), lat: Number((last.lat + 0.005).toFixed(6)) }]);
              }}
              className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white"
            >
              Add point
            </button>
            <button
              type="button"
              aria-label={`${title}: remove last point`}
              onClick={() => onChange(vertices.slice(0, -1))}
              disabled={vertices.length === 0}
              className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Remove last
            </button>
            <button
              type="button"
              aria-label={`${title}: clear polygon`}
              onClick={() => onChange([])}
              className="rounded border border-rose-300 px-3 py-1 text-xs font-medium text-rose-700 hover:bg-rose-50"
            >
              Clear polygon
            </button>
          </div>
        </div>

        <div>
          <div className="space-y-3">
            {vertices.map((vertex, index) => (
              <div key={`${title}-vertex-${index}`} className="grid gap-2 rounded-md border border-slate-200 bg-white p-3 md:grid-cols-[80px_1fr_1fr_auto]">
                <div className="self-center text-xs font-semibold uppercase tracking-wide text-slate-500">P{index + 1}</div>
                <label className="text-sm text-slate-700">
                  Longitude
                  <input
                    aria-label={`${title} vertex ${index + 1} longitude`}
                    type="number"
                    step="0.000001"
                    value={vertex.lng}
                    onChange={(event) => {
                      const lng = Number(event.target.value);
                      onChange(vertices.map((point, i) => (i === index ? { ...point, lng } : point)));
                    }}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                  />
                </label>
                <label className="text-sm text-slate-700">
                  Latitude
                  <input
                    aria-label={`${title} vertex ${index + 1} latitude`}
                    type="number"
                    step="0.000001"
                    value={vertex.lat}
                    onChange={(event) => {
                      const lat = Number(event.target.value);
                      onChange(vertices.map((point, i) => (i === index ? { ...point, lat } : point)));
                    }}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                  />
                </label>
                <div className="self-end">
                  <button
                    type="button"
                    aria-label={`${title}: remove vertex ${index + 1}`}
                    onClick={() => onChange(vertices.filter((_, i) => i !== index))}
                    className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>

          {errors.length > 0 ? (
            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              <p className="font-semibold">Polygon validation</p>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {errors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
              Polygon is valid and will be submitted as a closed GeoJSON ring.
            </div>
          )}

          <details className="mt-3 rounded-md border border-slate-200 bg-white p-3">
            <summary className="cursor-pointer text-sm font-medium text-slate-700">Advanced GeoJSON preview</summary>
            <pre className="mt-3 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify(closedPreview, null, 2)}</pre>
          </details>
        </div>
      </div>
    </div>
  );
}
