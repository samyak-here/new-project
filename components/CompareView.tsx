"use client";
import { useState } from "react";
import { api, type CompareSummary, type Simulation } from "@/lib/api";

interface Props {
  saved: Simulation[];
}

export default function CompareView({ saved }: Props) {
  const [aId, setAId] = useState("");
  const [bId, setBId] = useState("");
  const [result, setResult] = useState<{ a: CompareSummary; b: CompareSummary } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (saved.length < 2) {
    return (
      <section aria-label="Compare scenarios" className="hairline rounded-lg bg-[#260b03] p-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#baadab]">
          Compare
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-[#baadab]">
          Run two simulations and label them (for example “Scenario A” and
          “Scenario B”) to compare their damage side by side.
        </p>
      </section>
    );
  }

  const run = async () => {
    const a = aId || saved[0].id;
    const b = bId || saved[1].id;
    if (a === b) return setError("Pick two different scenarios.");
    setError(null);
    setLoading(true);
    try {
      setResult(await api.compare(a, b));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const labelOf = (s: Simulation) => s.label || `${s.target_name} (${s.kind})`;
  const rows: Array<[string, (s: CompareSummary) => string]> = [
    ["Closure", (s) => s.target_name || s.target_id],
    ["Est. residents affected", (s) => s.total_residents_affected.toLocaleString()],
    ["Avg Access Score drop", (s) => s.avg_score_drop.toFixed(1)],
    ["Worst-hit tract", (s) => (s.worst_tract ? `${s.worst_tract.name} (−${s.worst_tract.score_drop})` : "—")],
    ["Best fix recovery", (s) => (s.best_fix ? `+${s.best_fix.recovered_score.toFixed(0)} pts` : "none found")],
  ];

  return (
    <section aria-label="Compare scenarios" className="hairline rounded-lg bg-[#260b03] p-4">
      <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#baadab]">
        Compare
      </h2>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {([[aId, setAId], [bId, setBId]] as const).map(([val, set], i) => (
          <select
            key={i}
            value={val}
            onChange={(e) => set(e.target.value)}
            aria-label={i === 0 ? "Scenario A" : "Scenario B"}
            className="w-full rounded bg-[#190501] hairline px-2 py-2 text-sm text-[#f7f6ff]"
          >
            {saved.map((s) => (
              <option key={s.id} value={s.id}>{labelOf(s)}</option>
            ))}
          </select>
        ))}
      </div>
      <button
        onClick={run}
        disabled={loading}
        className="ember-button mt-3 w-full rounded px-3 py-2 text-sm font-medium text-[#f7f6ff] disabled:opacity-50"
      >
        {loading ? "Comparing…" : "Compare scenarios"}
      </button>
      {error && <p role="alert" className="mt-2 text-sm text-[#fcac9c]">{error}</p>}
      {result && (
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="hairline-b text-left font-mono text-[11px] uppercase tracking-wider text-[#baadab]">
              <th className="py-1 pr-2 font-normal">Measure</th>
              <th className="py-1 pr-2 font-normal">{result.a.label || "A"}</th>
              <th className="py-1 font-normal">{result.b.label || "B"}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, fmt]) => (
              <tr key={label} className="hairline-b last:border-0">
                <td className="py-1.5 pr-2 text-[#baadab]">{label}</td>
                <td className="py-1.5 pr-2 font-mono text-[13px]">{fmt(result.a)}</td>
                <td className="py-1.5 font-mono text-[13px]">{fmt(result.b)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
