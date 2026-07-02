import { get, post, del } from "./client";

export interface LibraryStatsBlock {
  total: number;
  with_metadata: number;
  with_folder: number;
  without_metadata: number;
}

export interface WatchStatsBlock {
  total: number;
  completed: number;
  completion_rate: number;
  avg_rating: number;
  rated_count: number;
  watched_count: number;
  total_watch_hours: number;
}

export interface DashboardSummary {
  library: LibraryStatsBlock;
  watch: WatchStatsBlock;
  pending_count: number;
  mosaic_queue_count: number;
  metadata_match_rate: number;
}

export interface PendingItem {
  product_code: string;
  title: string;
}

export interface SystemMetrics {
  gpu_name: string;
  gpu_usage_percent: number;
  gpu_total_gb: number;
  gpu_used_gb: number;
  cpu_percent: number;
  mem_percent: number;
  mem_used_gb: number;
  mem_total_gb: number;
  cpu_model: string;
}

export interface PreviewQueueItem {
  id: string;
  product_code: string;
  status: string;
  progress: number;
  message: string;
  attempts: number;
  activity: "active" | "stalled" | "waiting" | "idle";
  started_at_ms: number;
  updated_at_ms: number;
  elapsed_sec: number;
  segment_index: number;
  segment_total: number;
  source_position_sec: number;
  source_duration_sec: number;
}

function formatMediaTimestamp(sec: number): string {
  const total = Math.max(0, Math.floor(sec));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function formatPreviewSegmentProgress(item: PreviewQueueItem): string | null {
  if (item.message?.includes("구간")) return item.message;
  if (
    item.segment_total > 0
    && item.segment_index > 0
    && item.source_duration_sec > 0
  ) {
    return `구간 ${item.segment_index}/${item.segment_total} · 원본 ${formatMediaTimestamp(item.source_position_sec)} / ${formatMediaTimestamp(item.source_duration_sec)}`;
  }
  return null;
}

export interface PreviewQueueStatus {
  pending_count: number;
  running_count: number;
  queued_count: number;
  completed_total: number;
  failed_total: number;
  worker_count: number;
  processing_state: "active" | "idle" | "backlogged" | "stalled";
  last_activity_at_ms: number;
  seconds_since_activity: number;
  stall_threshold_sec: number;
  paused: boolean;
  harvest_paused: boolean;
  user_paused: boolean;
  items: PreviewQueueItem[];
}

export const fetchDashboardSummary = (): Promise<DashboardSummary> =>
  get("/api/dashboard/summary");

export const fetchPendingItems = (limit = 200): Promise<PendingItem[]> =>
  get(`/api/dashboard/pending?limit=${limit}`);

export const fetchSystemMetrics = (): Promise<SystemMetrics> =>
  get("/api/dashboard/system");

export const fetchPreviewQueue = (limit = 40): Promise<PreviewQueueStatus> =>
  get(`/api/dashboard/preview-queue?limit=${limit}`);

export const clearPreviewFinished = (): Promise<{ ok: boolean; removed: number }> =>
  del("/api/dashboard/preview-queue/finished");

export const pauseAllPreview = (): Promise<{ ok: boolean; paused: boolean }> =>
  post("/api/dashboard/preview-queue/pause-all");

export const resumeAllPreview = (): Promise<{ ok: boolean; resumed: number }> =>
  post("/api/dashboard/preview-queue/resume-all");

export const removePreviewJob = (jobId: string): Promise<{ ok: boolean }> =>
  del(`/api/dashboard/preview-queue/${encodeURIComponent(jobId)}`);

export const pausePreviewJob = (jobId: string): Promise<{ ok: boolean }> =>
  post(`/api/dashboard/preview-queue/${encodeURIComponent(jobId)}/pause`);

export const resumePreviewJob = (jobId: string): Promise<{ ok: boolean }> =>
  post(`/api/dashboard/preview-queue/${encodeURIComponent(jobId)}/resume`);
