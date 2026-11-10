"use client";
import type { Meta } from "@/lib/api";

interface Props {
  meta: Meta | null;
  open: boolean;
  onClose: () => void;
}

export default function MethodPanel({ meta, open, onClose }: Props) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center bg-black/70 p-4 pt-16"
      role="dialog"
      aria-modal="true"
      aria-label="Method and data sources"
      onClick={onClose}
    >
      <div
        className="hairline max-h-[80vh] w-full max-w-xl overflow-y-auto rounded-lg bg-[#200903] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-display text-xl font-bold">Method &amp; sources</h2>
          <button
            onClick={onClose}
            className="rounded hairline px-2 py-1 text-sm text-[#baadab]"
            aria-label="Close method panel"
          >
            Close
          </button>
        </div>
        {meta ? (
          <>
            <p className="mt-3 text-sm font-medium text-[#fcac9c]">{meta.method.summary}</p>
            <p className="mt-2 text-sm leading-relaxed text-[#e8dedd]">{meta.method.formula}</p>
            {meta.demo_mode && (
              <p className="mt-2 font-mono text-xs text-[#baadab]">
                DEMO MODE — serving a snapshot exported from real ingested data; simulations are
                computed live and held in memory. With DATABASE_URL set, simulations persist in Postgres.
              </p>
            )}
            <h3 className="mt-4 font-mono text-[11px] uppercase tracking-[0.18em] text-[#baadab]">
              Datasets
            </h3>
            <ul className="mt-2 space-y-2">
              {meta.datasets.map((d, i) => (
                <li key={i} className="rounded bg-[#190501] p-3 text-sm">
                  <span className="font-mono text-xs text-[#fcac9c]">{d.source}</span>{" "}
                  <span className="text-[#f7f6ff]">{d.vintage || "vintage unknown"}</span>
                  <span className="mt-1 block font-mono text-[11px] text-[#baadab]">
                    {Object.entries(d.row_counts || {})
                      .map(([k, v]) => `${k}: ${Number(v).toLocaleString()}`)
                      .join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs leading-relaxed text-[#baadab]">
              Sources: Madison Metro GTFS (City of Madison), US Census Bureau ACS 5-year
              (Dane County tracts), OpenStreetMap via Overpass API. No other datasets are used.
            </p>
          </>
        ) : (
          <p className="mt-3 text-sm text-[#baadab]">Method data has not loaded yet.</p>
        )}
      </div>
    </div>
  );
}
