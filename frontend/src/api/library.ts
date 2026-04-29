import { get, API_BASE } from "./client";

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
  updated_at: string | null;
}

export interface LibraryItemDetail extends LibraryItem {
  synopsis_ko: string | null;
  synopsis_ja: string | null;
  title_en: string | null;
  actors_romaji: string | null;
  genres_ja: string | null;
  maker_ja: string | null;
  cover_image_url: string | null;
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
  sort?: "updated_at" | "release_date" | "product_code" | "title_ko";
  order?: "asc" | "desc";
  has_folder?: boolean;
  has_metadata?: boolean;
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

export const coverUrl = (code: string) =>
  `${API_BASE}/api/library/cover/${code}`;
