import { get, post, API_BASE } from "./client";

const WEBAPI_PORT = String(import.meta.env.VITE_WEBAPI_PORT || "18765");

/**
 * dev: Vite 프록시는 대용량 `Range: bytes=0-` 응답(1GB+)을 버퍼링해 재생이 멈춘다.
 * 페이지와 동일 호스트명으로 webapi에 직접 스트리밍한다.
 */
function resolveStreamBase(): string {
  const fromEnv = import.meta.env.VITE_STREAM_BASE?.replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (import.meta.env.DEV) {
    const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
    return `http://${host}:${WEBAPI_PORT}`;
  }
  return (
    import.meta.env.VITE_API_BASE?.replace(/\/$/, "")
    || API_BASE
    || ""
  );
}

export interface SubtitleTrack {
  index: number;
  label: string;
  filename: string;
  ext: string;
}

export interface PlaybackPart {
  index: number;
  filename: string;
  resume_ms: number;
  needs_proxy?: boolean;
  proxy_ready?: boolean;
  proxy_reason?: string | null;
  stream_mode?: "direct" | "hls";
  subtitle_tracks: SubtitleTrack[];
}

export interface PlaybackInfo {
  product_code: string;
  title: string;
  parts: PlaybackPart[];
}

export interface SubtitleRunFont {
  family: string;
  size: number;
  bold: boolean;
  italic: boolean;
  underline: boolean;
  strike: boolean;
  spacing: number;
}

export interface SubtitleTextRun {
  kind: "text" | "drawing";
  text?: string;
  font?: SubtitleRunFont;
  primary?: string;
  outline?: string;
  shadow?: string;
  bord?: number;
  shad?: number;
  path?: string;
  bbox?: number[];
  fill?: string;
  stroke?: string;
  stroke_w?: number;
}

export interface AssSubtitleLine {
  an: number;
  pos: number[] | null;
  move: number[] | null;
  fade_in_ms: number;
  fade_out_ms: number;
  margin_l: number;
  margin_r: number;
  margin_v: number;
  runs: SubtitleTextRun[];
}

export interface AssSubtitleMeta {
  play_res_x: number;
  play_res_y: number;
  wrap_style: number;
  lines: AssSubtitleLine[];
}

export interface SubtitleCue {
  start_ms: number;
  end_ms: number;
  text: string;
  ass?: AssSubtitleMeta;
}

export const fetchPlaybackInfo = (code: string): Promise<PlaybackInfo> =>
  get(`/api/playback/${code}`);

export interface StreamPrepareResult {
  ready: boolean;
  needs_proxy: boolean;
  status: "direct" | "ready" | "building" | "failed" | string;
  proxy_reason?: string | null;
  error?: string | null;
  /** 변환 진행률(0~100). building이 아닐 땐 null일 수 있음 */
  progress?: number | null;
  /** 예상 남은 시간(초) */
  eta_sec?: number | null;
}

export interface StreamPrepareProgress {
  proxyReason: string | null;
  progress: number | null;
  etaSec: number | null;
}

export const preparePlaybackStream = (
  code: string,
  part: number,
): Promise<StreamPrepareResult> =>
  get(`/api/playback/${code}/stream/${part}/prepare`);

const PROXY_POLL_MS = 2000;
/**
 * 변환은 풀렝스 HEVC 등에서 백엔드 기준 최대 2시간까지 걸릴 수 있으므로,
 * 프론트에서 절대 시간으로 성급하게 포기하지 않는다. 서버가 `building`을
 * 정상 응답하는 한 계속 대기하고, `failed`거나 요청 자체가 연속으로 실패할
 * 때만 중단한다(백엔드가 ready/failed로 반드시 종결하므로 무한 루프는 없다).
 */
const PROXY_MAX_CONSECUTIVE_ERRORS = 5;

export async function waitForPlaybackStream(
  code: string,
  part: number,
  onPoll?: (info: StreamPrepareProgress) => void,
): Promise<void> {
  let consecutiveErrors = 0;
  for (;;) {
    let res: StreamPrepareResult;
    try {
      res = await preparePlaybackStream(code, part);
      consecutiveErrors = 0;
    } catch {
      consecutiveErrors += 1;
      if (consecutiveErrors >= PROXY_MAX_CONSECUTIVE_ERRORS) {
        throw new Error("재생 준비 상태를 확인할 수 없습니다 (서버 응답 없음)");
      }
      await new Promise(r => setTimeout(r, PROXY_POLL_MS));
      continue;
    }
    onPoll?.({
      proxyReason: res.proxy_reason ?? null,
      progress: res.progress ?? null,
      etaSec: res.eta_sec ?? null,
    });
    if (res.ready) return;
    if (res.status === "failed") {
      throw new Error(res.error || "브라우저 재생용 변환에 실패했습니다");
    }
    await new Promise(r => setTimeout(r, PROXY_POLL_MS));
  }
}

export const fetchSubtitleCues = (
  code: string,
  part: number,
  track: number,
): Promise<{ cues: SubtitleCue[] }> =>
  get(`/api/playback/${code}/subtitles/${part}/${track}`);

export const streamUrl = (code: string, part: number) => {
  const path = `/api/playback/${encodeURIComponent(code)}/stream/${part}`;
  const streamBase = resolveStreamBase();
  return streamBase ? `${streamBase}${path}` : path;
};

export const hlsPlaylistUrl = (code: string, part: number) => {
  const path = `/api/playback/${encodeURIComponent(code)}/hls/${part}/index.m3u8`;
  const streamBase = resolveStreamBase();
  return streamBase ? `${streamBase}${path}` : path;
};

export interface ProxyCacheStats {
  total_bytes: number;
  file_count: number;
  max_bytes: number;
}

export interface ProxyCacheClearResult {
  ok: boolean;
  removed: number;
  freed_bytes: number;
}

export const fetchProxyCacheStats = (): Promise<ProxyCacheStats> =>
  get(`/api/playback/cache/stats`);

export const clearProxyCache = (): Promise<ProxyCacheClearResult> =>
  post(`/api/playback/cache/clear`, {});
