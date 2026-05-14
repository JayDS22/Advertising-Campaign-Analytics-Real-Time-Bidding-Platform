"""Auction primitives. First-price and Vickrey (second-price) implementations."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AuctionResult:
    winner_id: str | None
    clearing_price: float
    num_bidders: int


class SecondPriceAuction:
    """Vickrey / second-price sealed-bid clearing.

    Winner pays max(second-highest bid, floor) + epsilon, capped at the
    winning bid so we never overcharge on a single-bidder auction.
    """

    def __init__(self, epsilon: float = 0.01):
        self.epsilon = epsilon

    def run(self, bids: dict[str, float], floor: float = 0.0) -> AuctionResult:
        if not bids:
            return AuctionResult(None, 0.0, 0)
        sorted_bids = sorted(bids.items(), key=lambda x: x[1], reverse=True)
        top_id, top_price = sorted_bids[0]
        if top_price < floor:
            return AuctionResult(None, 0.0, len(bids))
        second_price = sorted_bids[1][1] if len(sorted_bids) > 1 else floor
        clearing = max(second_price, floor) + self.epsilon
        clearing = min(clearing, top_price)
        return AuctionResult(top_id, round(clearing, 6), len(bids))


class FirstPriceAuction:
    """First-price sealed-bid clearing. Industry default since 2019."""

    def run(self, bids: dict[str, float], floor: float = 0.0) -> AuctionResult:
        if not bids:
            return AuctionResult(None, 0.0, 0)
        winner_id, top_price = max(bids.items(), key=lambda x: x[1])
        if top_price < floor:
            return AuctionResult(None, 0.0, len(bids))
        return AuctionResult(winner_id, round(top_price, 6), len(bids))
