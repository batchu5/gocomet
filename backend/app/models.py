import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TriggerType(str, enum.Enum):
    BID_RECEIVED = "BID_RECEIVED"
    ANY_RANK_CHANGE = "ANY_RANK_CHANGE"
    L1_CHANGE = "L1_CHANGE"


class AuctionStatus(str, enum.Enum):
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    FORCE_CLOSED = "FORCE_CLOSED"


class EventType(str, enum.Enum):
    RFQ_CREATED = "RFQ_CREATED"
    BID_PLACED = "BID_PLACED"
    EXTENDED = "EXTENDED"
    EXTENSION_CAPPED = "EXTENSION_CAPPED"
    CLOSED = "CLOSED"
    FORCE_CLOSED = "FORCE_CLOSED"


def _enum(e: type[enum.Enum]) -> Enum:
    # Stored as VARCHAR + CHECK rather than a native PG enum, so adding values needs no ALTER TYPE.
    return Enum(e, native_enum=False, length=32, validate_strings=True)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    email: Mapped[str] = mapped_column(String(200))


class RFQ(Base):
    __tablename__ = "rfqs"
    __table_args__ = (
        CheckConstraint("bid_close_at > bid_start_at", name="ck_close_after_start"),
        CheckConstraint("forced_close_at > bid_close_at", name="ck_forced_after_close"),
        CheckConstraint(
            "current_close_at >= bid_close_at AND current_close_at <= forced_close_at",
            name="ck_current_close_bounds",
        ),
        CheckConstraint("trigger_window_min > 0", name="ck_trigger_window_positive"),
        CheckConstraint("extension_min > 0", name="ck_extension_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    pickup_date: Mapped[date] = mapped_column(Date)
    bid_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Original close time as configured; never changes.
    bid_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Close time after extensions; always within [bid_close_at, forced_close_at].
    current_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forced_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trigger_window_min: Mapped[int] = mapped_column(Integer)
    extension_min: Mapped[int] = mapped_column(Integer)
    trigger_type: Mapped[TriggerType] = mapped_column(_enum(TriggerType))
    # Persisted by the close job; reads recompute it from the timestamps so it is never stale.
    status: Mapped[AuctionStatus] = mapped_column(_enum(AuctionStatus), default=AuctionStatus.UPCOMING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bids: Mapped[list["Bid"]] = relationship(back_populates="rfq", order_by="Bid.created_at")
    events: Mapped[list["AuctionEvent"]] = relationship(back_populates="rfq", order_by="AuctionEvent.id")


class Bid(Base):
    __tablename__ = "bids"
    __table_args__ = (
        CheckConstraint(
            "freight_charges >= 0 AND origin_charges >= 0 AND destination_charges >= 0",
            name="ck_charges_non_negative",
        ),
        Index("ix_bids_rfq_supplier_created", "rfq_id", "supplier_id", "created_at"),
    )
    # Fetch the generated `total` on INSERT so it can be ranked without a second query.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    carrier_name: Mapped[str] = mapped_column(String(120))
    freight_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    origin_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    destination_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("freight_charges + origin_charges + destination_charges", persisted=True)
    )
    transit_time_days: Mapped[int] = mapped_column(Integer)
    quote_valid_until: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    rfq: Mapped[RFQ] = relationship(back_populates="bids")
    supplier: Mapped[Supplier] = relationship(lazy="joined")

    @property
    def supplier_name(self) -> str:
        return self.supplier.name


class AuctionEvent(Base):
    __tablename__ = "auction_events"
    __table_args__ = (Index("ix_events_rfq", "rfq_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"))
    type: Mapped[EventType] = mapped_column(_enum(EventType))
    message: Mapped[str] = mapped_column(Text)
    # Why the auction was extended (only for EXTENDED / EXTENSION_CAPPED).
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    bid_id: Mapped[int | None] = mapped_column(ForeignKey("bids.id"), nullable=True)
    old_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    rfq: Mapped[RFQ] = relationship(back_populates="events")
