import { get, post, del, WS_BASE } from "./client";

const PROCESSING_TIMEOUT_MS = 120_000;

export type ProcessingKind = "stt" | "subtitle";

export interface ProcessingQueueItem {
  id: string;
  target: string;
  product_code: string | null;
  status: "pending" | "running" | "done" | "error";
  progress: number;
  message: string;
  file_name: string;
}

export interface ProcessingQueueSection {
  items: ProcessingQueueItem[];
  running: boolean;
}

export interface ProcessingQueueResponse {
  stt: ProcessingQueueSection;
  subtitle: ProcessingQueueSection;
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

export function parseProcessingPaths(raw: string): string[] {
  return raw
    .split(/[\n\r]+/)
    .map(p => p.trim())
    .filter(Boolean);
}

export const fetchProcessingQueue = (): Promise<ProcessingQueueResponse> =>
  get("/api/processing/queue", PROCESSING_TIMEOUT_MS);

export const addToProcessingQueue = (
  kind: ProcessingKind,
  paths: string[],
): Promise<ProcessingQueueResponse> =>
  post("/api/processing/add", { kind, paths }, PROCESSING_TIMEOUT_MS);

export const addProductsToProcessingQueue = (
  kind: ProcessingKind,
  productCodes: string[],
): Promise<ProcessingQueueResponse> =>
  post("/api/processing/products", { kind, product_codes: productCodes }, PROCESSING_TIMEOUT_MS);

export const addProcessingFolder = (
  kind: ProcessingKind,
  folderPath: string,
): Promise<ProcessingQueueResponse> =>
  post("/api/processing/folder", { kind, folder_path: folderPath }, PROCESSING_TIMEOUT_MS);

export const removeProcessingItem = (
  kind: ProcessingKind,
  id: string,
): Promise<{ ok: boolean }> =>
  del(`/api/processing/item/${kind}/${id}`, PROCESSING_TIMEOUT_MS);

export const startProcessingQueue = (
  kind: ProcessingKind,
): Promise<{ ok: boolean; queued: number }> =>
  post("/api/processing/start", { kind }, PROCESSING_TIMEOUT_MS);

export const cancelProcessingQueue = (
  kind: ProcessingKind,
): Promise<{ ok: boolean }> =>
  post("/api/processing/cancel", { kind }, PROCESSING_TIMEOUT_MS);

export const clearProcessingFinished = (
  kind: ProcessingKind,
): Promise<{ ok: boolean; removed: number }> =>
  post("/api/processing/clear-finished", { kind }, PROCESSING_TIMEOUT_MS);

export const clearProcessingQueue = (
  kind: ProcessingKind,
): Promise<{ ok: boolean; removed: number }> =>
  post("/api/processing/clear", { kind }, PROCESSING_TIMEOUT_MS);

export function createProcessingWS(
  onMessage: (event: ProcessingWsEvent) => void,
  onClose?: () => void,
): WebSocket {
  const ws = new WebSocket(`${WS_BASE}/api/processing/ws`);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data) as ProcessingWsEvent);
    } catch {
      /* ignore malformed */
    }
  };
  ws.onclose = onClose ?? null;
  return ws;
}

export interface SentenceLineEntry {
  id: string;
  kind: ProcessingKind;
  lang: "ja" | "ko";
  text: string;
  start?: number;
  end?: number;
  index?: number;
  ts: string;
}

export type ProcessingWsEvent =
  | { type: "state"; stt: ProcessingQueueSection; subtitle: ProcessingQueueSection }
  | { type: "queue_started"; kind: ProcessingKind }
  | { type: "queue_finished"; kind: ProcessingKind }
  | { type: "item_started"; kind: ProcessingKind; id: string }
  | { type: "item_done"; kind: ProcessingKind; id: string; message?: string; progress?: number }
  | { type: "item_error"; kind: ProcessingKind; id: string; message: string }
  | { type: "item_cancelled"; kind: ProcessingKind; id: string }
  | { type: "progress"; kind: ProcessingKind; id: string; message: string; progress: number }
  | { type: "log"; kind: ProcessingKind; level: string; text: string; ts: string }
  | {
      type: "content_line";
      kind: ProcessingKind;
      id: string;
      lang: "ja" | "ko";
      text: string;
      start?: number;
      end?: number;
      index?: number;
      ts: string;
    }
  | { type: "content_clear"; kind: ProcessingKind; id: string };

export function toQueueRow(item: ProcessingQueueItem) {
  return {
    id: item.id,
    label: item.file_name || item.product_code || item.target,
    status: item.status,
    progress: item.progress,
    message: item.message,
  };
}
