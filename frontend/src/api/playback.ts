import { get, API_BASE } from "./client";

const WEBAPI_PORT = String(import.meta.env.VITE_WEBAPI_PORT || "8765");

/**
 * dev: Vite 프록시는 대용량 `Range: bytes=0-` 응답(1GB+)을 버퍼링해 재생이 멈춘다.
 * `localhost:8765`로 직접 스트리밍한다(페이지와 동일 호스트명 `localhost` — `127.0.0.1`은 차단됨).
 */
const STREAM_BASE =
  import.meta.env.VITE_STREAM_BASE?.replace(/\/$/, "")
  || (import.meta.env.DEV ? `http://localhost:${WEBAPI_PORT}` : "")
  || import.meta.env.VITE_API_BASE?.replace(/\/$/, "")
  || API_BASE
  || "";

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
}

export const preparePlaybackStream = (
  code: string,
  part: number,
): Promise<StreamPrepareResult> =>
  get(`/api/playback/${code}/stream/${part}/prepare`);

const PROXY_POLL_MS = 2000;
const PROXY_MAX_WAIT_MS = 30 * 60 * 1000;

export async function waitForPlaybackStream(
  code: string,
  part: number,
  onPoll?: (proxyReason: string | null) => void,
): Promise<void> {
  const deadline = Date.now() + PROXY_MAX_WAIT_MS;
  while (Date.now() < deadline) {
    const res = await preparePlaybackStream(code, part);
    onPoll?.(res.proxy_reason ?? null);
    if (res.ready) return;
    if (res.status === "failed") {
      throw new Error(res.error || "브라우저 재생용 변환에 실패했습니다");
    }
    await new Promise(r => setTimeout(r, PROXY_POLL_MS));
  }
  throw new Error("브라우저 재생용 변환 시간이 초과되었습니다");
}

export const fetchSubtitleCues = (
  code: string,
  part: number,
  track: number,
): Promise<{ cues: SubtitleCue[] }> =>
  get(`/api/playback/${code}/subtitles/${part}/${track}`);

export const streamUrl = (code: string, part: number) => {
  const path = `/api/playback/${encodeURIComponent(code)}/stream/${part}`;
  return STREAM_BASE ? `${STREAM_BASE}${path}` : path;
};
