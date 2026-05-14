"""Threaded load generator for the local /api/bid endpoint.

Reports throughput (req/s), success rate, and P50 / P95 / P99 latency.
Defaults assume the API is on http://localhost:8000.

    python scripts/load_test.py --requests 5000 --concurrency 16
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import threading
import time
import urllib.request


SEGMENTS = ["sports_enthusiast", "tech_early_adopter", "music_lover",
            "fashion_forward", "binge_watcher", "foodie", "traveler"]
GEOS = ["US", "GB", "CA", "DE", "JP"]
DEVICES = ["mobile", "desktop", "tablet", "ctv"]


def make_payload() -> bytes:
    return json.dumps({
        "user_id": f"user-{random.randint(0, 9_999_999)}",
        "device_type": random.choice(DEVICES),
        "geo_country": random.choice(GEOS),
        "geo_city": "City",
        "site_domain": "example.com",
        "ad_slot_id": "s1",
        "ad_format": "banner",
        "user_segments": random.sample(SEGMENTS, k=random.randint(1, 3)),
        "floor_price": 0.001,
    }).encode()


def call_once(url: str) -> tuple[float, int]:
    body = make_payload()
    req = urllib.request.Request(url, data=body, method="POST",
                                  headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        resp.read()
        return (time.perf_counter() - t0) * 1000.0, resp.status
    except Exception:
        return (time.perf_counter() - t0) * 1000.0, 0


def worker(url: str, n: int, results: list):
    for _ in range(n):
        results.append(call_once(url))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000/api/bid")
    ap.add_argument("--requests", type=int, default=2000)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    per_thread = args.requests // args.concurrency
    threads = []
    results: list = []
    started = time.perf_counter()
    for _ in range(args.concurrency):
        t = threading.Thread(target=worker,
                             args=(args.url, per_thread, results))
        threads.append(t); t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - started

    latencies = [r[0] for r in results]
    statuses  = [r[1] for r in results]
    ok = sum(1 for s in statuses if s == 200)
    print(json.dumps({
        "requests": len(results),
        "elapsed_seconds": round(elapsed, 2),
        "throughput_rps": round(len(results) / elapsed, 1),
        "success_rate": round(ok / len(results), 4),
        "p50_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(statistics.quantiles(latencies, n=20)[18], 2),
        "p99_ms": round(statistics.quantiles(latencies, n=100)[98], 2),
    }, indent=2))


if __name__ == "__main__":
    main()
