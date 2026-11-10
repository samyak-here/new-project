"use client";
import { useMemo, useState } from "react";
import type { RouteInfo } from "@/lib/api";

interface StopOption {
  stop_id: string;
  name: string;
}

interface Props {
  routes: RouteInfo[];
  stops: StopOption[];
  loading: boolean;
  error: string | null;
  onSimulate: (kind: "stop" | "route", targetId: string, label: string) => void;
}

export default function SimulatePanel({ routes, stops, loading, error, onSimulate }: Props) {
  const [kind, setKind] = useState<"stop" | "route">("route");
  const [routeId, setRouteId] = useState<string>("");
  const [stopQuery, setStopQuery] = useState("");
  const [label, setLabel] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const matchedStop = useMemo(() => {
    const q = stopQuery.trim().toLowerCase();
    if (!q) return null;
    return (
      stops.find((s) => s.stop_id === q) ||
      stops.find((s) => s.name.toLowerCase() === q) ||
      stops.find((s) => s.name.toLowerCase().includes(q)) ||
      null
    );
  }, [stopQuery, stops]);

  const submit = () => {
    setLocalError(null);
    if (kind === "route") {
      const target = routeId || routes[0]?.route_id;
      if (!target) return setLocalError("No routes loaded yet.");
      onSimulate("route", target, label.trim());
    } else {
      if (!matchedStop) return setLocalError("No stop matches that name or ID yet.");
      onSimulate("stop", matchedStop.stop_id, label.trim());
    }
  };

  return (
    <section aria-label="Simulate a closure" className="hairline rounded-lg bg-[#260b03] p-4">
      <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#baadab]">
        Simulate closure
      </h2>
      <div className="mt-3 flex gap-2" role="tablist" aria-label="Closure type">
        {(["route", "stop"] as const).map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={kind === k}
            onClick={() => setKind(k)}
            className={`rounded px-3 py-1.5 text-sm capitalize focus:outline-2 ${
              kind === k
                ? "bg-[#340a01] text-[#f7f6ff] shadow-[inset_0_0_12px_rgba(99,19,3,0.9)]"
                : "bg-transparent text-[#baadab] hairline"
            }`}
          >
            {k === "route" ? "Bus route" : "Single stop"}
          </button>
        ))}
      </div>

      {kind === "route" ? (
        <label className="mt-3 block text-sm">
          <span className="text-[#baadab]">Route</span>
          <select
            value={routeId}
            onChange={(e) => setRouteId(e.target.value)}
            className="mt-1 w-full rounded bg-[#190501] hairline px-2 py-2 text-[#f7f6ff]"
          >
            {routes.map((r) => (
              <option key={r.route_id} value={r.route_id}>
                Route {r.short_name ?? r.route_id}
                {r.long_name ? ` — ${r.long_name}` : ""} ({r.stop_count} stops)
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label className="mt-3 block text-sm">
          <span className="text-[#baadab]">Stop name or ID</span>
          <input
            value={stopQuery}
            onChange={(e) => setStopQuery(e.target.value)}
            list="isthmus-stop-names"
            placeholder="e.g. Capitol or a stop ID"
            className="mt-1 w-full rounded bg-[#190501] hairline px-2 py-2 text-[#f7f6ff] placeholder:text-[#baadab]/60"
          />
          <datalist id="isthmus-stop-names">
            {stops.slice(0, 400).map((s) => (
              <option key={s.stop_id} value={s.name}>{s.stop_id}</option>
            ))}
          </datalist>
          {matchedStop && (
            <span className="mt-1 block font-mono text-xs text-[#fcac9c]">
              {matchedStop.stop_id} · {matchedStop.name}
            </span>
          )}
        </label>
      )}

      <label className="mt-3 block text-sm">
        <span className="text-[#baadab]">Scenario label (optional)</span>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Scenario A"
          className="mt-1 w-full rounded bg-[#190501] hairline px-2 py-2 text-[#f7f6ff] placeholder:text-[#baadab]/60"
        />
      </label>

      <button
        onClick={submit}
        disabled={loading}
        className="ember-button mt-4 w-full rounded px-3 py-2.5 font-medium text-[#f7f6ff] disabled:opacity-50"
      >
        {loading ? "Simulating…" : "Simulate closure"}
      </button>
      {(localError || error) && (
        <p role="alert" className="mt-2 text-sm text-[#fcac9c]">{localError || error}</p>
      )}
      <p className="mt-2 text-xs leading-relaxed text-[#baadab]">
        Or type a scenario in the search bar above, like “Close Route 80”.
      </p>
    </section>
  );
}
