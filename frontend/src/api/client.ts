export const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/$/, "")
  || (import.meta.env.DEV ? "" : "http://127.0.0.1:8765");

export interface ApiStatus {
  api: string;
  actress_count?: number;
  actresses_prefix?: string;
  db_path?: string;
}

export const fetchApiStatus = () => get<ApiStatus>("/api/status", 5_000);

function formatApiError(text: string): string {
  if (text.includes("Not Found") || text.includes('"detail":"Not Found"')) {
    if (text.includes("insight") || text.includes("/api/insight")) {
      return "인사이트 API를 찾을 수 없습니다. start_web.bat으로 webapi를 재시작해 주세요.";
    }
    return "배우 API를 찾을 수 없습니다. JAVSTORY_WebUI 폴더에서 start_web.bat으로 webapi를 재시작해 주세요. (구버전 JAVSTORY webapi가 8765 포트를 점유 중일 수 있습니다)";
  }
  if (text.includes("Method Not Allowed") || text.includes('"detail":"Method Not Allowed"')) {
    return "작품 편집 API가 활성화되지 않았습니다. start_web.bat으로 webapi를 재시작해 주세요. (8765 포트에 구버전 프로세스가 남아 있을 수 있습니다)";
  }
  return text;
}

const DEFAULT_TIMEOUT_MS = 45_000;
const MUTATION_TIMEOUT_MS = 30_000;

async function request<T>(path: string, init?: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...init, signal: ctrl.signal });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(formatApiError(text) || `HTTP ${res.status}`);
    }
    return res.json() as Promise<T>;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("API 응답 시간 초과 — webapi가 과부하 상태일 수 있습니다. 잠시 후 다시 시도하거나 start_web.bat으로 재시작해 주세요.");
    }
    throw e;
  } finally {
    window.clearTimeout(timer);
  }
}

export const get = <T>(path: string, timeoutMs?: number) => request<T>(path, undefined, timeoutMs);

export const post = <T>(path: string, body?: unknown, timeoutMs = MUTATION_TIMEOUT_MS) =>
  request<T>(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    },
    timeoutMs,
  );

export const del = <T>(path: string, timeoutMs = MUTATION_TIMEOUT_MS) =>
  request<T>(path, { method: "DELETE" }, timeoutMs);

export const patch = <T>(path: string, body?: unknown, timeoutMs = MUTATION_TIMEOUT_MS) =>
  request<T>(
    path,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    },
    timeoutMs,
  );

export const WS_BASE = API_BASE
  ? API_BASE.replace(/^http/, "ws")
  : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.hostname}:8765`;
