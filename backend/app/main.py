import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import SessionLocal, init_db
from app.realtime import manager
from app.routers import rfqs, suppliers
from app.services.auction import sync_statuses

log = logging.getLogger(__name__)


async def close_job() -> None:
    """Flip auctions to Active / Closed / Force Closed as their times pass, and notify clients."""
    while True:
        try:
            async with SessionLocal() as session:
                for rfq_id in await sync_statuses(session):
                    await manager.rfq_changed(rfq_id, "status")
        except Exception:
            log.exception("close job tick failed")
        await asyncio.sleep(settings.close_job_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    task = asyncio.create_task(close_job())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="British Auction RFQ", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(rfqs.router)
app.include_router(suppliers.router)


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive; clients don't send anything meaningful
    except WebSocketDisconnect:
        manager.disconnect(ws)
