from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Supplier
from app.schemas import SupplierOut

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("", response_model=list[SupplierOut])
async def list_suppliers(session: AsyncSession = Depends(get_session)):
    return list(await session.scalars(select(Supplier).order_by(Supplier.name)))
