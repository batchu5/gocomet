"""Auction operations that touch the database: creating RFQs, placing bids, closing auctions."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RFQ, AuctionEvent, AuctionStatus, Bid, EventType, Supplier
from app.schemas import BidCreate, RFQCreate
from app.services import rules

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


class AuctionError(Exception):
    """A request that breaks an auction rule. Carries the HTTP status to return."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _fmt_time(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%H:%M:%S UTC")


async def create_rfq(session: AsyncSession, data: RFQCreate, clock: Clock = utcnow) -> RFQ:
    now = clock()
    if data.bid_close_at <= now:
        raise AuctionError("Bid Close Time must be in the future", 422)
    if await session.scalar(select(RFQ.id).where(RFQ.reference_id == data.reference_id)):
        raise AuctionError(f"An RFQ with reference '{data.reference_id}' already exists", 409)

    rfq = RFQ(
        **data.model_dump(),
        current_close_at=data.bid_close_at,
        status=rules.compute_status(now, data.bid_start_at, data.bid_close_at, data.forced_close_at),
    )
    session.add(rfq)
    await session.flush()
    session.add(
        AuctionEvent(
            rfq_id=rfq.id,
            type=EventType.RFQ_CREATED,
            message=(
                f"RFQ created. Bidding {_fmt_time(data.bid_start_at)} → {_fmt_time(data.bid_close_at)}, "
                f"forced close {_fmt_time(data.forced_close_at)}"
            ),
            created_at=now,
        )
    )
    await session.commit()
    return rfq


async def place_bid(
    session: AsyncSession, rfq_id: int, data: BidCreate, clock: Clock = utcnow
) -> tuple[Bid, list[AuctionEvent]]:
    """Validate and record a bid, extending the auction if the configured trigger fires.

    Everything happens in one transaction with the RFQ row locked, so concurrent bids are
    applied one at a time and each sees the close time left by the previous one.
    """
    rfq = await session.scalar(
        select(RFQ).where(RFQ.id == rfq_id).with_for_update().execution_options(populate_existing=True)
    )
    if rfq is None:
        raise AuctionError("RFQ not found", 404)
    supplier = await session.get(Supplier, data.supplier_id)
    if supplier is None:
        raise AuctionError("Supplier not found", 404)

    # Read the clock only after the lock is held, so the window check uses the latest close time.
    now = clock()
    if now < rfq.bid_start_at:
        raise AuctionError("Bidding has not started yet")
    if now >= rfq.current_close_at:
        raise AuctionError("Bidding is closed for this RFQ")

    existing = list(await session.scalars(select(Bid).where(Bid.rfq_id == rfq_id)))
    before = rules.rank_latest_bids(existing)
    own_previous = next((b for b in before if b.supplier_id == supplier.id), None)
    if own_previous is not None and data.total >= own_previous.total:
        raise AuctionError(
            f"Your new total ({data.total}) must be lower than your previous bid ({own_previous.total})"
        )

    bid = Bid(rfq_id=rfq.id, supplier=supplier, created_at=now, **data.model_dump())
    session.add(bid)
    await session.flush()

    after = rules.rank_latest_bids([*existing, bid])
    names = {b.supplier_id: b.supplier.name for b in after}
    new_rank = next(i for i, b in enumerate(after) if b.id == bid.id) + 1

    events = [
        AuctionEvent(
            rfq_id=rfq.id,
            type=EventType.BID_PLACED,
            message=f"{supplier.name} ({bid.carrier_name}) bid {bid.total} — now L{new_rank}",
            bid_id=bid.id,
            created_at=now,
        )
    ]

    if rules.in_trigger_window(now, rfq.current_close_at, rfq.trigger_window_min):
        reason = rules.detect_trigger(
            rfq.trigger_type,
            [b.supplier_id for b in before],
            [b.supplier_id for b in after],
            names,
            supplier.id,
        )
        if reason:
            old_close = rfq.current_close_at
            new_close = rules.extended_close(old_close, rfq.extension_min, rfq.forced_close_at)
            if new_close > old_close:
                rfq.current_close_at = new_close
                capped = " (capped at forced close)" if new_close == rfq.forced_close_at else ""
                events.append(
                    AuctionEvent(
                        rfq_id=rfq.id,
                        type=EventType.EXTENDED,
                        message=f"Close time extended {_fmt_time(old_close)} → {_fmt_time(new_close)}{capped}",
                        reason=reason,
                        bid_id=bid.id,
                        old_close_at=old_close,
                        new_close_at=new_close,
                        created_at=now,
                    )
                )
            else:
                events.append(
                    AuctionEvent(
                        rfq_id=rfq.id,
                        type=EventType.EXTENSION_CAPPED,
                        message="Extension skipped: auction already ends at the forced close time",
                        reason=reason,
                        bid_id=bid.id,
                        old_close_at=old_close,
                        new_close_at=old_close,
                        created_at=now,
                    )
                )

    session.add_all(events)
    await session.commit()
    return bid, events


async def sync_statuses(session: AsyncSession, clock: Clock = utcnow) -> list[int]:
    """Persist status changes for auctions that have started or ended. Returns changed RFQ ids."""
    now = clock()
    open_rfqs = await session.scalars(
        select(RFQ)
        .where(RFQ.status.in_([AuctionStatus.UPCOMING, AuctionStatus.ACTIVE]))
        .with_for_update(skip_locked=True)
    )
    changed: list[int] = []
    for rfq in open_rfqs:
        status = rules.compute_status(now, rfq.bid_start_at, rfq.current_close_at, rfq.forced_close_at)
        if status == rfq.status:
            continue
        rfq.status = status
        changed.append(rfq.id)
        if status in (AuctionStatus.CLOSED, AuctionStatus.FORCE_CLOSED):
            forced = status is AuctionStatus.FORCE_CLOSED
            session.add(
                AuctionEvent(
                    rfq_id=rfq.id,
                    type=EventType.FORCE_CLOSED if forced else EventType.CLOSED,
                    message=(
                        f"Auction force closed at {_fmt_time(rfq.current_close_at)} (forced close time reached)"
                        if forced
                        else f"Auction closed at {_fmt_time(rfq.current_close_at)}"
                    ),
                    created_at=rfq.current_close_at,
                )
            )
    await session.commit()
    return changed
