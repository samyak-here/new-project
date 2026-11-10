"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MapView, { type FlyTo } from "@/components/MapView";
import SimulatePanel from "@/components/SimulatePanel";
import ImpactQueue from "@/components/ImpactQueue";
import BestFixCard from "@/components/BestFixCard";
import CompareView from "@/components/CompareView";
import MethodPanel from "@/components/MethodPanel";
import Legend from "@/components/Legend";
import {
  api, CATEGORY_LABELS,
  type Meta, type RouteInfo, type Simulation,
} from "@/lib/api";

interface TractPopup {
  name: string;
  access: number;
  cats: Array<[string, number]>;
  population: number;
  zeroVehicle: number | null;
}

export default function Home() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [tracts, setTracts] = useState<GeoJSON.FeatureCollection | null>(null);
  const [stops, setStops] = useState<GeoJSON.FeatureCollection | null>(null);
  const [pois, setPois] = useState<GeoJSON.FeatureCollection | null>(null);
  const [routes, setRoutes] = useState<RouteInfo[]>([]);
  const [routesGeojson, setRoutesGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [showStops, setShowStops] = useState(true);
  const [showRoutes, setShowRoutes] = useState(true);
  const [categories, setCategories] = useState<Set<string>>(new Set(Object.keys(CATEGORY_LABELS)));

  const [search, setSearch] = useState("");
  const [searchError, setSearchError] = useState<string | null>(null);
  const [flyTo, setFlyTo] = useState<FlyTo | null>(null);
  const nonce = useRef(0);

  const [simLoading, setSimLoading] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);
  const [currentSim, setCurrentSim] = useState<Simulation | null>(null);
  const [saved, setSaved] = useState<Simulation[]>([]);
  const [methodOpen, setMethodOpen] = useState(false);
  const [tractPopup, setTractPopup] = useState<TractPopup | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [m, t, s, p, r] = await Promise.all([
        api.meta(), api.tracts(), api.stops(), api.pois(), api.routes(),
      ]);
      setMeta(m); setTracts(t); setStops(s); setPois(p);
      setRoutes(r.routes); setRoutesGeojson(r.geojson);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const stopOptions = useMemo(
    () =>
      (stops?.features || []).map((f) => {
        const pr = (f.properties || {}) as Record<string, string>;
        return { stop_id: pr.stop_id, name: pr.name };
      }),
    [stops]);

  const runSimulation = useCallback(
    async (kind: "stop" | "route", targetId: string, label: string) => {
      setSimLoading(true);
      setSimError(null);
      try {
        const sim = await api.simulate(kind, targetId, label || undefined);
        setCurrentSim(sim);
        setSaved((prev) => [...prev, sim]);
      } catch (e) {
        setSimError(e instanceof Error ? e.message : String(e));
      } finally {
        setSimLoading(false);
      }
    }, []);

  const doFly = useCallback((lon: number, lat: number) => {
    nonce.current += 1;
    setFlyTo({ lon, lat, nonce: nonce.current });
  }, []);

  const submitSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = search.trim();
    if (!q) return;
    setSearchError(null);
    const lower = q.toLowerCase();
    // Local matches first: route short name, stop id, stop name.
    const route = routes.find(
      (r) => (r.short_name || "").toLowerCase() === lower.replace(/^route\s+/, ""));
    if (route) {
      runSimulation("route", route.route_id, "");
      return;
    }
    const stopById = stopOptions.find((s) => s.stop_id === q);
    const stopByName = stopOptions.find((s) => s.name.toLowerCase().includes(lower));
    const stopHit = stopById || stopByName;
    if (stopHit && !/^(close|stop|remove)\b/.test(lower)) {
      const feat = stops?.features.find(
        (f) => (f.properties as Record<string, string>)?.stop_id === stopHit.stop_id);
      const coords = (feat?.geometry as GeoJSON.Point)?.coordinates;
      if (coords) doFly(coords[0], coords[1]);
      return;
    }
    // Otherwise ask the API's rule-based scenario parser (BRIEF §9).
    try {
      const parsed = await api.parseScenario(q);
      if (parsed.matched && parsed.kind && parsed.target_id) {
        runSimulation(parsed.kind as "stop" | "route", parsed.target_id, "");
      } else {
        setSearchError(parsed.message || "Could not match that search.");
      }
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : String(err));
    }
  };

  const toggleCategory = (cat: string) => {
    setCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat); else next.add(cat);
      return next;
    });
  };

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-[#190501]">
      <MapView
        tracts={tracts} stops={stops} pois={pois} routesGeojson={routesGeojson}
        showStops={showStops} showRoutes={showRoutes} visibleCategories={categories}
        scenarioScores={currentSim ? currentSim.tract_scores : null}
        bestFix={currentSim?.best_fix ? { lat: currentSim.best_fix.lat, lon: currentSim.best_fix.lon } : null}
        flyTo={flyTo}
        onSelectTract={(pr) => {
          setTractPopup({
            name: String(pr.name || "Tract"),
            access: Number(pr.access_score ?? 0),
            cats: [
              ["Grocery", Number(pr.score_grocery ?? 0)],
              ["Health", Number(pr.score_health ?? 0)],
              ["Library", Number(pr.score_library ?? 0)],
              ["Education", Number(pr.score_education ?? 0)],
            ],
            population: Number(pr.population ?? 0),
            zeroVehicle: pr.zero_vehicle_pct != null ? Number(pr.zero_vehicle_pct) : null,
          });
        }}
        onSelectStop={(pr) => {
          setSearch(String(pr.name || pr.stop_id || ""));
        }}
      />

      {/* Top bar */}
      <header className="absolute inset-x-0 top-0 z-30 flex items-center gap-3 bg-[#190501]/92 px-3 py-2 backdrop-blur hairline-b">
        <h1 className="font-display text-lg font-bold tracking-tight">
          Isthmus<span className="text-[#fa5838]">.</span>
        </h1>
        <span className="hidden font-mono text-[11px] uppercase tracking-[0.18em] text-[#baadab] lg:inline">
          Madison transit what-if
        </span>
        <form onSubmit={submitSearch} className="relative mx-auto w-full max-w-xl">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search a stop, or type “Close Route 80”"
            aria-label="Search stops and routes, or type a scenario"
            className="w-full rounded bg-[#260b03] hairline px-3 py-2 font-mono text-sm text-[#f7f6ff] placeholder:text-[#baadab]/70"
          />
          {searchError && (
            <p role="alert" className="absolute left-0 top-full mt-1 rounded bg-[#340a01] px-2 py-1 text-xs text-[#fcac9c]">
              {searchError}
            </p>
          )}
        </form>
        <button
          onClick={() => setMethodOpen(true)}
          className="shrink-0 rounded hairline px-3 py-2 text-sm text-[#f7f6ff]"
        >
          Method
        </button>
      </header>

      {/* Layer toggles */}
      <div className="absolute left-3 top-16 z-20 rounded-lg bg-[#200903]/90 p-3 hairline backdrop-blur">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#baadab]">Layers</p>
        <label className="mt-2 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showStops} onChange={(e) => setShowStops(e.target.checked)} />
          Bus stops
        </label>
        <label className="mt-1 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showRoutes} onChange={(e) => setShowRoutes(e.target.checked)} />
          Route lines
        </label>
        <div className="mt-2 space-y-1">
          {Object.entries(CATEGORY_LABELS).map(([cat, label]) => (
            <label key={cat} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={categories.has(cat)}
                onChange={() => toggleCategory(cat)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <Legend scenarioActive={!!currentSim} />

      {/* Tract popover */}
      {tractPopup && (
        <div className="absolute bottom-3 left-1/2 z-20 w-64 -translate-x-1/2 rounded-lg bg-[#200903]/95 p-3 hairline backdrop-blur md:left-auto md:right-[404px] md:translate-x-0">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-medium">{tractPopup.name}</h3>
            <button onClick={() => setTractPopup(null)} aria-label="Close tract details"
              className="text-[#baadab]">×</button>
          </div>
          <p className="mt-1 font-mono text-sm">
            Access Score <span className="text-[#14919b]">{tractPopup.access}</span>
            <span className="text-[#baadab]"> / 100</span>
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            {tractPopup.cats.map(([label, v]) => (
              <li key={label} className="flex justify-between">
                <span className="text-[#baadab]">{label}</span>
                <span className="font-mono">{v.toFixed(0)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 font-mono text-[11px] text-[#baadab]">
            pop. {tractPopup.population.toLocaleString()}
            {tractPopup.zeroVehicle != null
              ? ` · ${tractPopup.zeroVehicle.toFixed(0)}% zero-vehicle households`
              : ""}
          </p>
        </div>
      )}

      {/* Right panel / mobile bottom sheet */}
      <aside className="absolute z-30 space-y-3 overflow-y-auto p-3 max-md:inset-x-0 max-md:bottom-0 max-md:max-h-[52dvh] md:bottom-3 md:right-3 md:top-16 md:w-[380px]">
        {loadError && (
          <div role="alert" className="rounded-lg bg-[#340a01] p-4 text-sm ember-glow">
            <p className="font-medium">Data could not be loaded.</p>
            <p className="mt-1 font-mono text-xs leading-relaxed text-[#fcac9c]">{loadError}</p>
            <button onClick={load} className="ember-button mt-3 rounded px-3 py-2 text-sm">
              Retry
            </button>
          </div>
        )}
        {loading && !loadError && (
          <div className="hairline rounded-lg bg-[#260b03] p-4 font-mono text-sm text-[#baadab]">
            Loading Madison data…
          </div>
        )}
        {currentSim && (
          <button
            onClick={() => setCurrentSim(null)}
            className="w-full rounded hairline bg-[#260b03] px-3 py-2 text-sm text-[#f7f6ff]"
          >
            ← Back to baseline map (simulation stays saved below)
          </button>
        )}
        <SimulatePanel
          routes={routes} stops={stopOptions} loading={simLoading}
          error={simError} onSimulate={runSimulation}
        />
        <ImpactQueue sim={currentSim} />
        <BestFixCard sim={currentSim} />
        <CompareView saved={saved} />
      </aside>

      <MethodPanel meta={meta} open={methodOpen} onClose={() => setMethodOpen(false)} />
    </main>
  );
}
