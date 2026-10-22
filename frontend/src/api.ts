import type { RFQDetail, RFQSummary, Supplier, TriggerType } from "./types";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(formatDetail(body?.detail) ?? `Request failed (${res.status})`);
  }
  return res.json();
}

// FastAPI returns either a string or a list of pydantic errors.
function formatDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((l: unknown) => l !== "body").join(".") : "";
        const msg = String(d.msg ?? "").replace(/^Value error, /, "");
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  return null;
}

export interface RFQInput {
  reference_id: string;
  name: string;
  pickup_date: string;
  bid_start_at: string;
  bid_close_at: string;
  forced_close_at: string;
  trigger_window_min: number;
  extension_min: number;
  trigger_type: TriggerType;
}

export interface BidInput {
  supplier_id: number;
  carrier_name: string;
  freight_charges: string;
  origin_charges: string;
  destination_charges: string;
  transit_time_days: number;
  quote_valid_until: string;
}

export const api = {
  listRfqs: () => request<{ items: RFQSummary[]; server_time: string }>("/api/rfqs"),
  getRfq: (id: number) => request<RFQDetail>(`/api/rfqs/${id}`),
  createRfq: (body: RFQInput) => request<RFQDetail>("/api/rfqs", { method: "POST", body: JSON.stringify(body) }),
  placeBid: (rfqId: number, body: BidInput) =>
    request(`/api/rfqs/${rfqId}/bids`, { method: "POST", body: JSON.stringify(body) }),
  listSuppliers: () => request<Supplier[]>("/api/suppliers"),
};
