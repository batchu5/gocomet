from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import AuctionStatus, EventType, TriggerType


def _as_utc(value: datetime) -> datetime:
    # Naive datetimes are treated as UTC so comparisons against timestamptz columns are safe.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class RFQCreate(BaseModel):
    reference_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    pickup_date: date
    bid_start_at: datetime
    bid_close_at: datetime
    forced_close_at: datetime
    trigger_window_min: int = Field(gt=0, le=24 * 60)
    extension_min: int = Field(gt=0, le=24 * 60)
    trigger_type: TriggerType

    @field_validator("bid_start_at", "bid_close_at", "forced_close_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _as_utc(v)

    @model_validator(mode="after")
    def _check_times(self) -> "RFQCreate":
        if self.bid_close_at <= self.bid_start_at:
            raise ValueError("Bid Close Time must be later than Bid Start Time")
        if self.forced_close_at <= self.bid_close_at:
            raise ValueError("Forced Bid Close Time must be later than Bid Close Time")
        return self


class BidCreate(BaseModel):
    supplier_id: int
    carrier_name: str = Field(min_length=1, max_length=120)
    freight_charges: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    origin_charges: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    destination_charges: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    transit_time_days: int = Field(gt=0, le=365)
    quote_valid_until: date

    @property
    def total(self) -> Decimal:
        return self.freight_charges + self.origin_charges + self.destination_charges


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


class BidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    supplier_name: str
    carrier_name: str
    freight_charges: Decimal
    origin_charges: Decimal
    destination_charges: Decimal
    total: Decimal
    transit_time_days: int
    quote_valid_until: date
    created_at: datetime


class RankedBidOut(BidOut):
    rank: int  # 1 = L1
    bid_count: int  # how many times this supplier has bid on the RFQ


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: EventType
    message: str
    reason: str | None
    old_close_at: datetime | None
    new_close_at: datetime | None
    created_at: datetime


class RFQSummary(BaseModel):
    id: int
    reference_id: str
    name: str
    lowest_bid: Decimal | None
    l1_supplier: str | None
    bid_count: int
    extension_count: int
    bid_start_at: datetime
    bid_close_at: datetime
    current_close_at: datetime
    forced_close_at: datetime
    trigger_window_min: int
    extension_min: int
    trigger_type: TriggerType
    status: AuctionStatus


class RFQDetail(RFQSummary):
    pickup_date: date
    created_at: datetime
    ranking: list[RankedBidOut]
    bids: list[BidOut]  # every bid ever placed, sorted by price
    events: list[EventOut]  # newest first
    server_time: datetime  # lets the client correct its countdown for clock skew


class RFQListOut(BaseModel):
    items: list[RFQSummary]
    server_time: datetime
