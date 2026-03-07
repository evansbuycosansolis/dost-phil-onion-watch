export type LonLatPoint = {
  lng: number;
  lat: number;
};

const EPSILON = 1e-9;

export function defaultPolygonVertices(): LonLatPoint[] {
  return [
    { lng: 121.0, lat: 16.0 },
    { lng: 121.01, lat: 16.0 },
    { lng: 121.01, lat: 16.01 },
    { lng: 121.0, lat: 16.01 },
  ];
}

export function verticesToPolygonGeojson(vertices: LonLatPoint[]): Record<string, unknown> {
  const closed = closeRing(vertices);
  return {
    type: "Polygon",
    coordinates: [closed.map((point) => [roundCoord(point.lng), roundCoord(point.lat)])],
  };
}

export function polygonGeojsonToVertices(geojson: Record<string, unknown>): LonLatPoint[] {
  const polygon = normalizePolygonInput(geojson);
  const coordinates = polygon.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length === 0) {
    throw new Error("Polygon coordinates are missing.");
  }
  const outerRing = coordinates[0];
  if (!Array.isArray(outerRing) || outerRing.length < 4) {
    throw new Error("Polygon outer ring must contain at least 4 coordinates.");
  }

  const parsed = outerRing.map((pair) => {
    if (!Array.isArray(pair) || pair.length < 2) {
      throw new Error("Each polygon coordinate must be a [lng, lat] pair.");
    }
    const lng = Number(pair[0]);
    const lat = Number(pair[1]);
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
      throw new Error("Polygon coordinates must be numeric.");
    }
    return { lng, lat };
  });

  const first = parsed[0];
  const last = parsed[parsed.length - 1];
  if (!pointsEqual(first, last)) {
    throw new Error("Polygon outer ring must be closed.");
  }

  return parsed.slice(0, -1);
}

export function validatePolygonVertices(vertices: LonLatPoint[]): string[] {
  const errors: string[] = [];
  if (vertices.length < 3) {
    errors.push("Polygon needs at least 3 vertices.");
  }

  vertices.forEach((vertex, index) => {
    if (!Number.isFinite(vertex.lng) || !Number.isFinite(vertex.lat)) {
      errors.push(`Vertex ${index + 1} must have numeric coordinates.`);
      return;
    }
    if (vertex.lng < -180 || vertex.lng > 180) {
      errors.push(`Vertex ${index + 1} longitude must be between -180 and 180.`);
    }
    if (vertex.lat < -90 || vertex.lat > 90) {
      errors.push(`Vertex ${index + 1} latitude must be between -90 and 90.`);
    }
  });

  const uniqueVertexCount = new Set(vertices.map((vertex) => `${roundCoord(vertex.lng)}:${roundCoord(vertex.lat)}`)).size;
  if (vertices.length >= 3 && uniqueVertexCount < 3) {
    errors.push("Polygon must contain at least 3 unique vertices.");
  }

  return Array.from(new Set(errors));
}

export function validatePolygonGeojson(geojson: Record<string, unknown>): string[] {
  try {
    const vertices = polygonGeojsonToVertices(geojson);
    return validatePolygonVertices(vertices);
  } catch (error) {
    return [error instanceof Error ? error.message : "Invalid GeoJSON polygon."];
  }
}

export function polygonSummary(vertices: LonLatPoint[]): { bboxLabel: string; vertexCount: number } {
  if (vertices.length === 0) {
    return { bboxLabel: "No vertices", vertexCount: 0 };
  }
  const lngs = vertices.map((point) => point.lng);
  const lats = vertices.map((point) => point.lat);
  return {
    bboxLabel: `${roundCoord(Math.min(...lngs))}, ${roundCoord(Math.min(...lats))} → ${roundCoord(Math.max(...lngs))}, ${roundCoord(Math.max(...lats))}`,
    vertexCount: vertices.length,
  };
}

function normalizePolygonInput(input: Record<string, unknown>) {
  if (input.type === "Feature") {
    const geometry = input.geometry;
    if (!geometry || typeof geometry !== "object" || Array.isArray(geometry)) {
      throw new Error("Feature geometry is missing.");
    }
    return normalizePolygonInput(geometry as Record<string, unknown>);
  }

  if (input.type !== "Polygon") {
    throw new Error("Only Polygon GeoJSON is supported for AOI editing.");
  }

  return input as { type: "Polygon"; coordinates: unknown[] };
}

function closeRing(vertices: LonLatPoint[]): LonLatPoint[] {
  if (vertices.length === 0) {
    return [];
  }
  const first = vertices[0];
  const last = vertices[vertices.length - 1];
  if (pointsEqual(first, last)) {
    return [...vertices];
  }
  return [...vertices, first];
}

function pointsEqual(a: LonLatPoint, b: LonLatPoint) {
  return Math.abs(a.lng - b.lng) < EPSILON && Math.abs(a.lat - b.lat) < EPSILON;
}

function roundCoord(value: number) {
  return Number(value.toFixed(6));
}
