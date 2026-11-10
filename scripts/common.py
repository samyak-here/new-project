"""Shared helpers for Isthmus ingest scripts.

Rules (BRIEF §13): never fabricate data. Every fetch is retried exactly once;
on failure the caller logs the exact error + URL and exits non-zero.
Scripts use only the Python standard library for parsing, plus psycopg when
DATABASE_URL is set and a DB load is requested.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Isthmus/0.1 (student project; contact: github.com/samyak-here/new-project)"}


def load_dotenv() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def database_url() -> str | None:
    load_dotenv()
    return os.environ.get("DATABASE_URL") or None


def fetch_bytes(url: str, data: bytes | None = None, timeout: int = 180) -> bytes:
    """GET (or POST when data is given) with exactly one retry, per BRIEF §13."""
    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001 - we log and re-raise verbatim
            last_err = exc
            print(f"[fetch] attempt {attempt} failed for {url}: {exc!r}", file=sys.stderr)
            if attempt == 1:
                time.sleep(2)
    raise RuntimeError(f"fetch failed after retry: {url}: {last_err!r}")


def fetch_json(url: str, data: bytes | None = None, timeout: int = 180) -> dict | list:
    return json.loads(fetch_bytes(url, data=data, timeout=timeout).decode("utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    print(f"[out] wrote {path} ({path.stat().st_size:,} bytes)")


def connect_db():
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set; use --dry-run or set DATABASE_URL (see .env.example)")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for DB loads: pip install 'psycopg[binary]'") from exc
    return psycopg.connect(url)
