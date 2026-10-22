export type TriggerType = "BID_RECEIVED" | "ANY_RANK_CHANGE" | "L1_CHANGE";
export type AuctionStatus = "UPCOMING" | "ACTIVE" | "CLOSED" | "FORCE_CLOSED";
export type EventType =
  | "RFQ_CREATED"
  | "BID_PLACED"
  | "EXTENDED"
  | "EXTENSION_CAPPED"
  | "CLOSED"
  | "FORCE_CLOSED";

export interface Supplier {
  id: number;
  name: string;
  email: string;
}

export interface Bid {
  id: number;
  supplier_id: number;
  supplier_name: string;
  carrier_name: string;
  freight_charges: string;
  origin_charges: string;
  destination_charges: string;
  total: string;
  transit_time_days: number;
  quote_valid_until: string;
  created_at: string;
}

export interface RankedBid extends Bid {
  rank: number;
  bid_count: number;
}

export interface AuctionEvent {
  id: number;
  type: EventType;
  message: string;
  reason: string | null;
  old_close_at: string | null;
  new_close_at: string | null;
  created_at: string;
}

export interface RFQSummary {
  id: number;
  reference_id: string;
  name: string;
  lowest_bid: string | null;
  l1_supplier: string | null;
  bid_count: number;
  extension_count: number;
  bid_start_at: string;
  bid_close_at: string;
  current_close_at: string;
  forced_close_at: string;
  trigger_window_min: number;
  extension_min: number;
  trigger_type: TriggerType;
  status: AuctionStatus;
}

export interface RFQDetail extends RFQSummary {
  pickup_date: string;
  created_at: string;
  ranking: RankedBid[];
  bids: Bid[];
  events: AuctionEvent[];
  server_time: string;
}

export const TRIGGER_LABELS: Record<TriggerType, string> = {
  BID_RECEIVED: "Any bid in last X min",
  ANY_RANK_CHANGE: "Any rank change in last X min",
  L1_CHANGE: "L1 change in last X min",
};
