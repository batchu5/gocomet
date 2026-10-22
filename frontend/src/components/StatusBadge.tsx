import type { AuctionStatus } from "../types";

const LABELS: Record<AuctionStatus, string> = {
  UPCOMING: "Upcoming",
  ACTIVE: "Active",
  CLOSED: "Closed",
  FORCE_CLOSED: "Force Closed",
};

export function StatusBadge({ status }: { status: AuctionStatus }) {
  return <span className={`badge badge-${status.toLowerCase()}`}>{LABELS[status]}</span>;
}

/** Status as of `now`, so badges flip the moment the countdown hits zero instead of on the next refetch. */
export function liveStatus(
  r: { status: AuctionStatus; bid_start_at: string; current_close_at: string; forced_close_at: string },
  now: number,
): AuctionStatus {
  if (now < Date.parse(r.bid_start_at)) return "UPCOMING";
  if (now < Date.parse(r.current_close_at)) return "ACTIVE";
  return Date.parse(r.current_close_at) >= Date.parse(r.forced_close_at) ? "FORCE_CLOSED" : "CLOSED";
}
