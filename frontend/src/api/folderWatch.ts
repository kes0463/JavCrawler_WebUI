import { get, post, del } from "./client";

export interface FolderBindingInboxItem {
  product_code: string;
  old_path: string;
  candidates: string[];
  monitoring_paused: boolean;
}

export interface FolderBindingInboxResponse {
  revision: number;
  items: FolderBindingInboxItem[];
}

export const fetchFolderBindingInbox = (): Promise<FolderBindingInboxResponse> =>
  get("/api/folder-watch/inbox");

export const removeFolderBindingInboxItem = (code: string): Promise<FolderBindingInboxResponse> =>
  del(`/api/folder-watch/inbox/${encodeURIComponent(code)}`);

export const clearFolderBindingInbox = (): Promise<FolderBindingInboxResponse> =>
  post("/api/folder-watch/inbox/clear");

export const searchFolderBindingCandidates = (
  productCode: string,
  oldPath: string,
): Promise<{ candidates: string[] }> =>
  post("/api/folder-watch/candidates", {
    product_code: productCode,
    old_path: oldPath,
  });

export const refreshFolderBindingCandidates = (
  productCode: string,
  oldPath: string,
): Promise<FolderBindingInboxResponse> =>
  post("/api/folder-watch/candidates/refresh", {
    product_code: productCode,
    old_path: oldPath,
  });

export const pauseFolderMonitoring = (code: string): Promise<FolderBindingInboxResponse> =>
  post(`/api/folder-watch/pause/${encodeURIComponent(code)}`);

export const resumeFolderMonitoring = (code: string): Promise<FolderBindingInboxResponse> =>
  post(`/api/folder-watch/resume/${encodeURIComponent(code)}`);

export const pauseAllListedFolderMonitoring = async (
  codes: string[],
): Promise<void> => {
  await Promise.all(codes.map(pc => pauseFolderMonitoring(pc)));
};
