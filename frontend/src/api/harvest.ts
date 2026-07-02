import { get, post, del, patch, WS_BASE } from "./client";

export interface HarvestItem {
  id: string;
  target: string;
  product_code: string | null;
  status: "pending" | "running" | "done" | "error";
  progress: number;
  message: string;
  kind?: "code" | "folder" | "video_path";
  is_path?: boolean;
  force_rebuild?: boolean;
  staged?: boolean;
}

export interface HarvestQueueResponse {
  items: HarvestItem[];
  running: boolean;
  grok_enabled?: boolean;
  planned?: number;
  warnings?: string[];
  folder_path?: string;
}

export interface LogEntry {
  id: string;
  level: "info" | "warn" | "error" | "debug" | "success";
  text: string;
  ts: string;
}

export function isPlausibleHarvestCode(code: string): boolean {
  const s = code.trim().toUpperCase().replace(/_/g, "-").replace(/\s/g, "-");
  if (s.length < 4) return false;
  if (!/^[A-Z0-9][A-Z0-9-]*$/.test(s)) return false;
  if (!/\d{2,}/.test(s)) return false;
  return true;
}

export function parseHarvestCodes(raw: string): string[] {
  return raw
    .split(/[\s,\n]+/)
    .map(c => c.trim().toUpperCase())
    .filter(Boolean);
}

export const fetchQueue = (): Promise<HarvestQueueResponse> =>
  get("/api/harvest/queue");

export const addToQueue = (
  codes: string[],
  autoStart = false,
): Promise<HarvestQueueResponse> =>
  post("/api/harvest/add", { codes, auto_start: autoStart });

export const recrawlProducts = (
  codes: string[],
  force = true,
): Promise<HarvestQueueResponse> =>
  post("/api/harvest/recrawl", { codes, force });

export const queueFolder = (path: string): Promise<HarvestQueueResponse> =>
  post("/api/harvest/queue-folder", { path });

export const queueFolders = (paths: string[]): Promise<HarvestQueueResponse> =>
  post("/api/harvest/queue-folders", { paths });

export const queueParentFolder = (path: string): Promise<HarvestQueueResponse> =>
  post("/api/harvest/queue-parent-folder", { path });

export interface PickFoldersResponse {
  paths: string[];
  cancelled: boolean;
}

/** Electron IPC 또는 webapi 네이티브 대화상자 (다중 폴더). */
export async function pickFoldersDialog(): Promise<string[]> {
  const bridge = window.javstory;
  if (bridge?.pickFolders) {
    const paths = await bridge.pickFolders();
    return paths;
  }
  const res = await post<PickFoldersResponse>("/api/harvest/pick-folders", {});
  const paths = res.cancelled ? [] : res.paths;
  return paths;
}

export const startStaged = (): Promise<{ ok: boolean; queued: number }> =>
  post("/api/harvest/start-staged");

export const removeFromQueue = (id: string): Promise<{ ok: boolean }> =>
  del(`/api/harvest/queue/${id}`);

export const cancelHarvestItem = (id: string): Promise<{ ok: boolean }> =>
  post(`/api/harvest/cancel/${id}`);

export const startHarvest = (): Promise<{ ok: boolean; queued: number }> =>
  post("/api/harvest/start");

export const clearFinished = (): Promise<{ ok: boolean; removed: number }> =>
  post("/api/harvest/clear-finished");

export const clearQueue = (): Promise<{ ok: boolean }> =>
  post("/api/harvest/clear");

export const patchHarvestSettings = (
  grokEnabled: boolean,
): Promise<HarvestQueueResponse> =>
  patch("/api/harvest/settings", { grok_enabled: grokEnabled });

export const harvestFavorites = (
  mode: "selected" | "all" | "missing",
  codes?: string[],
): Promise<{ ok: boolean; queued: number; mode: string }> =>
  post("/api/harvest/favorites", { mode, codes });

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

export type HarvestWsEvent =
  | { type: "state"; running: boolean; items: HarvestItem[]; grok_enabled?: boolean }
  | { type: "queue_started" }
  | { type: "queue_finished" }
  | { type: "item_started"; id: string }
  | { type: "item_done"; id: string; message?: string; progress?: number }
  | { type: "item_error"; id: string; message: string }
  | { type: "item_cancelled"; id: string }
  | { type: "progress"; id: string; sku: string; message: string; progress: number }
  | { type: "log"; level: string; text: string; ts: string }
  | { type: "folder_planned"; path: string; count: number; warnings: string[] }
  | { type: "harvest_alert"; product_code: string; message: string }
  | { type: "favorites_started"; mode: string; total: number }
  | { type: "favorites_progress"; current: number; total: number; product_code: string; status: string; progress: number; message: string }
  | { type: "favorites_finished"; updated: number; zero: number; failed: number; total: number }
  | { type: "favorites_error"; message: string };
