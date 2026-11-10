// Isthmus API client. The frontend never computes scores (BRIEF §13) —
// every number it renders comes from these endpoints.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface DatasetMeta {
  source: string;
  vintage: string | null;
  row_counts: Record<string, number>;
}
export interface Meta {
  datasets: DatasetMeta[];
  method: { summary: string; formula: string; walk_radius_m: number; categories: string[] };
  demo_mode: boolean;
}
export interface RouteInfo {
  route_id: string;
  short_name: string | null;
  long_name: string | null;
  color: string | null;
  stop_count: number;
}
export interface Impact {
  geoid: string;
  name: string;
  score_before: number;
  score_after: number;
  score_drop: number;
  residents_affected: number;
  zero_vehicle_pct: number | null;
  reason: string;
}
export interface BestFix {
  lat: number;
  lon: number;
  route_id: string;
  recovered_score: number;
  note: string;
}
export interface Simulation {
  id: string;
  label: string | null;
  kind: "stop" | "route";
  target_id: string;
  target_name: string;
  created_at: string;
  total_residents_affected: number;
  avg_score_drop: number;
  best_fix: BestFix | null;
  impacts: Impact[];
  tract_scores: Record<string, number>;
}
export interface CompareSummary {
  id: string;
  label: string | null;
  kind: string;
  target_id: string;
  target_name: string | null;
  total_residents_affected: number;
  avg_score_drop: number;
  worst_tract: { name: string; score_drop: number; residents_affected: number } | null;
  best_fix: BestFix | null;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch { /* keep status text */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const b = await res.json();
      if (b?.detail) detail = b.detail;
    } catch { /* keep status text */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  meta: () => getJson<Meta>("/api/meta"),
  tracts: () => getJson<GeoJSON.FeatureCollection>("/api/tracts"),
  stops: () => getJson<GeoJSON.FeatureCollection>("/api/stops"),
  pois: () => getJson<GeoJSON.FeatureCollection>("/api/pois"),
  routes: () =>
    getJson<{ routes: RouteInfo[]; geojson: GeoJSON.FeatureCollection }>("/api/routes"),
  simulate: (kind: string, target_id: string, label?: string) =>
    postJson<Simulation>("/api/simulate", { kind, target_id, label }),
  compare: (a: string, b: string) =>
    getJson<{ a: CompareSummary; b: CompareSummary }>(
      `/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  parseScenario: (text: string) =>
    postJson<{ matched: boolean; kind?: string; target_id?: string;
               matched_name?: string; message?: string }>("/api/parse-scenario", { text }),
};

/** 5-step sequential scale: teal (high access) -> vermillion (low / loss). */
export function scoreColor(score: number): [number, number, number, number] {
  if (score >= 80) return [15, 118, 110, 175];   // deep teal
  if (score >= 60) return [20, 145, 155, 175];   // teal
  if (score >= 40) return [150, 122, 88, 175];   // warm neutral
  if (score >= 20) return [205, 92, 48, 190];    // ember
  return [250, 88, 56, 205];                     // Flare Orange / vermillion
}

export const CATEGORY_LABELS: Record<string, string> = {
  grocery: "Grocery",
  health: "Health",
  library: "Library",
  education: "Education / Campus",
};
export const CATEGORY_COLORS: Record<string, string> = {
  grocery: "#fcac9c",
  health: "#f7f6ff",
  library: "#baadab",
  education: "#fa5838",
};
