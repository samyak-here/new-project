"use client";
import type { Simulation } from "@/lib/api";

function ThermalStrip({ sim }: { sim: Simulation }) {
  const bars = sim.impacts.slice(0, 24);
  const max = Math.max(1, ...bars.map((i) => i.score_drop));
  return (
    <div className="flex h-8 items-end gap-[3px]" aria-hidden="true">
      {bars.map((imp, idx) => (
        <div
          key={idx}
          className="thermal-bar w-[6px] rounded-t-sm"
          style={{ height: `${Math.max(8, (imp.score_drop / max) * 100)}%`, opacity: 0.35 + 0.65 * (imp.score_drop / max) }}
        />
      ))}
    </div>
  );
}

export default function ImpactQueue({ sim }: { sim: Simulation | null }) {
  if (!sim) {
    return (
      <section aria-label="Impact queue" className="hairline rounded-lg bg-[#260b03] p-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#baadab]">
          Impact queue
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-[#baadab]">
          Close a stop or route to see who is affected. Neighborhoods will be
          ranked here, hardest hit first, each with a one-sentence reason.
        </p>
      </section>
    );
  }
  const maxDrop = Math.max(1, ...sim.impacts.map((i) => i.score_drop));
  return (
    <section aria-label="Impact queue" className="hairline rounded-lg bg-[#260b03] p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#baadab]">
          Impact queue
        </h2>
        <span className="font-mono text-xs text-[#fcac9c]">
          {sim.target_name}
        </span>
      </div>
      <div className="mt-2 flex items-end justify-between gap-3">
        <ThermalStrip sim={sim} />
        <div className="text-right font-mono text-xs leading-relaxed">
          <div>
            ACCESS <span className="text-[#fa5838]">−{sim.avg_score_drop.toFixed(1)}</span> avg
          </div>
          <div>
            <span className="text-[#f7f6ff]">{sim.total_residents_affected.toLocaleString()}</span>{" "}
            est. residents affected
          </div>
        </div>
      </div>
      <ol className="mt-3 space-y-2">
        {sim.impacts.filter((i) => i.score_drop > 0).slice(0, 15).map((imp, idx) => (
          <li key={imp.geoid} className="flex gap-3 rounded-md bg-[#190501] p-3">
            <div className="relative w-[3px] shrink-0 overflow-hidden rounded bg-[#340a01]" aria-hidden="true">
              <div
                className="thermal-bar absolute bottom-0 left-0 w-full"
                style={{ height: `${(imp.score_drop / maxDrop) * 100}%` }}
              />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-mono text-xs text-[#baadab]">{String(idx + 1).padStart(2, "0")}</span>
                <span className="font-medium">{imp.name}</span>
                <span className="font-mono text-sm">
                  {imp.score_before} → {imp.score_after}{" "}
                  <span className="text-[#fa5838]">−{imp.score_drop}</span>
                </span>
              </div>
              <p className="mt-1 text-sm leading-snug text-[#e8dedd]">{imp.reason}</p>
              <p className="mt-1 font-mono text-[11px] text-[#baadab]">
                {imp.residents_affected.toLocaleString()} est. residents affected
                {imp.zero_vehicle_pct != null
                  ? ` · ${Number(imp.zero_vehicle_pct).toFixed(0)}% zero-vehicle households`
                  : ""}
              </p>
            </div>
          </li>
        ))}
        {sim.impacts.every((i) => i.score_drop === 0) && (
          <li className="rounded-md bg-[#190501] p-3 text-sm text-[#baadab]">
            No tract lost Access Score points in this simulation. Try closing a
            route with no parallel service.
          </li>
        )}
      </ol>
    </section>
  );
}
