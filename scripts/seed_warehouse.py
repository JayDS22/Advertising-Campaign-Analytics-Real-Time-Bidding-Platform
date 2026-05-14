"""Bulk-load 10k synthetic events through the full pipeline (producer ->
aggregator -> warehouse -> bandit) so analysts can prod the data offline.
"""
from __future__ import annotations

from src.api.seed_data import make_demo_campaigns, synthetic_event_stream
from src.api.state import PlatformState


def main():
    state = PlatformState.get()
    campaigns = list(state.engine.campaigns.values()) or make_demo_campaigns()
    events = synthetic_event_stream(campaigns, n=10_000)
    for e in events:
        state.emit(e)
    print("seeded events:", len(events))
    print("warehouse rows:", {t: len(rs)
                              for t, rs in state.warehouse._tables.items()})


if __name__ == "__main__":
    main()
