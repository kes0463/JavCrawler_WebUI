import { get } from "./client";

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
