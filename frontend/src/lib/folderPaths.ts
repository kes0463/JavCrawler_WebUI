/** Extract local folder paths from drag-and-drop (Electron / Windows Explorer). */

type FileWithPath = File & { path?: string };

const VIDEO_EXT = /\.(mp4|mkv|avi|wmv|mov|m4v|ts|webm|flv|mpg|mpeg)$/i;

function decodeUriPath(uri: string): string | null {
  const raw = uri.trim();
  if (!raw || raw.startsWith("#")) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "file:") return null;
    let p = decodeURIComponent(url.pathname || "");
    if (/^\/[A-Za-z]:/.test(p)) p = p.slice(1);
    return p.replace(/\//g, "\\");
  } catch {
    return null;
  }
}

function parentDir(filePath: string): string {
  const i = Math.max(filePath.lastIndexOf("\\"), filePath.lastIndexOf("/"));
  return i > 0 ? filePath.slice(0, i) : filePath;
}

/** 동영상 파일이면 부모 폴더, 폴더 경로면 그대로. */
function folderFromLocalPath(p: string): string {
  const trimmed = p.trim();
  if (!trimmed) return trimmed;
  return VIDEO_EXT.test(trimmed) ? parentDir(trimmed) : trimmed;
}

export function extractFolderPathsFromDataTransfer(dt: DataTransfer): string[] {
  const found = new Set<string>();

  const uriBlob = dt.getData("text/uri-list") || dt.getData("text/plain");
  if (uriBlob) {
    for (const line of uriBlob.split(/\r?\n/)) {
      const p = decodeUriPath(line);
      if (p) found.add(folderFromLocalPath(p));
    }
  }

  for (const file of Array.from(dt.files) as FileWithPath[]) {
    let p = file.path?.trim();
    if (!p && typeof window !== "undefined") {
      p = window.javstory?.getPathForFile?.(file)?.trim() || "";
    }
    if (!p) continue;
    found.add(folderFromLocalPath(p));
  }

  return [...found].filter(Boolean);
}

export function isElectron(): boolean {
  return typeof window !== "undefined" && !!(window as Window & { javstory?: unknown }).javstory;
}
