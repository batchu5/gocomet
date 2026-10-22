"""place_bid against a real Postgres (row locks and generated columns need it).

Set TEST_DATABASE_URL to a throwaway database, e.g.
    postgresql+asyncpg://postgres:<pw>@localhost:5432/rfq_auction_test
Tables in that database are dropped and recreated for every test.
"""

import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models import RFQ, AuctionEvent, EventType, Supplier, TriggerType
from app.schemas import BidCreate, RFQCreate
from app.services.auction import AuctionError, create_rfq, place_bid, sync_statuses

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")

START = datetime(2026, 1, 1, 17, 0, tzinfo=UTC)
CLOSE = datetime(2026, 1, 1, 18, 0, tzinfo=UTC)


class Clock:
    def __init__(self, t: datetime):
        self.t = t

    def __call__(self) -> datetime:
        return self.t

    def at(self, minutes_before_close: float) -> "Clock":
        self.t = CLOSE - timedelta(minutes=minutes_before_close)
        return self


@pytest_asyncio.fixture
async def sessions():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add_all([Supplier(name=n, email=f"{n}@x.test") for n in ("A", "B", "C")])
        await s.commit()
    yield maker
    await engine.dispose()


async def make_rfq(maker, trigger=TriggerType.BID_RECEIVED, x=10, y=5, forced_after=30) -> int:
    async with maker() as s:
        rfq = await create_rfq(
            s,
            RFQCreate(
                reference_id="RFQ-1",
                name="Test lane",
                pickup_date=date(2026, 1, 10),
                bid_start_at=START,
                bid_close_at=CLOSE,
                forced_close_at=CLOSE + timedelta(minutes=forced_after),
                trigger_window_min=x,
                extension_min=y,
                trigger_type=trigger,
            ),
            clock=lambda: START,
        )
        return rfq.id


async def bid(maker, rfq_id, supplier_id, total, clock):
    data = BidCreate(
        supplier_id=supplier_id,
        carrier_name="Carrier",
        freight_charges=Decimal(total),
        origin_charges=Decimal(0),
        destination_charges=Decimal(0),
        transit_time_days=5,
        quote_valid_until=date(2026, 2, 1),
    )
    async with maker() as s:
        return await place_bid(s, rfq_id, data, clock=clock)


async def close_at(maker, rfq_id) -> datetime:
    async with maker() as s:
        return (await s.get(RFQ, rfq_id)).current_close_at


async def event_types(maker, rfq_id) -> list[EventType]:
    async with maker() as s:
        return list(await s.scalars(select(AuctionEvent.type).where(AuctionEvent.rfq_id == rfq_id).order_by(AuctionEvent.id)))


async def test_bid_outside_window_does_not_extend(sessions):
    rfq = await make_rfq(sessions)
    await bid(sessions, rfq, 1, 1000, Clock(CLOSE).at(30))
    assert await close_at(sessions, rfq) == CLOSE


async def test_bid_in_window_extends_by_y(sessions):
    rfq = await make_rfq(sessions)
    _, events = await bid(sessions, rfq, 1, 1000, Clock(CLOSE).at(5))
    assert await close_at(sessions, rfq) == CLOSE + timedelta(minutes=5)
    assert events[-1].type is EventType.EXTENDED and events[-1].reason


async def test_window_follows_the_extended_close(sessions):
    rfq = await make_rfq(sessions)
    clock = Clock(CLOSE).at(1)
    await bid(sessions, rfq, 1, 1000, clock)  # close → 18:05
    clock.t = CLOSE + timedelta(minutes=2)  # past the original close, inside the new window
    await bid(sessions, rfq, 2, 900, clock)
    assert await close_at(sessions, rfq) == CLOSE + timedelta(minutes=10)


async def test_extension_never_passes_forced_close(sessions):
    rfq = await make_rfq(sessions, forced_after=7)
    clock = Clock(CLOSE).at(1)
    await bid(sessions, rfq, 1, 1000, clock)  # 18:00 → 18:05
    clock.t = CLOSE + timedelta(minutes=4)
    await bid(sessions, rfq, 2, 900, clock)  # 18:05 → capped 18:07
    assert await close_at(sessions, rfq) == CLOSE + timedelta(minutes=7)
    clock.t = CLOSE + timedelta(minutes=6)
    await bid(sessions, rfq, 3, 800, clock)  # already at the cap
    assert await close_at(sessions, rfq) == CLOSE + timedelta(minutes=7)
    assert (await event_types(sessions, rfq))[-1] is EventType.EXTENSION_CAPPED

    clock.t = CLOSE + timedelta(minutes=7)
    with pytest.raises(AuctionError, match="closed"):
        await bid(sessions, rfq, 1, 700, clock)
    async with sessions() as s:
        assert await sync_statuses(s, clock) == [rfq]
    assert (await event_types(sessions, rfq))[-1] is EventType.FORCE_CLOSED


async def test_l1_trigger_ignores_bids_that_do_not_take_the_lead(sessions):
    rfq = await make_rfq(sessions, trigger=TriggerType.L1_CHANGE)
    await bid(sessions, rfq, 1, 1000, Clock(CLOSE).at(30))
    await bid(sessions, rfq, 2, 1100, Clock(CLOSE).at(3))  # becomes L2
    assert await close_at(sessions, rfq) == CLOSE
    await bid(sessions, rfq, 2, 950, Clock(CLOSE).at(2))  # takes L1
    assert await close_at(sessions, rfq) == CLOSE + timedelta(minutes=5)


async def test_rank_change_trigger(sessions):
    rfq = await make_rfq(sessions, trigger=TriggerType.ANY_RANK_CHANGE)
    await bid(sessions, rfq, 1, 1000, Clock(CLOSE).at(30))
    await bid(sessions, rfq, 2, 1100, Clock(CLOSE).at(20))
    await bid(sessions, rfq, 2, 1050, Clock(CLOSE).at(3))  # still L2: no change
    assert await close_at(sessions, rfq) == CLOSE
    await bid(sessions, rfq, 2, 990, Clock(CLOSE).at(2))  # B overtakes A
    assert await close_at(sessions, rfq) == CLOSE + timedelta(minutes=5)


async def test_supplier_must_undercut_own_previous_bid(sessions):
    rfq = await make_rfq(sessions)
    await bid(sessions, rfq, 1, 1000, Clock(CLOSE).at(30))
    with pytest.raises(AuctionError, match="lower than your previous"):
        await bid(sessions, rfq, 1, 1000, Clock(CLOSE).at(29))


async def test_bid_before_start_rejected(sessions):
    rfq = await make_rfq(sessions)
    with pytest.raises(AuctionError, match="not started"):
        await bid(sessions, rfq, 1, 1000, Clock(START - timedelta(minutes=1)))


async def test_concurrent_bids_are_serialised(sessions):
    """Without the row lock both bids would read 18:00 and both write 18:05."""
    rfq = await make_rfq(sessions)
    clock = Clock(CLOSE).at(2)
    await asyncio.gather(
        bid(sessions, rfq, 1, 1000, clock),
        bid(sessions, rfq, 2, 900, clock),
    )
    assert await close_at(sessions, rfq) == CLOSE + timedelta(minutes=10)
