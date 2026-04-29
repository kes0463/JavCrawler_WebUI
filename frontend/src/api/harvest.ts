import { get, post, del, WS_BASE } from "./client";

export interface HarvestItem {
  id: string;
  target: string;
  product_code: string | null;
  status: "pending" | "running" | "done" | "error";
  progress: number;
  message: string;
}

export interface HarvestQueueResponse {
  items: HarvestItem[];
  running: boolean;
}

export const fetchQueue = (): Promise<HarvestQueueResponse> =>
  get("/api/harvest/queue");

export const addToQueue = (codes: string[]): Promise<HarvestQueueResponse> =>
  post("/api/harvest/add", { codes });

export const removeFromQueue = (id: string): Promise<{ ok: boolean }> =>
  del(`/api/harvest/queue/${id}`);

export const startHarvest = (): Promise<{ ok: boolean; queued: number }> =>
  post("/api/harvest/start");

export const clearQueue = (): Promise<{ ok: boolean }> =>
  post("/api/harvest/clear");

export function createHarvestWS(
  onMessage: (event: HarvestWsEvent) => void,
  onClose?: () => void,
): WebSocket {
  const ws = new WebSocket(`${WS_BASE}/api/harvest/ws`);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data) as HarvestWsEvent);
    } catch {}
  };
  ws.onclose = onClose ?? null;
  return ws;
}

// ── WebSocket 이벤트 타입 ────────────────────────────────────────

export type HarvestWsEvent =
  | { type: "state"; running: boolean; items: HarvestItem[] }
  | { type: "queue_started" }
  | { type: "queue_finished" }
  | { type: "item_started"; id: string }
  | { type: "item_done"; id: string }
  | { type: "item_error"; id: string; message: string }
  | { type: "progress"; id: string; sku: string; message: string; progress: number };
