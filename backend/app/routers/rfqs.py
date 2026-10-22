from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.realtime import manager
from app.schemas import BidCreate, BidOut, RFQCreate, RFQDetail, RFQListOut
from app.services import auction, views

router = APIRouter(prefix="/api/rfqs", tags=["rfqs"])


@router.get("", response_model=RFQListOut)
async def list_rfqs(session: AsyncSession = Depends(get_session)):
    now = auction.utcnow()
    return RFQListOut(items=await views.list_rfqs(session, now), server_time=now)


@router.post("", response_model=RFQDetail, status_code=status.HTTP_201_CREATED)
async def create_rfq(data: RFQCreate, session: AsyncSession = Depends(get_session)):
    try:
        rfq = await auction.create_rfq(session, data)
    except auction.AuctionError as e:
        raise HTTPException(e.status_code, e.message) from e
    await manager.rfq_changed(rfq.id, "created")
    return await views.get_rfq_detail(session, rfq.id, auction.utcnow())


@router.get("/{rfq_id}", response_model=RFQDetail)
async def get_rfq(rfq_id: int, session: AsyncSession = Depends(get_session)):
    detail = await views.get_rfq_detail(session, rfq_id, auction.utcnow())
    if detail is None:
        raise HTTPException(404, "RFQ not found")
    return detail


@router.post("/{rfq_id}/bids", response_model=BidOut, status_code=status.HTTP_201_CREATED)
async def place_bid(rfq_id: int, data: BidCreate, session: AsyncSession = Depends(get_session)):
    try:
        bid, events = await auction.place_bid(session, rfq_id, data)
    except auction.AuctionError as e:
        raise HTTPException(e.status_code, e.message) from e
    await manager.rfq_changed(rfq_id, "extended" if len(events) > 1 else "bid")
    return BidOut.model_validate(bid)
