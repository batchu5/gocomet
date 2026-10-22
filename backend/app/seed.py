"""Seed suppliers and a few demo auctions:  python -m app.seed  [--reset]"""

import asyncio
import sys
from datetime import date, timedelta

from sqlalchemy import select, text

from app.db import SessionLocal, init_db
from app.models import Supplier, TriggerType
from app.schemas import RFQCreate
from app.services.auction import create_rfq, utcnow

SUPPLIERS = [
    ("Blue Dart Logistics", "bids@bluedart.example"),
    ("Maersk Freight", "rfq@maersk.example"),
    ("DHL Global Forwarding", "quotes@dhl.example"),
    ("Delhivery Cargo", "sales@delhivery.example"),
]


async def main(reset: bool) -> None:
    await init_db()
    async with SessionLocal() as session:
        if reset:
            await session.execute(text("TRUNCATE auction_events, bids, rfqs RESTART IDENTITY CASCADE"))
            await session.commit()

        existing = set(await session.scalars(select(Supplier.name)))
        session.add_all(Supplier(name=n, email=e) for n, e in SUPPLIERS if n not in existing)
        await session.commit()

        now = utcnow().replace(microsecond=0)
        stamp = now.strftime("%H%M%S")
        demos = [
            # Short auction for live demos: closes in 4 min, X=2, Y=1, hard stop at 7 min.
            ("Mumbai → Rotterdam (any bid extends)", TriggerType.BID_RECEIVED, 4, 7, 2, 1),
            ("Chennai → Singapore (rank change extends)", TriggerType.ANY_RANK_CHANGE, 5, 10, 2, 2),
            ("Delhi → Dubai (L1 change extends)", TriggerType.L1_CHANGE, 6, 12, 3, 2),
        ]
        for i, (name, trigger, close_in, forced_in, x, y) in enumerate(demos, start=1):
            await create_rfq(
                session,
                RFQCreate(
                    reference_id=f"RFQ-{stamp}-{i}",
                    name=name,
                    pickup_date=date.today() + timedelta(days=7),
                    bid_start_at=now - timedelta(seconds=5),
                    bid_close_at=now + timedelta(minutes=close_in),
                    forced_close_at=now + timedelta(minutes=forced_in),
                    trigger_window_min=x,
                    extension_min=y,
                    trigger_type=trigger,
                ),
            )
    print(f"Seeded {len(SUPPLIERS)} suppliers and {len(demos)} demo auctions.")


if __name__ == "__main__":
    asyncio.run(main(reset="--reset" in sys.argv))
