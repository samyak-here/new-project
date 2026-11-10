"use client";
// Full-screen Madison map: MapLibre dark basemap + Deck.gl layers.
// Fallback (documented in NOTES.md): if Deck.gl fails to load at runtime,
// tracts/stops render as plain MapLibre GeoJSON layers instead.
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { scoreColor, CATEGORY_COLORS } from "@/lib/api";

export interface FlyTo {
  lon: number;
  lat: number;
  nonce: number;
}

interface Props {
  tracts: GeoJSON.FeatureCollection | null;
  stops: GeoJSON.FeatureCollection | null;
  pois: GeoJSON.FeatureCollection | null;
  routesGeojson: GeoJSON.FeatureCollection | null;
  showStops: boolean;
  showRoutes: boolean;
  visibleCategories: Set<string>;
  scenarioScores: Record<string, number> | null;
  bestFix: { lat: number; lon: number } | null;
  flyTo: FlyTo | null;
  onSelectTract: (props: Record<string, unknown>) => void;
  onSelectStop: (props: Record<string, unknown>) => void;
}

const DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

export default function MapView(props: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<{ setProps: (p: Record<string, unknown>) => void } | null>(null);
  const deckFailedRef = useRef(false);
  const propsRef = useRef(props);
  propsRef.current = props;

  // --- init map once -------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_STYLE,
      center: [-89.4012, 43.0731], // Madison isthmus, between the lakes
      zoom: 11,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.on("style.load", async () => {
      try {
        const { MapboxOverlay } = await import("@deck.gl/mapbox");
        const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
        map.addControl(overlay as unknown as maplibregl.IControl);
        overlayRef.current = overlay as unknown as typeof overlayRef.current;
        pushLayers();
      } catch (err) {
        console.warn("Deck.gl failed to load; using MapLibre fallback layers.", err);
        deckFailedRef.current = true;
        pushLayers();
      }
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- fly-to ---------------------------------------------------------------
  useEffect(() => {
    if (props.flyTo && mapRef.current) {
      mapRef.current.flyTo({ center: [props.flyTo.lon, props.flyTo.lat], zoom: 13.5 });
    }
  }, [props.flyTo]);

  // --- layers ---------------------------------------------------------------
  function buildDeckLayers() {
    const p = propsRef.current;
    return (async () => {
      const [{ GeoJsonLayer, ScatterplotLayer, PathLayer }] = await Promise.all([
        import("@deck.gl/layers"),
      ]);
      const layers: unknown[] = [];
      if (p.routesGeojson && p.showRoutes) {
        const paths = (p.routesGeojson.features || [])
          .filter((f) => f.geometry?.type === "LineString")
          .map((f) => ({
            path: (f.geometry as GeoJSON.LineString).coordinates.map(
              (c) => [c[0], c[1]] as [number, number]),
            route_id: (f.properties || {}).route_id,
          }));
        if (paths.length) {
          layers.push(new PathLayer({
            id: "routes", data: paths,
            getPath: (d: { path: [number, number][] }) => d.path,
            getColor: [149, 28, 4, 130], getWidth: 2, widthUnits: "pixels", pickable: false,
          }));
        }
      }
      if (p.tracts) {
        const scored = {
          ...p.tracts,
          features: p.tracts.features.map((f) => {
            const pr = (f.properties || {}) as Record<string, number>;
            const display = p.scenarioScores?.[String(pr.geoid)] ?? pr.access_score ?? 0;
            return { ...f, properties: { ...pr, _display: display } };
          }),
        };
        layers.push(new GeoJsonLayer({
          id: "tracts", data: scored, pickable: true, stroked: true, filled: true,
          getFillColor: (f: GeoJSON.Feature) =>
            scoreColor(Number((f.properties as Record<string, number>)?._display ?? 0)),
          getLineColor: [186, 173, 171, 90], lineWidthMinPixels: 0.5,
          transitions: { getFillColor: 400 }, // the ember flip (prefers-reduced-motion handled in CSS for DOM; Deck transition is data-driven)
          updateTriggers: { getFillColor: [p.scenarioScores] },
          onClick: (info: { object?: GeoJSON.Feature }) => {
            if (info.object?.properties) {
              p.onSelectTract(info.object.properties as Record<string, unknown>);
            }
          },
        }));
      }
      if (p.pois) {
        const visible = {
          ...p.pois,
          features: p.pois.features.filter((f) =>
            p.visibleCategories.has(String((f.properties || {}).category))),
        };
        layers.push(new ScatterplotLayer({
          id: "pois", data: visible.features, pickable: false,
          getPosition: (f: GeoJSON.Feature) => (f.geometry as GeoJSON.Point).coordinates as [number, number],
          getRadius: 55, radiusUnits: "meters",
          getFillColor: (f: GeoJSON.Feature) => {
            const hex = CATEGORY_COLORS[String((f.properties || {}).category)] || "#f7f6ff";
            const n = parseInt(hex.slice(1), 16);
            return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 190];
          },
        }));
      }
      if (p.stops && p.showStops) {
        layers.push(new ScatterplotLayer({
          id: "stops", data: p.stops.features, pickable: true,
          getPosition: (f: GeoJSON.Feature) => (f.geometry as GeoJSON.Point).coordinates as [number, number],
          getRadius: 28, radiusUnits: "meters", getFillColor: [247, 246, 255, 170],
          onClick: (info: { object?: GeoJSON.Feature }) => {
            if (info.object?.properties) {
              p.onSelectStop(info.object.properties as Record<string, unknown>);
            }
          },
        }));
      }
      if (p.bestFix) {
        layers.push(new ScatterplotLayer({
          id: "best-fix", data: [p.bestFix], pickable: false,
          getPosition: (d: { lat: number; lon: number }) => [d.lon, d.lat],
          getRadius: 150, radiusUnits: "meters",
          getFillColor: [250, 88, 56, 230], getLineColor: [254, 234, 230, 255],
          lineWidthMinPixels: 2, stroked: true,
        }));
      }
      return layers;
    })();
  }

  function pushFallbackLayers() {
    const map = mapRef.current;
    const p = propsRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const upsert = (id: string, data: GeoJSON.FeatureCollection | null) => {
      const source = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
      if (source && data) source.setData(data);
      else if (data && !source) map.addSource(id, { type: "geojson", data });
    };
    if (p.tracts && !map.getLayer("tracts-fill")) {
      upsert("tracts", p.tracts);
      map.addLayer({
        id: "tracts-fill", type: "fill", source: "tracts",
        paint: {
          "fill-color": ["interpolate", ["linear"], ["get", "access_score"],
            0, "#fa5838", 20, "#cd5c30", 40, "#967a58", 60, "#14919b", 80, "#0f766e"],
          "fill-opacity": 0.68, "fill-outline-color": "rgba(186,173,171,0.35)",
        },
      });
      map.on("click", "tracts-fill", (e) => {
        const f = e.features?.[0];
        if (f?.properties) p.onSelectTract(f.properties as Record<string, unknown>);
      });
    } else upsert("tracts", p.tracts);
    if (p.stops && !map.getLayer("stops-circle")) {
      upsert("stops", p.stops);
      map.addLayer({
        id: "stops-circle", type: "circle", source: "stops",
        paint: { "circle-radius": 2.5, "circle-color": "rgba(247,246,255,0.65)" },
        layout: { visibility: p.showStops ? "visible" : "none" },
      });
    } else {
      upsert("stops", p.stops);
      if (map.getLayer("stops-circle")) {
        map.setLayoutProperty("stops-circle", "visibility", p.showStops ? "visible" : "none");
      }
    }
  }

  function pushLayers() {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    if (deckFailedRef.current) {
      pushFallbackLayers();
      return;
    }
    if (!overlayRef.current) return;
    buildDeckLayers()
      .then((layers) => overlayRef.current?.setProps({ layers }))
      .catch((err) => {
        console.warn("Deck.gl layer build failed; switching to fallback.", err);
        deckFailedRef.current = true;
        pushFallbackLayers();
      });
  }

  useEffect(() => {
    pushLayers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.tracts, props.stops, props.pois, props.routesGeojson, props.showStops,
      props.showRoutes, props.visibleCategories, props.scenarioScores, props.bestFix]);

  // Inline positioning, not Tailwind classes: maplibre-gl.css is unlayered and
  // its `.maplibregl-map { position: relative }` rule would otherwise override
  // Tailwind's layered `absolute inset-0`, collapsing the container height to 0.
  return (
    <div
      ref={containerRef}
      style={{ position: "absolute", inset: 0 }}
      aria-label="Map of Madison"
    />
  );
}
