from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models import AuctionStatus, TriggerType
from app.services import rules

T0 = datetime(2026, 1, 1, 18, 0, tzinfo=UTC)  # "6:00 PM" close time from the spec
NAMES = {1: "A", 2: "B", 3: "C"}


@dataclass
class FakeBid:
    id: int
    supplier_id: int
    total: Decimal
    created_at: datetime


def bid(id, supplier, total, minute):
    return FakeBid(id, supplier, Decimal(total), T0 + timedelta(minutes=minute))


class TestRanking:
    def test_uses_each_suppliers_latest_bid_sorted_by_price(self):
        bids = [bid(1, 1, 500, -30), bid(2, 2, 450, -20), bid(3, 1, 400, -10)]
        assert [b.id for b in rules.rank_latest_bids(bids)] == [3, 2]

    def test_tie_goes_to_earlier_bid(self):
        bids = [bid(1, 1, 400, -10), bid(2, 2, 400, -20)]
        assert [b.supplier_id for b in rules.rank_latest_bids(bids)] == [2, 1]

    def test_empty(self):
        assert rules.rank_latest_bids([]) == []


class TestTriggerWindow:
    # Spec: close 6:00 PM, X = 10 → monitor 5:50–6:00.
    def test_inside(self):
        assert rules.in_trigger_window(T0 - timedelta(minutes=5), T0, 10)

    def test_window_start_is_inclusive(self):
        assert rules.in_trigger_window(T0 - timedelta(minutes=10), T0, 10)

    def test_before_window(self):
        assert not rules.in_trigger_window(T0 - timedelta(minutes=10, seconds=1), T0, 10)

    def test_at_close_is_outside(self):
        assert not rules.in_trigger_window(T0, T0, 10)


class TestExtension:
    def test_adds_y_minutes(self):
        # Spec: 6:00 PM + Y=5 → 6:05 PM
        assert rules.extended_close(T0, 5, T0 + timedelta(hours=1)) == T0 + timedelta(minutes=5)

    def test_capped_at_forced_close(self):
        forced = T0 + timedelta(minutes=3)
        assert rules.extended_close(T0, 5, forced) == forced


class TestTriggers:
    def test_bid_received_always_fires(self):
        assert rules.detect_trigger(TriggerType.BID_RECEIVED, [1, 2], [1, 2], NAMES, 2)

    def test_any_rank_change_fires_on_reorder(self):
        reason = rules.detect_trigger(TriggerType.ANY_RANK_CHANGE, [1, 2], [2, 1], NAMES, 2)
        assert reason and "B L2→L1" in reason and "A L1→L2" in reason

    def test_any_rank_change_fires_when_new_supplier_enters(self):
        reason = rules.detect_trigger(TriggerType.ANY_RANK_CHANGE, [1, 2], [1, 2, 3], NAMES, 3)
        assert reason and "C entered at L3" in reason

    def test_any_rank_change_ignores_same_order(self):
        assert rules.detect_trigger(TriggerType.ANY_RANK_CHANGE, [1, 2], [1, 2], NAMES, 2) is None

    def test_l1_change_fires_only_when_leader_changes(self):
        assert rules.detect_trigger(TriggerType.L1_CHANGE, [1, 2, 3], [1, 3, 2], NAMES, 3) is None
        reason = rules.detect_trigger(TriggerType.L1_CHANGE, [1, 2, 3], [3, 1, 2], NAMES, 3)
        assert reason == "L1 changed from A to C"

    def test_l1_first_bid(self):
        assert rules.detect_trigger(TriggerType.L1_CHANGE, [], [1], NAMES, 1) == "A became the first L1"


class TestStatus:
    start = T0 - timedelta(hours=1)
    forced = T0 + timedelta(minutes=30)

    def test_upcoming_active_closed(self):
        assert rules.compute_status(self.start - timedelta(seconds=1), self.start, T0, self.forced) is AuctionStatus.UPCOMING
        assert rules.compute_status(T0 - timedelta(seconds=1), self.start, T0, self.forced) is AuctionStatus.ACTIVE
        assert rules.compute_status(T0, self.start, T0, self.forced) is AuctionStatus.CLOSED

    def test_force_closed_when_extended_to_forced_close(self):
        assert rules.compute_status(self.forced, self.start, self.forced, self.forced) is AuctionStatus.FORCE_CLOSED
