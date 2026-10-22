import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { liveStatus, StatusBadge } from "../components/StatusBadge";
import { fmtDateTime, fmtDuration, fmtMoney } from "../format";
import { useRfqUpdates, useServerNow } from "../live";
import { TRIGGER_LABELS, type RFQSummary } from "../types";

export function AuctionList() {
  const [items, setItems] = useState<RFQSummary[] | null>(null);
  const [serverTime, setServerTime] = useState<string>();
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const now = useServerNow(serverTime);

  const load = useCallback(() => {
    api
      .listRfqs()
      .then((r) => {
        setItems(r.items);
        setServerTime(r.server_time);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);
  useRfqUpdates(load);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>British Auctions</h1>
          <p className="muted">Live view of every RFQ running as a British auction. Updates automatically.</p>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {items === null ? (
        <div className="card muted">Loading…</div>
      ) : items.length === 0 ? (
        <div className="card empty">
          <p>No auctions yet.</p>
          <Link to="/new" className="btn btn-primary">
            Create the first RFQ
          </Link>
        </div>
      ) : (
        <div className="card table-wrap">
          <table className="table table-hover">
            <thead>
              <tr>
                <th>RFQ</th>
                <th className="num">Current lowest bid</th>
                <th>Current bid close</th>
                <th>Forced close</th>
                <th>Rule</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => {
                const status = liveStatus(r, now);
                const closeMs = Date.parse(r.current_close_at);
                return (
                  <tr key={r.id} onClick={() => navigate(`/rfqs/${r.id}`)}>
                    <td>
                      <div className="strong">{r.name}</div>
                      <div className="muted small mono">{r.reference_id}</div>
                    </td>
                    <td className="num">
                      <div className="strong">{fmtMoney(r.lowest_bid)}</div>
                      <div className="muted small">
                        {r.l1_supplier ? `L1 · ${r.l1_supplier}` : "No bids"}
                        {r.bid_count > 0 && ` · ${r.bid_count} bid${r.bid_count > 1 ? "s" : ""}`}
                      </div>
                    </td>
                    <td>
                      <div>{fmtDateTime(r.current_close_at)}</div>
                      <div className="small">
                        {status === "ACTIVE" && <span className="countdown-inline">ends in {fmtDuration(closeMs - now)}</span>}
                        {status === "UPCOMING" && (
                          <span className="muted">starts in {fmtDuration(Date.parse(r.bid_start_at) - now)}</span>
                        )}
                        {r.extension_count > 0 && (
                          <span className="chip chip-ext">
                            +{r.extension_count} extension{r.extension_count > 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>{fmtDateTime(r.forced_close_at)}</td>
                    <td className="small">
                      <div>{TRIGGER_LABELS[r.trigger_type]}</div>
                      <div className="muted">
                        X = {r.trigger_window_min}m · Y = {r.extension_min}m
                      </div>
                    </td>
                    <td>
                      <StatusBadge status={status} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
