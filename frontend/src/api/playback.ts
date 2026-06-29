import { get, API_BASE } from "./client";

/** 대용량 영상 스트림은 dev에서 Vite 프록시를 우회해 webapi로 직접 연결한다. */
const STREAM_BASE =
  import.meta.env.VITE_STREAM_BASE?.replace(/\/$/, "")
  || import.meta.env.VITE_API_BASE?.replace(/\/$/, "")
  || (import.meta.env.DEV ? "http://127.0.0.1:8765" : API_BASE || "http://127.0.0.1:8765");

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
): Promise<void> {
  const deadline = Date.now() + PROXY_MAX_WAIT_MS;
  while (Date.now() < deadline) {
    const res = await preparePlaybackStream(code, part);
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

export const streamUrl = (code: string, part: number) =>
  `${STREAM_BASE}/api/playback/${encodeURIComponent(code)}/stream/${part}`;
