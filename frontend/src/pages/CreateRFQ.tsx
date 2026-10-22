import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { toLocalInput } from "../format";
import { TRIGGER_LABELS, type TriggerType } from "../types";

const TRIGGER_HELP: Record<TriggerType, string> = {
  BID_RECEIVED: "Extend whenever any supplier submits a bid inside the trigger window.",
  ANY_RANK_CHANGE: "Extend when any supplier's rank (L1, L2, L3…) changes inside the trigger window.",
  L1_CHANGE: "Extend only when a different supplier becomes the lowest bidder (L1) inside the trigger window.",
};

function defaults() {
  const now = new Date();
  now.setSeconds(0, 0);
  const plus = (min: number) => toLocalInput(new Date(now.getTime() + min * 60_000));
  const pickup = new Date(now.getTime() + 7 * 86_400_000).toISOString().slice(0, 10);
  return {
    reference_id: `RFQ-${now.getTime().toString(36).toUpperCase()}`,
    name: "",
    pickup_date: pickup,
    bid_start_at: plus(0),
    bid_close_at: plus(10),
    forced_close_at: plus(20),
    trigger_window_min: 3,
    extension_min: 2,
    trigger_type: "BID_RECEIVED" as TriggerType,
  };
}

export function CreateRFQ() {
  const [form, setForm] = useState(defaults);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: value }));

  // Mirrors the backend validation so mistakes show up before submitting.
  const problems = useMemo(() => {
    const p: Partial<Record<keyof typeof form, string>> = {};
    const start = Date.parse(form.bid_start_at);
    const close = Date.parse(form.bid_close_at);
    const forced = Date.parse(form.forced_close_at);
    if (close <= start) p.bid_close_at = "Must be later than Bid Start";
    if (close <= Date.now()) p.bid_close_at = "Must be in the future";
    if (forced <= close) p.forced_close_at = "Must be later than Bid Close";
    if (form.trigger_window_min < 1) p.trigger_window_min = "At least 1 minute";
    if (form.extension_min < 1) p.extension_min = "At least 1 minute";
    return p;
  }, [form]);

  const maxExtensions =
    form.extension_min > 0
      ? Math.ceil((Date.parse(form.forced_close_at) - Date.parse(form.bid_close_at)) / (form.extension_min * 60_000))
      : 0;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (Object.keys(problems).length) return;
    setSubmitting(true);
    setError(null);
    try {
      const rfq = await api.createRfq({
        ...form,
        bid_start_at: new Date(form.bid_start_at).toISOString(),
        bid_close_at: new Date(form.bid_close_at).toISOString(),
        forced_close_at: new Date(form.forced_close_at).toISOString(),
      });
      navigate(`/rfqs/${rfq.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Create RFQ</h1>
          <p className="muted">Set up a request for quotation with British auction bidding.</p>
        </div>
      </div>

      <form className="form-grid" onSubmit={submit} noValidate>
        <section className="card">
          <h2>RFQ details</h2>
          <div className="fields">
            <Field label="RFQ name" wide>
              <input required value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Mumbai → Rotterdam, 2×40ft" />
            </Field>
            <Field label="Reference ID">
              <input required value={form.reference_id} onChange={(e) => set("reference_id", e.target.value)} className="mono" />
            </Field>
            <Field label="Pickup / service date">
              <input type="date" required value={form.pickup_date} onChange={(e) => set("pickup_date", e.target.value)} />
            </Field>
          </div>
        </section>

        <section className="card">
          <h2>Bidding schedule</h2>
          <div className="fields">
            <Field label="Bid start">
              <input type="datetime-local" value={form.bid_start_at} onChange={(e) => set("bid_start_at", e.target.value)} />
            </Field>
            <Field label="Bid close" error={problems.bid_close_at}>
              <input type="datetime-local" value={form.bid_close_at} onChange={(e) => set("bid_close_at", e.target.value)} />
            </Field>
            <Field label="Forced bid close" error={problems.forced_close_at} hint="Hard stop: extensions can never go past this.">
              <input type="datetime-local" value={form.forced_close_at} onChange={(e) => set("forced_close_at", e.target.value)} />
            </Field>
          </div>
        </section>

        <section className="card">
          <h2>British auction rules</h2>
          <div className="fields">
            <Field label="Trigger window (X minutes)" error={problems.trigger_window_min} hint="Activity this close to the end can extend the auction.">
              <input type="number" min={1} value={form.trigger_window_min} onChange={(e) => set("trigger_window_min", Number(e.target.value))} />
            </Field>
            <Field label="Extension duration (Y minutes)" error={problems.extension_min} hint="Added to the current close time when triggered.">
              <input type="number" min={1} value={form.extension_min} onChange={(e) => set("extension_min", Number(e.target.value))} />
            </Field>
          </div>
          <div className="radio-cards">
            {(Object.keys(TRIGGER_LABELS) as TriggerType[]).map((t) => (
              <label key={t} className={`radio-card ${form.trigger_type === t ? "selected" : ""}`}>
                <input type="radio" name="trigger" checked={form.trigger_type === t} onChange={() => set("trigger_type", t)} />
                <span className="strong">{TRIGGER_LABELS[t]}</span>
                <span className="muted small">{TRIGGER_HELP[t]}</span>
              </label>
            ))}
          </div>
          {maxExtensions > 0 && !problems.forced_close_at && (
            <p className="muted small">
              Room for up to {maxExtensions} extension{maxExtensions > 1 ? "s" : ""} of {form.extension_min} min before the forced close.
            </p>
          )}
        </section>

        {error && <div className="alert alert-error">{error}</div>}
        <div className="form-actions">
          <button type="button" className="btn" onClick={() => navigate("/")}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting || !form.name || Object.keys(problems).length > 0}>
            {submitting ? "Creating…" : "Create RFQ"}
          </button>
        </div>
      </form>
    </>
  );
}

function Field(props: { label: string; error?: string; hint?: string; wide?: boolean; children: ReactNode }) {
  return (
    <label className={`field ${props.wide ? "field-wide" : ""} ${props.error ? "field-error" : ""}`}>
      <span className="field-label">{props.label}</span>
      {props.children}
      {props.error ? <span className="field-msg">{props.error}</span> : props.hint && <span className="field-hint">{props.hint}</span>}
    </label>
  );
}
