import { get, post, patch, del, API_BASE } from "./client";

export const HARVEST_FAILED_TITLE_MARKER = "(수집 실패/정보 없음)";

export function hasRealLibraryMetadata(
  item: Pick<LibraryItem, "title_ko" | "title_ja" | "analysis_status">,
): boolean {
  const ko = (item.title_ko || "").trim();
  const ja = (item.title_ja || "").trim();
  if (!ko && !ja) return false;
  if (item.analysis_status === "FAILED_CRAWL") return false;
  if (ko.includes(HARVEST_FAILED_TITLE_MARKER)) return false;
  return true;
}

export interface LibraryItem {
  id: number;
  product_code: string;
  title_ko: string | null;
  title_ja: string | null;
  actors_ko: string | null;
  actors_ja: string | null;
  genres_ko: string | null;
  maker_ko: string | null;
  cover_image_local_path: string | null;
  release_date: string | null;
  folder_path: string | null;
  is_hardcoded: boolean;
  is_mopa: boolean;
  analysis_status?: string | null;
  metadata_manual?: boolean;
  updated_at: string | null;
  scene_count?: number;
  favorite_score?: number;
  has_subtitle?: boolean;
  has_hardcoded_subtitle?: boolean;
  has_mosaic_removed?: boolean;
  has_preview?: boolean;
  preview_media?: "mp4" | "webp" | null;
}

export interface SceneSummary {
  scene_id: string;
  time_range: string;
  scene_label: string;
  scene_summary: string;
  tone: string;
  key_tags?: string[];
}

export interface LibraryItemDetail extends LibraryItem {
  synopsis_ko: string | null;
  synopsis_ja: string | null;
  title_en: string | null;
  actors_romaji: string | null;
  genres_ja: string | null;
  maker_ja: string | null;
  cover_image_url: string | null;
  overall_summary?: string | null;
  scenes?: SceneSummary[];
  scenes_source?: "grok" | "canonical" | null;
  snapshot_count?: number;
}

export interface LibraryItemUpdate {
  title_ko?: string | null;
  title_ja?: string | null;
  title_en?: string | null;
  synopsis_ko?: string | null;
  synopsis_ja?: string | null;
  synopsis_en?: string | null;
  actors_ko?: string | null;
  actors_ja?: string | null;
  actors_romaji?: string | null;
  actors_en?: string | null;
  genres_ko?: string | null;
  genres_ja?: string | null;
  maker_ko?: string | null;
  maker_ja?: string | null;
  maker_en?: string | null;
  release_date?: string | null;
}

export interface LibraryListResponse {
  total: number;
  page: number;
  per_page: number;
  items: LibraryItem[];
}

export interface LibraryStats {
  total: number;
  with_metadata: number;
  with_folder: number;
  without_metadata: number;
}

export interface LibraryQuery {
  q?: string;
  page?: number;
  per_page?: number;
  sort?: "updated_at" | "release_date" | "product_code" | "title_ko" | "favorite_score";
  order?: "asc" | "desc";
  has_folder?: boolean;
  has_metadata?: boolean;
  has_subtitle?: boolean;
  has_mosaic_removed?: boolean;
  include_total?: boolean;
}

function toQueryString(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (!entries.length) return "";
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
}

export const fetchLibrary = (q: LibraryQuery): Promise<LibraryListResponse> =>
  get(`/api/library${toQueryString(q as Record<string, unknown>)}`);

export const fetchLibraryStats = (): Promise<LibraryStats> =>
  get("/api/library/stats");

export const fetchLibraryDetail = (code: string): Promise<LibraryItemDetail> =>
  get(`/api/library/${code}`);

export const updateLibraryItem = (
  code: string,
  body: LibraryItemUpdate,
): Promise<LibraryItemDetail> =>
  patch(`/api/library/${code}`, body);

export const openLibraryFolder = (code: string): Promise<{ ok: boolean; path?: string }> =>
  post(`/api/library/${code}/open-folder`);

export const bindLibraryFolder = (
  code: string,
  folderPath: string,
  force = false,
): Promise<{ ok: boolean; path?: string; detail?: LibraryItemDetail }> =>
  post(`/api/library/${code}/folder`, { folder_path: folderPath, force });

export const clearLibraryFolder = (
  code: string,
): Promise<{ ok: boolean; detail?: LibraryItemDetail }> =>
  del(`/api/library/${code}/folder`);

export const coverUrl = (code: string, cacheBust?: string | number) => {
  const base = `${API_BASE}/api/library/cover/${encodeURIComponent(code)}`;
  return cacheBust != null ? `${base}?t=${encodeURIComponent(String(cacheBust))}` : base;
};

export const previewUrl = (code: string, cacheBust?: string | number) => {
  const base = `${API_BASE}/api/library/preview/${encodeURIComponent(code)}`;
  return cacheBust != null ? `${base}?t=${encodeURIComponent(String(cacheBust))}` : base;
};

export const snapshotUrl = (code: string, index: number) =>
  `${API_BASE}/api/library/${encodeURIComponent(code)}/snapshots/${index}`;

export const uploadLibraryCover = async (code: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/library/${encodeURIComponent(code)}/cover`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<{
    ok: boolean;
    path?: string;
    detail?: LibraryItemDetail;
  }>;
};

export const fetchLibraryCoverFromUrl = (code: string) =>
  post<{ ok: boolean; path?: string; detail?: LibraryItemDetail }>(
    `/api/library/${encodeURIComponent(code)}/cover/fetch`,
  );
