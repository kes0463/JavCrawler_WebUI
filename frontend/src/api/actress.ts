import { get, post, patch, del, API_BASE } from "./client";

export type ActressSort = "name" | "works" | "favorite" | "score" | "recent";

export interface ActressListItem {
  id: number;
  name_ko: string;
  name_ja: string;
  profile_image_url: string;
  user_score: number;
  is_favorite: boolean;
  genres: string;
  work_count: number;
}

export interface ActressAlias {
  alias_id: number;
  alias_name: string;
  alias_type: string;
  is_primary: boolean;
}

export interface ActressGalleryImage {
  image_id?: number;
  image_url: string;
  thumb_url: string;
  image_url_raw?: string;
  sort_order?: number;
}

export interface ActressProfile {
  id: number;
  name_ja: string;
  name_ko: string;
  name_en: string;
  romaji: string;
  profile_image_url: string;
  genres: string;
  user_score: number;
  profile_text: string;
  birth_date: string;
  height: number;
  bust: number;
  waist: number;
  hip: number;
  cup_size: string;
  debut_date: string;
  debut_date_raw: string;
  agency: string;
  is_favorite: boolean;
  favorite_intensity: number;
  memo: string;
  work_count: number;
  aliases: ActressAlias[];
  gallery_images: ActressGalleryImage[];
}

export interface ActressWork {
  product_code: string;
  title_ko: string;
  actors_ko: string;
  genres_ko: string;
  cover_path: string;
  cover_url?: string;
  release_date: string;
  folder_path?: string;
  favorite_score: number;
  user_rating: number;
  user_liked: boolean;
  watch_later?: boolean;
  has_subtitle?: boolean;
  has_hardcoded_subtitle?: boolean;
  has_mosaic_removed?: boolean;
  has_preview?: boolean;
  preview_media?: "mp4" | "webp" | null;
  updated_at?: string;
}

export interface ActressWorksBundle {
  works: ActressWork[];
  genres: string[];
}

export const actressPhotoUrl = (profileImageUrl: string) =>
  profileImageUrl.startsWith("http")
    ? profileImageUrl
    : `${API_BASE}${profileImageUrl}`;

export const fetchActresses = (
  q = "",
  sort: ActressSort = "name",
  order: "asc" | "desc" = "asc",
  page = 1,
  perPage = 48,
) =>
  get<{ total: number; page: number; per_page: number; items: ActressListItem[] }>(
    `/api/actresses?q=${encodeURIComponent(q)}&sort=${sort}&order=${order}&page=${page}&per_page=${perPage}`,
  );

export const fetchActressProfile = (id: number) =>
  get<ActressProfile>(`/api/actresses/${id}`);

export const fetchActressWorks = (id: number) =>
  get<ActressWorksBundle>(`/api/actresses/${id}/works`);

export const resolveActressByName = (name: string) =>
  get<{ name: string; actress_id: number | null }>(
    `/api/actresses/resolve?name=${encodeURIComponent(name)}`,
  );

export const searchActresses = (q: string) =>
  get<Array<{ id: number; name_ko: string; name_ja: string; user_score: number }>>(
    `/api/actresses/search?q=${encodeURIComponent(q)}`,
  );

export const createActress = (body: Partial<ActressProfile>) =>
  post<ActressProfile>("/api/actresses", body);

export const updateActress = (id: number, body: Record<string, unknown>) =>
  patch<ActressProfile>(`/api/actresses/${id}`, body);

export const mergeActresses = (keepId: number, mergeId: number) =>
  post<{ ok: boolean; profile: ActressProfile }>(
    `/api/actresses/${keepId}/merge`,
    { merge_id: mergeId },
  );

export const addActressAlias = (
  id: number,
  alias_name: string,
  alias_type = "stage",
) =>
  post<ActressAlias>(`/api/actresses/${id}/aliases`, {
    alias_name,
    alias_type,
    is_primary: false,
  });

export const removeActressAlias = (id: number, aliasId: number) =>
  del<{ ok: boolean }>(`/api/actresses/${id}/aliases/${aliasId}`);

export const uploadActressImage = async (
  id: number,
  file: File,
  isProfile = false,
) => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(
    `${API_BASE}/api/actresses/${id}/images?is_profile=${isProfile ? "true" : "false"}`,
    { method: "POST", body: form },
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ ok: boolean; profile: ActressProfile }>;
};

export const setActressProfileImage = (id: number, imageId: number) =>
  post<{ ok: boolean; profile: ActressProfile }>(
    `/api/actresses/${id}/images/${imageId}/profile`,
    {},
  );
