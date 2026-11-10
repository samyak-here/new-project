"""Rule-based scenario parser for POST /api/parse-scenario (BRIEF §9).

No LLM. Matches, in order: a route short/long name, a numeric stop id, then a
stop-name substring. Returns a dict describing the match, or None.
"""
from __future__ import annotations

import re


def parse_scenario(text: str, routes: list[dict], stops: list[dict]) -> dict | None:
    t = " ".join((text or "").strip().lower().split())
    if not t:
        return None
    # Route short name, e.g. "close route 80", "stop route a", "remove brt a"
    for route in sorted(routes, key=lambda r: -len(r.get("short_name") or "")):
        short = (route.get("short_name") or "").strip().lower()
        if short and re.search(rf"\broute\s+{re.escape(short)}\b", t):
            return {"kind": "route", "target_id": route["route_id"],
                    "matched_name": f"Route {route.get('short_name')}"}
        if short and t in (f"close {short}", f"stop {short}", f"remove {short}"):
            return {"kind": "route", "target_id": route["route_id"],
                    "matched_name": f"Route {route.get('short_name')}"}
    # Route long name substring
    for route in routes:
        long_name = (route.get("long_name") or "").strip().lower()
        if long_name and len(long_name) >= 5 and long_name in t:
            return {"kind": "route", "target_id": route["route_id"],
                    "matched_name": route.get("long_name")}
    # Numeric stop id, e.g. "close stop 1234"
    m = re.search(r"\bstop\s+(\d{2,6})\b", t) or re.search(r"\b(\d{4,6})\b", t)
    if m:
        for stop in stops:
            if stop["stop_id"] == m.group(1):
                return {"kind": "stop", "target_id": stop["stop_id"],
                        "matched_name": stop.get("name") or stop["stop_id"]}
    # Stop name substring (longest match wins)
    best = None
    for stop in stops:
        name = (stop.get("name") or "").strip().lower()
        if name and len(name) >= 4 and name in t:
            if best is None or len(name) > len(best.get("name") or ""):
                best = stop
    if best is not None:
        return {"kind": "stop", "target_id": best["stop_id"],
                "matched_name": best.get("name") or best["stop_id"]}
    return None
