import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { liveStatus, StatusBadge } from "../components/StatusBadge";
import { fmtDate, fmtDateTime, fmtDuration, fmtMoney, fmtTime } from "../format";
import { useRfqUpdates, useServerNow } from "../live";
import { TRIGGER_LABELS, type AuctionEvent, type RFQDetail, type Supplier } from "../types";

export function AuctionDetail() {
  const id = Number(useParams().id);
  const [rfq, setRfq] = useState<RFQDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const now = useServerNow(rfq?.server_time);

  const load = useCallback(() => {
    api
      .getRfq(id)
      .then((r) => {
        setRfq(r);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(load, [load]);
  useRfqUpdates(load, id);

  if (error && !rfq) return <div className="alert alert-error">{error}</div>;
  if (!rfq) return <div className="card muted">Loading…</div>;

  const status = liveStatus(rfq, now);
  const closeMs = Date.parse(rfq.current_close_at);
  const inWindow = status === "ACTIVE" && closeMs - now <= rfq.trigger_window_min * 60_000;

  return (
    <>
      <Link to="/" className="back">
        ← All auctions
      </Link>
      <div className="page-head">
        <div>
          <div className="muted small mono">{rfq.reference_id}</div>
          <h1>{rfq.name}</h1>
          <p className="muted">
            Pickup {fmtDate(rfq.pickup_date)} · {rfq.bid_count} bid{rfq.bid_count === 1 ? "" : "s"} from {rfq.ranking.length} supplier
            {rfq.ranking.length === 1 ? "" : "s"}
          </p>
        </div>
        <StatusBadge status={status} />
      </div>

      <section className={`card hero ${inWindow ? "hero-hot" : ""}`}>
        <div className="hero-stats">
          <Stat label={status === "UPCOMING" ? "Starts in" : status === "ACTIVE" ? "Closes in" : "Closed at"}>
            <span className="big mono">
              {status === "UPCOMING"
                ? fmtDuration(Date.parse(rfq.bid_start_at) - now)
                : status === "ACTIVE"
                  ? fmtDuration(closeMs - now)
                  : fmtTime(rfq.current_close_at)}
            </span>
            {inWindow && <span className="chip chip-hot">In trigger window</span>}
          </Stat>
          <Stat label="Current lowest (L1)">
            <span className="big">{fmtMoney(rfq.lowest_bid)}</span>
            <span className="muted small">{rfq.l1_supplier ?? "No bids yet"}</span>
          </Stat>
          <Stat label="Current close">
            <span className="mid">{fmtTime(rfq.current_close_at)}</span>
            <span className="muted small">
              {rfq.extension_count > 0 ? `originally ${fmtTime(rfq.bid_close_at)} · +${rfq.extension_count} ext.` : "not extended"}
            </span>
          </Stat>
          <Stat label="Forced close">
            <span className="mid">{fmtTime(rfq.forced_close_at)}</span>
            <span className="muted small">hard stop</span>
          </Stat>
        </div>
        <Timeline rfq={rfq} now={now} />
      </section>

      <div className="detail-grid">
        <div className="stack">
          <section className="card">
            <h2>Supplier ranking</h2>
            {rfq.ranking.length === 0 ? (
              <p className="muted">No bids yet.</p>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Supplier / carrier</th>
                      <th className="num">Freight</th>
                      <th className="num">Origin</th>
                      <th className="num">Destination</th>
                      <th className="num">Total</th>
                      <th>Transit</th>
                      <th>Valid until</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rfq.ranking.map((b) => (
                      <tr key={b.id} className={b.rank === 1 ? "row-l1" : ""}>
                        <td>
                          <span className={`rank rank-${Math.min(b.rank, 4)}`}>L{b.rank}</span>
                        </td>
                        <td>
                          <div className="strong">{b.supplier_name}</div>
                          <div className="muted small">
                            {b.carrier_name} · {b.bid_count} bid{b.bid_count > 1 ? "s" : ""} · last {fmtTime(b.created_at)}
                          </div>
                        </td>
                        <td className="num">{fmtMoney(b.freight_charges)}</td>
                        <td className="num">{fmtMoney(b.origin_charges)}</td>
                        <td className="num">{fmtMoney(b.destination_charges)}</td>
                        <td className="num strong">{fmtMoney(b.total)}</td>
                        <td>{b.transit_time_days} d</td>
                        <td>{fmtDate(b.quote_valid_until)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card">
            <h2>All bids (by price)</h2>
            {rfq.bids.length === 0 ? (
              <p className="muted">No bids yet.</p>
            ) : (
              <div className="table-wrap">
                <table className="table table-compact">
                  <thead>
                    <tr>
                      <th>Supplier</th>
                      <th>Carrier</th>
                      <th className="num">Total</th>
                      <th>Transit</th>
                      <th>Placed at</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rfq.bids.map((b) => {
                      const isLatest = rfq.ranking.some((r) => r.id === b.id);
                      return (
                        <tr key={b.id} className={isLatest ? "" : "superseded"}>
                          <td>{b.supplier_name}</td>
                          <td>{b.carrier_name}</td>
                          <td className="num">{fmtMoney(b.total)}</td>
                          <td>{b.transit_time_days} d</td>
                          <td>
                            {fmtTime(b.created_at)}
                            {!isLatest && <span className="muted small"> · superseded</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card">
            <h2>Activity log</h2>
            <ol className="log">
              {rfq.events.map((e) => (
                <LogItem key={e.id} event={e} rfq={rfq} />
              ))}
            </ol>
          </section>
        </div>

        <div className="stack">
          <BidForm rfq={rfq} active={status === "ACTIVE"} onPlaced={load} />
          <section className="card">
            <h2>Auction configuration</h2>
            <dl className="kv">
              <dt>Trigger window (X)</dt>
              <dd>{rfq.trigger_window_min} min</dd>
              <dt>Extension (Y)</dt>
              <dd>{rfq.extension_min} min</dd>
              <dt>Extends on</dt>
              <dd>{TRIGGER_LABELS[rfq.trigger_type]}</dd>
              <dt>Bid start</dt>
              <dd>{fmtDateTime(rfq.bid_start_at)}</dd>
              <dt>Original close</dt>
              <dd>{fmtDateTime(rfq.bid_close_at)}</dd>
              <dt>Current close</dt>
              <dd>{fmtDateTime(rfq.current_close_at)}</dd>
              <dt>Forced close</dt>
              <dd>{fmtDateTime(rfq.forced_close_at)}</dd>
            </dl>
          </section>
        </div>
      </div>
    </>
  );
}

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      {children}
    </div>
  );
}

/** Start → forced close, with the original close, current close, trigger window and "now" marked. */
function Timeline({ rfq, now }: { rfq: RFQDetail; now: number }) {
  const start = Date.parse(rfq.bid_start_at);
  const end = Date.parse(rfq.forced_close_at);
  const pct = (t: number) => `${Math.max(0, Math.min(100, ((t - start) / (end - start)) * 100))}%`;
  const close = Date.parse(rfq.current_close_at);
  const windowStart = close - rfq.trigger_window_min * 60_000;

  return (
    <div className="timeline" aria-label="Auction timeline">
      <div className="tl-track">
        <div className="tl-open" style={{ width: pct(close) }} />
        <div className="tl-window" style={{ left: pct(windowStart), width: `calc(${pct(close)} - ${pct(windowStart)})` }} />
        <div className="tl-mark tl-orig" style={{ left: pct(Date.parse(rfq.bid_close_at)) }} title="Original close" />
        <div className="tl-mark tl-close" style={{ left: pct(close) }} title="Current close" />
        {now >= start && now <= end && <div className="tl-now" style={{ left: pct(now) }} title="Now" />}
      </div>
      <div className="tl-legend small muted">
        <span>{fmtTime(rfq.bid_start_at)} start</span>
        <span>
          <i className="sw sw-window" /> trigger window <i className="sw sw-orig" /> original close <i className="sw sw-close" /> current close
          <i className="sw sw-now" /> now
        </span>
        <span>{fmtTime(rfq.forced_close_at)} forced</span>
      </div>
    </div>
  );
}

const EVENT_ICON: Record<AuctionEvent["type"], string> = {
  RFQ_CREATED: "✦",
  BID_PLACED: "₹",
  EXTENDED: "⏱",
  EXTENSION_CAPPED: "⛔",
  CLOSED: "■",
  FORCE_CLOSED: "■",
};

/** The API's messages carry UTC times; rebuild the timed ones in the viewer's local time. */
function eventText(e: AuctionEvent, rfq: RFQDetail): string {
  switch (e.type) {
    case "RFQ_CREATED":
      return `RFQ created. Bidding ${fmtTime(rfq.bid_start_at)} → ${fmtTime(rfq.bid_close_at)}, forced close ${fmtTime(rfq.forced_close_at)}`;
    case "EXTENDED":
      return `Close time extended ${fmtTime(e.old_close_at!)} → ${fmtTime(e.new_close_at!)}${
        Date.parse(e.new_close_at!) === Date.parse(rfq.forced_close_at) ?" (capped at forced close)" : ""
      }`;
    case "CLOSED":
      return "Auction closed";
    case "FORCE_CLOSED":
      return "Auction force closed: forced close time reached";
    default:
      return e.message;
  }
}

function LogItem({ event: e, rfq }: { event: AuctionEvent; rfq: RFQDetail }) {
  return (
    <li className={`log-item log-${e.type.toLowerCase()}`}>
      <span className="log-icon">{EVENT_ICON[e.type]}</span>
      <div>
        <div>{eventText(e, rfq)}</div>
        {e.reason && <div className="log-reason">Reason: {e.reason}</div>}
      </div>
      <time className="muted small mono">{fmtTime(e.created_at)}</time>
    </li>
  );
}

function BidForm({ rfq, active, onPlaced }: { rfq: RFQDetail; active: boolean; onPlaced: () => void }) {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplierId, setSupplierId] = useState<number | "">("");
  const [form, setForm] = useState({
    carrier_name: "",
    freight_charges: "",
    origin_charges: "0",
    destination_charges: "0",
    transit_time_days: "7",
    quote_valid_until: new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10),
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  useEffect(() => {
    api.listSuppliers().then((s) => {
      setSuppliers(s);
      if (s.length) setSupplierId((cur) => (cur === "" ? s[0].id : cur));
    });
  }, []);

  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const total = ["freight_charges", "origin_charges", "destination_charges"].reduce(
    (sum, k) => sum + (Number(form[k as keyof typeof form]) || 0),
    0,
  );
  const mine = rfq.ranking.find((b) => b.supplier_id === supplierId);
  const l1 = rfq.ranking[0];

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (supplierId === "") return;
    setBusy(true);
    setMsg(null);
    try {
      await api.placeBid(rfq.id, {
        supplier_id: supplierId,
        ...form,
        freight_charges: form.freight_charges || "0",
        origin_charges: form.origin_charges || "0",
        destination_charges: form.destination_charges || "0",
        transit_time_days: Number(form.transit_time_days),
      });
      setMsg({ kind: "ok", text: `Bid of ${fmtMoney(total)} submitted.` });
      onPlaced();
    } catch (err) {
      setMsg({ kind: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Submit a quote</h2>
      {!active && <p className="muted small">Bidding is not open right now.</p>}
      <form onSubmit={submit} className="bid-form">
        <label className="field">
          <span className="field-label">Bidding as supplier</span>
          <select value={supplierId} onChange={(e) => setSupplierId(Number(e.target.value))}>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <span className="field-hint">
            {mine ? `Currently L${mine.rank} at ${fmtMoney(mine.total)} — new bid must be lower.` : "No bid yet from this supplier."}
            {l1 && (!mine || mine.rank !== 1) && ` L1 is ${fmtMoney(l1.total)}.`}
          </span>
        </label>
        <label className="field">
          <span className="field-label">Carrier name</span>
          <input required value={form.carrier_name} onChange={(e) => set("carrier_name", e.target.value)} />
        </label>
        <div className="fields-3">
          <label className="field">
            <span className="field-label">Freight</span>
            <input type="number" min={0} step="0.01" required value={form.freight_charges} onChange={(e) => set("freight_charges", e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">Origin</span>
            <input type="number" min={0} step="0.01" value={form.origin_charges} onChange={(e) => set("origin_charges", e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">Destination</span>
            <input type="number" min={0} step="0.01" value={form.destination_charges} onChange={(e) => set("destination_charges", e.target.value)} />
          </label>
        </div>
        <div className="fields-2">
          <label className="field">
            <span className="field-label">Transit time (days)</span>
            <input type="number" min={1} required value={form.transit_time_days} onChange={(e) => set("transit_time_days", e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">Quote valid until</span>
            <input type="date" required value={form.quote_valid_until} onChange={(e) => set("quote_valid_until", e.target.value)} />
          </label>
        </div>
        <div className="bid-total">
          <span className="muted">Total</span>
          <span className="mid">{fmtMoney(total)}</span>
        </div>
        {msg && <div className={`alert alert-${msg.kind}`}>{msg.text}</div>}
        <button className="btn btn-primary btn-block" disabled={!active || busy || !form.carrier_name || !form.freight_charges}>
          {busy ? "Submitting…" : "Submit bid"}
        </button>
      </form>
    </section>
  );
}
