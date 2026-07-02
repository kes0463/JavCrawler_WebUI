/** Extract local folder paths from drag-and-drop (Electron / Windows Explorer). */

type FileWithPath = File & { path?: string };

const VIDEO_EXT = /\.(mp4|mkv|avi|wmv|mov|m4v|ts|webm|flv|mpg|mpeg)$/i;
const WIN_PATH_RE = /^(?:[A-Za-z]:[\\/]|\\\\)/;

function decodeUriPath(uri: string): string | null {
  const raw = uri.trim();
  if (!raw || raw.startsWith("#")) return null;

  const normalized = raw.replace(/^file:\/\/([A-Za-z]:)/i, "file:///$1");

  try {
    const url = new URL(normalized);
    if (url.protocol !== "file:") return null;
    let p = decodeURIComponent(url.pathname || "");
    if (/^\/[A-Za-z]:/.test(p)) p = p.slice(1);
    return p.replace(/\//g, "\\");
  } catch {
    const m = raw.match(/^file:(\/\/+)(.+)$/i);
    if (m) {
      let p = decodeURIComponent(m[2]);
      if (!/^[A-Za-z]:/.test(p)) p = p.replace(/\//g, "\\");
      if (WIN_PATH_RE.test(p)) return p;
    }
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

function addPathFromLine(line: string, found: Set<string>): void {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#")) return;

  const fromUri = decodeUriPath(trimmed);
  if (fromUri) {
    found.add(folderFromLocalPath(fromUri));
    return;
  }

  if (WIN_PATH_RE.test(trimmed)) {
    found.add(folderFromLocalPath(trimmed));
  }
}

function extractFromTextBlob(text: string, found: Set<string>): void {
  for (const line of text.split(/\r?\n/)) {
    addPathFromLine(line, found);
  }
}

function extractFromHtml(html: string, found: Set<string>): void {
  const hrefRe = /href\s*=\s*["'](file:[^"']+)["']/gi;
  for (const m of html.matchAll(hrefRe)) {
    const p = decodeUriPath(m[1]);
    if (p) found.add(folderFromLocalPath(p));
  }
  const uriRe = /file:\/\/\/[^\s"'<>]+/gi;
  for (const m of html.matchAll(uriRe)) {
    const p = decodeUriPath(m[0]);
    if (p) found.add(folderFromLocalPath(p));
  }
}

function addPathFromFile(file: File, found: Set<string>): void {
  const f = file as FileWithPath;
  let p = f.path?.trim();
  if (!p && typeof window !== "undefined") {
    p = window.javstory?.getPathForFile?.(file)?.trim() || "";
  }
  if (!p) return;
  found.add(folderFromLocalPath(p));
}

export interface DataTransferSnapshot {
  typeData: Array<{ type: string; data: string }>;
  files: File[];
}

/** Drop 이벤트가 끝나기 전에 동기적으로 호출해야 dataTransfer 내용이 유지됩니다. */
export function snapshotDataTransfer(dt: DataTransfer): DataTransferSnapshot {
  const typeData: Array<{ type: string; data: string }> = [];
  for (const type of Array.from(dt.types)) {
    try {
      const data = dt.getData(type);
      if (data) typeData.push({ type, data });
    } catch {
      /* getData may throw for protected types */
    }
  }

  const files = Array.from(dt.files);
  if (dt.items) {
    for (let i = 0; i < dt.items.length; i++) {
      const item = dt.items[i];
      if (item.kind !== "file") continue;
      const file = item.getAsFile();
      if (file && !files.includes(file)) files.push(file);
    }
  }

  return { typeData, files };
}

function collectFromSnapshot(snapshot: DataTransferSnapshot, found: Set<string>): void {
  for (const { type, data } of snapshot.typeData) {
    const lower = type.toLowerCase();
    if (lower.includes("uri") || lower === "text/plain" || lower === "text") {
      extractFromTextBlob(data, found);
    } else if (lower === "text/html") {
      extractFromHtml(data, found);
    } else if (data.includes("file:") || WIN_PATH_RE.test(data.trim())) {
      extractFromTextBlob(data, found);
    }
  }

  for (const file of snapshot.files) {
    addPathFromFile(file, found);
  }
}

export function extractFolderPathsFromSnapshot(snapshot: DataTransferSnapshot): string[] {
  const found = new Set<string>();
  collectFromSnapshot(snapshot, found);
  return [...found].filter(Boolean);
}

export async function extractFolderPathsFromDataTransferAsync(dt: DataTransfer): Promise<string[]> {
  return extractFolderPathsFromSnapshot(snapshotDataTransfer(dt));
}

export function extractFolderPathsFromDataTransfer(dt: DataTransfer): string[] {
  return extractFolderPathsFromSnapshot(snapshotDataTransfer(dt));
}

export function isElectron(): boolean {
  return typeof window !== "undefined" && !!window.javstory?.isElectron;
}
