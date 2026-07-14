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
  search_score?: number | null;
  search_source?: string | null;
  user_liked?: boolean;
  watch_later?: boolean;
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
  folder_monitoring_paused?: boolean;
  folder_binding_pending?: boolean;
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
  has_grok_story?: boolean;
  grok_story_running?: boolean;
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
  search_mode?: string | null;
  embeddings_enabled?: boolean | null;
  embedding_channel_used?: boolean | null;
  search_message?: string | null;
}

export interface LibraryStats {
  total: number;
  with_metadata: number;
  with_folder: number;
  without_metadata: number;
}

export interface LibraryGenreItem {
  name: string;
  count: number;
}

export type LibrarySearchMode = "auto" | "keyword" | "hybrid";

export interface LibraryQuery {
  q?: string;
  page?: number;
  per_page?: number;
  sort?: "similarity" | "updated_at" | "release_date" | "product_code" | "title_ko" | "favorite_score";
  order?: "asc" | "desc";
  has_folder?: boolean;
  has_metadata?: boolean;
  /** @deprecated subtitle_filter 사용 */
  has_subtitle?: boolean;
  /** 전체=미지정, has=자막·자체자막, none=자막 없음, ja_only=일본어만 */
  subtitle_filter?: "has" | "none" | "ja_only";
  has_mosaic_removed?: boolean;
  user_liked?: boolean;
  watch_later?: boolean;
  genres?: string[];
  genre_mode?: "and" | "or";
  include_total?: boolean;
  search_mode?: LibrarySearchMode;
}

function toQueryString(params: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === "") continue;
    if (Array.isArray(v)) {
      if (!v.length) continue;
      parts.push(`${k}=${encodeURIComponent(v.join(","))}`);
      continue;
    }
    parts.push(`${k}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? "?" + parts.join("&") : "";
}

export const fetchLibrary = (q: LibraryQuery): Promise<LibraryListResponse> =>
  get(`/api/library${toQueryString(q as Record<string, unknown>)}`);

export const fetchLibrarySearch = (q: LibraryQuery): Promise<LibraryListResponse> => {
  const params: Record<string, unknown> = {
    q: q.q,
    mode: q.search_mode ?? "auto",
    page: q.page,
    per_page: q.per_page,
    sort: q.sort,
    order: q.order,
    has_folder: q.has_folder,
    has_metadata: q.has_metadata,
    has_subtitle: q.has_subtitle,
    subtitle_filter: q.subtitle_filter,
    has_mosaic_removed: q.has_mosaic_removed,
    user_liked: q.user_liked,
    watch_later: q.watch_later,
    genres: q.genres,
    genre_mode: q.genre_mode,
  };
  return get(`/api/library/search${toQueryString(params)}`, 90_000);
};

export const warmupLibraryEmbeddings = (maxBatch = 12): Promise<{
  ok: boolean;
  queued: number;
  message: string;
}> => post(`/api/library/embeddings/warmup?max_batch=${maxBatch}`);

export const backfillLibraryEmbeddings = (batchSize = 4): Promise<{
  ok: boolean;
  queued: number;
  message: string;
}> => post(`/api/library/embeddings/backfill?batch_size=${batchSize}`);

export const startGrokStory = (
  code: string,
  force = false,
): Promise<{ ok: boolean; queued: number; skipped: number; message: string }> =>
  post(`/api/library/${encodeURIComponent(code)}/grok-story?force=${force ? "true" : "false"}`);

export const startGrokStoryBatch = (
  productCodes: string[],
  force = false,
): Promise<{ ok: boolean; queued: number; skipped: number; message: string }> =>
  post("/api/library/grok-story", { product_codes: productCodes, force });

export const toggleLibraryLike = (
  code: string,
): Promise<{ ok: boolean; user_liked: boolean; watch_later: boolean }> =>
  post(`/api/library/${encodeURIComponent(code)}/like`);

export const toggleLibraryWatchLater = (
  code: string,
): Promise<{ ok: boolean; user_liked: boolean; watch_later: boolean }> =>
  post(`/api/library/${encodeURIComponent(code)}/watch-later`);

export const fetchLibraryStats = (): Promise<LibraryStats> =>
  get("/api/library/stats");

export const fetchLibraryGenres = (force = false): Promise<LibraryGenreItem[]> =>
  get(`/api/library/genres${force ? "?force=true" : ""}`);

export function genresFromLibraryItems(items: Iterable<LibraryItem>): LibraryGenreItem[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const raw = item.genres_ko || "";
    for (const part of raw.split(",")) {
      const name = part.trim();
      if (!name) continue;
      counts.set(name, (counts.get(name) || 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ko"))
    .map(([name, count]) => ({ name, count }));
}

let _genreServerFilter: boolean | null = null;
let _genreScanCache: { key: string; items: LibraryItem[] } | null = null;
let _allLibraryItemsCache: LibraryItem[] | null = null;
let _allLibraryLoadPromise: Promise<LibraryItem[]> | null = null;
let _genreIndex: Map<string, LibraryItem[]> | null = null;

const LIBRARY_PAGE_FETCH = 200;
const LIBRARY_FETCH_CONCURRENCY = 8;

export function clearLibraryGenreScanCache(): void {
  _genreScanCache = null;
}

export function clearLibraryClientIndex(): void {
  _genreScanCache = null;
  _allLibraryItemsCache = null;
  _genreIndex = null;
  _allLibraryLoadPromise = null;
}

export function isClientLibraryIndexReady(): boolean {
  return _allLibraryItemsCache !== null && _allLibraryItemsCache.length > 0;
}

export function isClientLibraryIndexLoading(): boolean {
  return _allLibraryLoadPromise !== null;
}

function buildGenreIndex(items: LibraryItem[]): Map<string, LibraryItem[]> {
  const index = new Map<string, LibraryItem[]>();
  for (const item of items) {
    for (const token of itemGenreTokens(item)) {
      const bucket = index.get(token);
      if (bucket) bucket.push(item);
      else index.set(token, [item]);
    }
  }
  return index;
}

function filterIndexedByGenres(
  all: LibraryItem[],
  genres: string[],
  mode: "and" | "or",
): LibraryItem[] {
  const selected = genres.map(g => g.trim()).filter(Boolean);
  if (!selected.length) return all;

  const index = _genreIndex;
  if (!index) {
    return all.filter(item => matchesLibraryGenres(item, selected, mode));
  }

  if (mode === "or") {
    const seen = new Set<string>();
    const out: LibraryItem[] = [];
    for (const g of selected) {
      for (const item of index.get(g) ?? []) {
        const pc = item.product_code.toUpperCase();
        if (seen.has(pc)) continue;
        seen.add(pc);
        out.push(item);
      }
    }
    return out;
  }

  let codes: Set<string> | undefined;
  for (const g of selected) {
    const pageCodes = new Set((index.get(g) ?? []).map(i => i.product_code.toUpperCase()));
    if (!codes) {
      codes = pageCodes;
      continue;
    }
    const next = new Set<string>();
    for (const c of codes) {
      if (pageCodes.has(c)) next.add(c);
    }
    codes = next;
  }
  if (!codes || codes.size === 0) return [];
  const byCode = new Map(all.map(i => [i.product_code.toUpperCase(), i]));
  return [...codes].map(c => byCode.get(c)).filter((i): i is LibraryItem => !!i);
}

async function fetchAllLibraryPages(): Promise<LibraryItem[]> {
  const first = await fetchLibrary({
    page: 1,
    per_page: LIBRARY_PAGE_FETCH,
    sort: "updated_at",
    order: "desc",
    include_total: true,
  });
  const items = [...first.items];
  const pageCount = Math.max(1, Math.ceil(first.total / LIBRARY_PAGE_FETCH));

  for (let start = 2; start <= pageCount; start += LIBRARY_FETCH_CONCURRENCY) {
    const pages = Array.from(
      { length: Math.min(LIBRARY_FETCH_CONCURRENCY, pageCount - start + 1) },
      (_, i) => start + i,
    );
    const chunks = await Promise.all(
      pages.map(page =>
        fetchLibrary({
          page,
          per_page: LIBRARY_PAGE_FETCH,
          sort: "updated_at",
          order: "desc",
          include_total: false,
        }),
      ),
    );
    for (const res of chunks) items.push(...res.items);
  }
  return items;
}

/** 라이브러리 전체 목록 (구 webapi 장르 칩·필터용, 1회 캐시 + 병렬 로드) */
async function loadAllLibraryItems(): Promise<LibraryItem[]> {
  if (_allLibraryItemsCache) return _allLibraryItemsCache;
  if (_allLibraryLoadPromise) return _allLibraryLoadPromise;

  _allLibraryLoadPromise = (async () => {
    const items = await fetchAllLibraryPages();
    _allLibraryItemsCache = items;
    _genreIndex = buildGenreIndex(items);
    return items;
  })();

  try {
    return await _allLibraryLoadPromise;
  } finally {
    _allLibraryLoadPromise = null;
  }
}

/** 구 webapi: 라이브러리 진입 시 백그라운드 인덱스 빌드 */
export function prefetchLibraryClientIndex(): void {
  void probeLibraryGenreFilterSupport().then(supported => {
    if (!supported) void loadAllLibraryItems();
  });
}

/** /api/library/genres 미지원 시 전체 라이브러리에서 장르 집계 */
export async function bootstrapLibraryGenres(): Promise<LibraryGenreItem[]> {
  const items = await loadAllLibraryItems();
  return genresFromLibraryItems(items);
}

export async function fetchLibraryGenresResilient(): Promise<{
  genres: LibraryGenreItem[];
  source: "api" | "bootstrap";
}> {
  try {
    const genres = await fetchLibraryGenres();
    if (genres.length > 0) return { genres, source: "api" };
  } catch {
    /* 구 webapi — /genres 없음 */
  }
  const genres = await bootstrapLibraryGenres();
  return { genres, source: "bootstrap" };
}

export function itemGenreTokens(item: Pick<LibraryItem, "genres_ko">): Set<string> {
  const raw = item.genres_ko || "";
  return new Set(
    raw.split(",").map(s => s.trim()).filter(Boolean),
  );
}

export function matchesLibraryGenres(
  item: LibraryItem,
  genres: string[],
  mode: "and" | "or" = "and",
): boolean {
  if (!genres.length) return true;
  const tokens = itemGenreTokens(item);
  const selected = genres.map(g => g.trim()).filter(Boolean);
  if (mode === "or") return selected.some(g => tokens.has(g));
  return selected.every(g => tokens.has(g));
}

export function resetLibraryGenreFilterProbe(): void {
  _genreServerFilter = null;
}

export async function probeLibraryGenreFilterSupport(): Promise<boolean> {
  if (_genreServerFilter !== null) return _genreServerFilter;
  try {
    await fetchLibraryGenres();
    _genreServerFilter = true;
  } catch {
    _genreServerFilter = false;
  }
  return _genreServerFilter;
}

function libraryListFilterKey(q: LibraryQuery): string {
  const { page: _p, per_page: _n, include_total: _t, ...rest } = q;
  return JSON.stringify(rest);
}

function hasNonGenreListFilters(q: LibraryQuery): boolean {
  return !!(
    (q.q && q.q.trim())
    || q.has_folder !== undefined
    || q.has_metadata !== undefined
    || q.has_subtitle !== undefined
    || q.subtitle_filter !== undefined
    || q.has_mosaic_removed
    || q.user_liked
    || q.watch_later
  );
}

function sortLibraryItems(
  items: LibraryItem[],
  sort: LibraryQuery["sort"] = "updated_at",
  order: LibraryQuery["order"] = "desc",
): LibraryItem[] {
  const key = sort ?? "updated_at";
  const dir = order === "asc" ? 1 : -1;
  const sorted = [...items];
  sorted.sort((a, b) => {
    let cmp = 0;
    switch (key) {
      case "similarity":
        cmp = 0;
        break;
      case "release_date":
        cmp = (a.release_date ?? "").localeCompare(b.release_date ?? "");
        break;
      case "product_code":
        cmp = (a.product_code ?? "").localeCompare(b.product_code ?? "", undefined, { sensitivity: "base" });
        break;
      case "title_ko":
        cmp = (a.title_ko ?? "").localeCompare(b.title_ko ?? "", "ko");
        break;
      case "favorite_score":
        cmp = (Number(a.favorite_score) || 0) - (Number(b.favorite_score) || 0);
        break;
      case "updated_at":
      default:
        cmp = (a.updated_at ?? "").localeCompare(b.updated_at ?? "");
        break;
    }
    return cmp * dir;
  });
  return sorted;
}

async function scanLibraryForGenres(q: LibraryQuery): Promise<LibraryItem[]> {
  const key = libraryListFilterKey(q);
  if (_genreScanCache?.key === key) return _genreScanCache.items;

  const genres = q.genres ?? [];
  const mode = q.genre_mode ?? "and";

  if (!hasNonGenreListFilters(q)) {
    const all = await loadAllLibraryItems();
    const matched = filterIndexedByGenres(all, genres, mode);
    _genreScanCache = { key, items: matched };
    return matched;
  }

  const matched: LibraryItem[] = [];
  for (let page = 1; page <= 150; page += 1) {
    const res = await fetchLibrary({
      ...q,
      genres: undefined,
      genre_mode: undefined,
      page,
      per_page: 200,
      include_total: false,
    });
    for (const item of res.items) {
      if (matchesLibraryGenres(item, genres, mode)) matched.push(item);
    }
    if (res.items.length < 200) break;
  }

  _genreScanCache = { key, items: matched };
  return matched;
}

/** 장르 필터 포함 목록 — 구 webapi는 클라이언트 스캔 폴백 */
export async function fetchLibraryListed(q: LibraryQuery): Promise<LibraryListResponse> {
  const genres = q.genres;
  const hasSearch = !!(q.q || "").trim();
  const fetchBase = hasSearch ? fetchLibrarySearch : fetchLibrary;

  if (!genres?.length) {
    return fetchBase(q);
  }

  const serverSupported = await probeLibraryGenreFilterSupport();
  if (serverSupported) {
    return fetchBase(q);
  }

  const matched = sortLibraryItems(
    await scanLibraryForGenres(q),
    q.sort,
    q.order,
  );
  const perPage = q.per_page ?? 64;
  const page = q.page ?? 1;
  const start = (page - 1) * perPage;

  return {
    total: matched.length,
    page,
    per_page: perPage,
    items: matched.slice(start, start + perPage),
    search_mode: "keyword",
  };
}

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
