"use client";

const STEPS: Array<[string, string]> = [
  ["#0f766e", "80–100"],
  ["#14919b", "60–79"],
  ["#967a58", "40–59"],
  ["#cd5c30", "20–39"],
  ["#fa5838", "0–19"],
];

export default function Legend({ scenarioActive }: { scenarioActive: boolean }) {
  return (
    <div
      className="hairline pointer-events-none absolute bottom-3 left-3 z-20 rounded-lg bg-[#200903]/90 p-3 backdrop-blur"
      aria-label="Legend: Access Score"
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#baadab]">
        Access Score{scenarioActive ? " (after closure)" : ""}
      </p>
      <ul className="mt-2 space-y-1">
        {STEPS.map(([color, label]) => (
          <li key={label} className="flex items-center gap-2 text-xs">
            <span className="inline-block h-3 w-3 rounded-sm" style={{ background: color }} />
            <span className="font-mono">{label}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 max-w-[150px] text-[11px] leading-snug text-[#baadab]">
        Higher = more places reachable within 45 min by walk + bus.
      </p>
    </div>
  );
}
