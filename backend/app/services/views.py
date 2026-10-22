"""Read-side helpers that turn ORM rows into API responses."""

from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import RFQ, AuctionEvent, Bid, EventType
from app.schemas import BidOut, EventOut, RankedBidOut, RFQDetail, RFQSummary
from app.services import rules


def _bid_out(bid: Bid) -> dict:
    return BidOut.model_validate(bid).model_dump()


def _summary_fields(rfq: RFQ, extension_count: int, now: datetime) -> dict:
    ranking = rules.rank_latest_bids(rfq.bids)
    l1 = ranking[0] if ranking else None
    return dict(
        id=rfq.id,
        reference_id=rfq.reference_id,
        name=rfq.name,
        lowest_bid=l1.total if l1 else None,
        l1_supplier=l1.supplier.name if l1 else None,
        bid_count=len(rfq.bids),
        extension_count=extension_count,
        bid_start_at=rfq.bid_start_at,
        bid_close_at=rfq.bid_close_at,
        current_close_at=rfq.current_close_at,
        forced_close_at=rfq.forced_close_at,
        trigger_window_min=rfq.trigger_window_min,
        extension_min=rfq.extension_min,
        trigger_type=rfq.trigger_type,
        # Derived from timestamps rather than the stored column, so it is right even between job ticks.
        status=rules.compute_status(now, rfq.bid_start_at, rfq.current_close_at, rfq.forced_close_at),
    )


async def list_rfqs(session: AsyncSession, now: datetime) -> list[RFQSummary]:
    rfqs = list(await session.scalars(select(RFQ).options(selectinload(RFQ.bids)).order_by(RFQ.id.desc())))
    ext_counts = dict(
        (
            await session.execute(
                select(AuctionEvent.rfq_id, func.count())
                .where(AuctionEvent.type == EventType.EXTENDED)
                .group_by(AuctionEvent.rfq_id)
            )
        ).all()
    )
    return [RFQSummary(**_summary_fields(r, ext_counts.get(r.id, 0), now)) for r in rfqs]


async def get_rfq_detail(session: AsyncSession, rfq_id: int, now: datetime) -> RFQDetail | None:
    rfq = await session.scalar(
        select(RFQ)
        .where(RFQ.id == rfq_id)
        .options(selectinload(RFQ.bids), selectinload(RFQ.events))
        .execution_options(populate_existing=True)
    )
    if rfq is None:
        return None

    bid_counts = Counter(b.supplier_id for b in rfq.bids)
    ranking = [
        RankedBidOut(**_bid_out(b), rank=i + 1, bid_count=bid_counts[b.supplier_id])
        for i, b in enumerate(rules.rank_latest_bids(rfq.bids))
    ]
    all_bids = [BidOut(**_bid_out(b)) for b in sorted(rfq.bids, key=lambda b: (b.total, b.created_at, b.id))]
    extension_count = sum(1 for e in rfq.events if e.type is EventType.EXTENDED)

    return RFQDetail(
        **_summary_fields(rfq, extension_count, now),
        pickup_date=rfq.pickup_date,
        created_at=rfq.created_at,
        ranking=ranking,
        bids=all_bids,
        events=[EventOut.model_validate(e) for e in reversed(rfq.events)],
        server_time=now,
    )
