import { useEffect, useRef, useState } from "react";

type Listener = (msg: { type: string; rfq_id: number; reason: string }) => void;

const listeners = new Set<Listener>();
let socket: WebSocket | null = null;

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${proto}://${location.host}/ws`);
  socket.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    listeners.forEach((l) => l(msg));
  };
  // Reconnect after a backend restart.
  socket.onclose = () => setTimeout(connect, 2000);
}

/** Calls `onChange` whenever the backend reports a change (to `rfqId`, or to any RFQ if omitted). */
export function useRfqUpdates(onChange: () => void, rfqId?: number) {
  const cb = useRef(onChange);
  cb.current = onChange;
  useEffect(() => {
    if (!socket) connect();
    const listener: Listener = (msg) => {
      if (rfqId === undefined || msg.rfq_id === rfqId) cb.current();
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, [rfqId]);
}

/** Current time on the server's clock, ticking every second. */
export function useServerNow(serverTime: string | undefined): number {
  const [offset, setOffset] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (serverTime) setOffset(new Date(serverTime).getTime() - Date.now());
  }, [serverTime]);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now + offset;
}
