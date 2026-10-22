"""Pure British-auction rules. No database access here, so every rule can be unit-tested directly."""

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol

from app.models import AuctionStatus, TriggerType


class BidLike(Protocol):
    id: int
    supplier_id: int
    total: Decimal
    created_at: datetime


def rank_latest_bids[B: BidLike](bids: Iterable[B]) -> list[B]:
    """Each supplier's latest bid, best first.

    Ranking is by total ascending; on a tie the bid placed earlier wins.
    """
    latest: dict[int, B] = {}
    for bid in bids:
        current = latest.get(bid.supplier_id)
        if current is None or (bid.created_at, bid.id) > (current.created_at, current.id):
            latest[bid.supplier_id] = bid
    return sorted(latest.values(), key=lambda b: (b.total, b.created_at, b.id))


def in_trigger_window(now: datetime, close_at: datetime, window_min: int) -> bool:
    return close_at - timedelta(minutes=window_min) <= now < close_at


def detect_trigger(
    trigger_type: TriggerType,
    before: list[int],
    after: list[int],
    names: Mapping[int, str],
    bidder_id: int,
) -> str | None:
    """Return a human-readable reason if this bid fires the configured trigger, else None.

    `before` / `after` are supplier ids in rank order (L1 first) around the new bid.
    """
    bidder = names.get(bidder_id, f"Supplier #{bidder_id}")

    if trigger_type is TriggerType.BID_RECEIVED:
        return f"Bid received from {bidder} inside the trigger window"

    if trigger_type is TriggerType.ANY_RANK_CHANGE:
        if before == after:
            return None
        before_rank = {sid: i for i, sid in enumerate(before)}
        moved = [
            f"{names.get(sid, sid)} L{before_rank[sid] + 1}→L{i + 1}"
            if sid in before_rank
            else f"{names.get(sid, sid)} entered at L{i + 1}"
            for i, sid in enumerate(after)
            if before_rank.get(sid) != i
        ]
        return "Supplier ranking changed: " + ", ".join(moved)

    if trigger_type is TriggerType.L1_CHANGE:
        old_l1 = before[0] if before else None
        new_l1 = after[0] if after else None
        if old_l1 == new_l1:
            return None
        if old_l1 is None:
            return f"{names.get(new_l1, new_l1)} became the first L1"
        return f"L1 changed from {names.get(old_l1, old_l1)} to {names.get(new_l1, new_l1)}"

    raise ValueError(f"Unknown trigger type: {trigger_type}")


def extended_close(current_close: datetime, extension_min: int, forced_close: datetime) -> datetime:
    """New close time after an extension, never past the forced close."""
    return min(current_close + timedelta(minutes=extension_min), forced_close)


def compute_status(
    now: datetime, bid_start_at: datetime, current_close_at: datetime, forced_close_at: datetime
) -> AuctionStatus:
    if now < bid_start_at:
        return AuctionStatus.UPCOMING
    if now < current_close_at:
        return AuctionStatus.ACTIVE
    # Ran all the way to the hard stop: extensions were cut off by the forced close.
    if current_close_at >= forced_close_at:
        return AuctionStatus.FORCE_CLOSED
    return AuctionStatus.CLOSED
