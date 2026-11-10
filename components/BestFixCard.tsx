"use client";
import type { Simulation } from "@/lib/api";

export default function BestFixCard({ sim }: { sim: Simulation | null }) {
  if (!sim) return null;
  if (!sim.best_fix) {
    return (
      <section aria-label="Best fix" className="hairline rounded-lg bg-[#260b03] p-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#baadab]">
          Best fix
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-[#baadab]">
          No single added stop recovered access for this closure — the affected
          tracts are not near a still-running route.
        </p>
      </section>
    );
  }
  const bf = sim.best_fix;
  return (
    <section
      aria-label="Best fix"
      className="ember-glow rounded-lg bg-[#340a01] p-4"
    >
      <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#fcac9c]">
        Best fix found
      </h2>
      <p className="mt-2 font-display text-lg font-bold leading-snug text-[#f7f6ff]">
        Add a temporary stop here —{" "}
        <span className="text-[#fa5838]">+{bf.recovered_score.toFixed(0)}</span>{" "}
        Access points recovered
      </p>
      <p className="mt-1 text-sm leading-relaxed text-[#f7f6ff]/85">{bf.note}</p>
      <p className="mt-2 font-mono text-xs text-[#fcac9c]">
        {bf.lat.toFixed(5)}, {bf.lon.toFixed(5)} · served by route {bf.route_id} · pin shown on map
      </p>
    </section>
  );
}
