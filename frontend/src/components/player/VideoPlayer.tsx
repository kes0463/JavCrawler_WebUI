import { useCallback, useEffect, useMemo, useRef, useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  Maximize,
  Minimize,
  Pause,
  Play,
  Settings2,
  Subtitles,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  fetchSubtitleCues,
  streamUrl,
  waitForPlaybackStream,
  type PlaybackInfo,
  type SubtitleCue,
} from "@/api/playback";
import { SubtitleOverlay } from "@/components/player/SubtitleOverlay";
import {
  loadSubtitleOptions,
  saveSubtitleOptions,
  type SubtitleDisplayOptions,
} from "@/components/player/subtitleOptions";
import { AppSelect } from "@/components/ui/AppSelect";

function pickDefaultTrack(tracks: { index: number; filename: string }[]): number {
  const ko = tracks.find(t => t.filename.includes(".ko."));
  if (ko) return ko.index;
  return tracks.length > 0 ? tracks[0].index : -1;
}

function formatTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function proxyPreparingMessage(reason?: string | null): string {
  switch (reason) {
    case "hevc":
      return "HEVC → H.264 변환 중… (GPU 가속 시도)";
    case "fragmented":
      return "스트리밍 재생용 MP4 재배치 중…";
    case "container":
      return "브라우저 재생용 MP4 변환 중…";
    case "codec":
      return "브라우저 호환 코덱으로 변환 중…";
    default:
      return "브라우저 재생용 MP4 변환 중…";
  }
}

interface VideoPlayerProps {
  session: PlaybackInfo;
  onClose: () => void;
}

export function VideoPlayer({ session, onClose }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resumeDone = useRef(false);
  const shouldAutoPlayRef = useRef(true);

  const [partIndex, setPartIndex] = useState(0);
  const [trackIndex, setTrackIndex] = useState(-1);
  const [cues, setCues] = useState<SubtitleCue[]>([]);
  const [activeCue, setActiveCue] = useState<SubtitleCue | null>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(() => {
    try {
      const v = localStorage.getItem("javstory.player.volume");
      return v ? Math.min(1, Math.max(0, parseFloat(v))) : 0.8;
    } catch {
      return 0.8;
    }
  });
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [showControls, setShowControls] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [osd, setOsd] = useState<string | null>(null);
  const [videoSize, setVideoSize] = useState({ w: 0, h: 0 });
  const [loadError, setLoadError] = useState<string | null>(null);
  const [proxyReady, setProxyReady] = useState(false);
  const [streamEpoch, setStreamEpoch] = useState(0);
  const [preparingProxy, setPreparingProxy] = useState(false);
  const [proxyReason, setProxyReason] = useState<string | null>(null);
  const [subtitleOptions, setSubtitleOptions] = useState<SubtitleDisplayOptions>(loadSubtitleOptions);
  const [subtitleSettingsOpen, setSubtitleSettingsOpen] = useState(false);

  const part = session.parts[partIndex] ?? session.parts[0];
  const code = session.product_code;
  const needsProxyWait = useMemo(() => {
    if (!part) return false;
    return (
      part.needs_proxy === true
      || part.proxy_ready === false
      || /\.(ts|avi|mkv|wmv|mov)$/i.test(part.filename)
    );
  }, [part]);
  const streamReady = !needsProxyWait || proxyReady;
  const streamSrc = useMemo(
    () => (streamReady && part ? streamUrl(code, part.index) : undefined),
    [streamReady, part, code],
  );

  const showOsd = useCallback((msg: string) => {
    setOsd(msg);
    window.setTimeout(() => setOsd(null), 1200);
  }, []);

  const bumpControls = useCallback(() => {
    setShowControls(true);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      if (playing) setShowControls(false);
    }, 3000);
  }, [playing]);

  const toggleFullscreen = useCallback(async () => {
    const el = containerRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await el.requestFullscreen();
      }
    } catch {
      showOsd("전체화면을 사용할 수 없습니다");
    }
  }, [showOsd]);

  const seekBy = useCallback((deltaSec: number, label: string) => {
    const v = videoRef.current;
    if (!v) return;
    const next = Math.max(0, Math.min(v.duration || 0, v.currentTime + deltaSec));
    v.currentTime = next;
    showOsd(label);
    bumpControls();
  }, [showOsd, bumpControls]);

  const handleKeyDown = useCallback((e: ReactKeyboardEvent | KeyboardEvent) => {
    const v = videoRef.current;
    if (!v) return;

    const key = e.key;
    const ctrl = e.ctrlKey || (e as ReactKeyboardEvent).ctrlKey;
    const alt = e.altKey || (e as ReactKeyboardEvent).altKey;
    const shift = e.shiftKey || (e as ReactKeyboardEvent).shiftKey;

    const prevent = () => {
      e.preventDefault();
      e.stopPropagation();
    };

    switch (key) {
      case " ":
        prevent();
        if (v.paused) { void v.play(); showOsd("▶ 재생"); }
        else { v.pause(); showOsd("⏸ 일시정지"); }
        bumpControls();
        break;
      case "Escape":
      case "Backspace":
        prevent();
        if (document.fullscreenElement) void toggleFullscreen();
        else onClose();
        break;
      case "Enter":
      case "f":
      case "F":
        prevent();
        void toggleFullscreen();
        break;
      case "ArrowLeft": {
        prevent();
        let d = 5;
        let label = "◀ -5초";
        if (alt) { d = 300; label = "◀◀◀◀ -5분"; }
        else if (ctrl) { d = 60; label = "◀◀◀ -1분"; }
        else if (shift) { d = 30; label = "◀◀ -30초"; }
        seekBy(-d, label);
        break;
      }
      case "ArrowRight": {
        prevent();
        let d = 5;
        let label = "+5초 ▶";
        if (alt) { d = 300; label = "+5분 ▶▶▶▶"; }
        else if (ctrl) { d = 60; label = "+1분 ▶▶▶"; }
        else if (shift) { d = 30; label = "+30초 ▶▶"; }
        seekBy(d, label);
        break;
      }
      case "ArrowUp":
        prevent();
        setVolume(vol => {
          const next = Math.min(1, vol + 0.05);
          showOsd(`🔊 ${Math.round(next * 100)}%`);
          return next;
        });
        bumpControls();
        break;
      case "ArrowDown":
        prevent();
        setVolume(vol => {
          const next = Math.max(0, vol - 0.05);
          showOsd(`🔊 ${Math.round(next * 100)}%`);
          return next;
        });
        bumpControls();
        break;
      case "m":
      case "M":
        prevent();
        setMuted(m => {
          showOsd(m ? "🔊 음소거 해제" : "🔇 음소거");
          return !m;
        });
        bumpControls();
        break;
      case "Home":
        prevent();
        v.currentTime = 0;
        showOsd("⏮ 처음으로");
        bumpControls();
        break;
      default:
        if (/^[1-9]$/.test(key) && v.duration > 0) {
          prevent();
          const pct = parseInt(key, 10) / 10;
          v.currentTime = v.duration * pct;
          showOsd(`▶ ${parseInt(key, 10) * 10}%`);
          bumpControls();
        }
        break;
    }
  }, [onClose, toggleFullscreen, seekBy, showOsd, bumpControls]);

  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => handleKeyDown(e);
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [handleKeyDown]);

  useEffect(() => {
    if (!part) return;
    const def = pickDefaultTrack(part.subtitle_tracks);
    setTrackIndex(def);
  }, [part]);

  useEffect(() => {
    resumeDone.current = false;
    setLoadError(null);
    setCurrentTime(0);
    setDuration(0);
    setPlaying(false);
    shouldAutoPlayRef.current = true;
  }, [partIndex, code]);

  useEffect(() => {
    if (!part) return;
    let cancelled = false;

    if (!needsProxyWait) {
      setProxyReady(true);
      setPreparingProxy(false);
      setProxyReason(null);
      return () => {
        cancelled = true;
      };
    }

    setProxyReady(false);
    setProxyReason(part.proxy_reason ?? null);
    const run = async () => {
      setPreparingProxy(true);
      try {
        await waitForPlaybackStream(code, part.index, (reason: string | null) => {
          if (!cancelled) setProxyReason(reason);
        });
        if (!cancelled) {
          setLoadError(null);
          setProxyReady(true);
          setStreamEpoch(e => e + 1);
          setPreparingProxy(false);
        }
      } catch (e) {
        if (!cancelled) {
          setPreparingProxy(false);
          setLoadError(
            e instanceof Error ? e.message : "재생 준비에 실패했습니다",
          );
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [code, part, partIndex, needsProxyWait]);

  useEffect(() => {
    if (!streamReady) return;
    const timer = window.setTimeout(() => {
      const v = videoRef.current;
      if (!v || loadError) return;
      if (!Number.isFinite(v.duration) || v.duration <= 0) {
        setLoadError("영상 메타데이터를 읽지 못했습니다. 새로고침 후 다시 시도해 주세요.");
      }
    }, 20_000);
    return () => window.clearTimeout(timer);
  }, [streamReady, code, partIndex, loadError]);

  useEffect(() => {
    if (trackIndex < 0 || !part) {
      setCues([]);
      return;
    }
    let cancelled = false;
    fetchSubtitleCues(code, part.index, trackIndex)
      .then(res => { if (!cancelled) setCues(res.cues); })
      .catch(() => { if (!cancelled) setCues([]); });
    return () => { cancelled = true; };
  }, [code, part, trackIndex]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v || !streamReady) return;
    v.volume = volume;
    v.muted = muted;
    try { localStorage.setItem("javstory.player.volume", String(volume)); } catch { /* ignore */ }
  }, [streamReady, volume, muted]);

  useEffect(() => {
    const ms = (currentTime || 0) * 1000;
    const cue = cues.find(c => ms >= c.start_ms && ms < c.end_ms) ?? null;
    setActiveCue(cue);
  }, [currentTime, cues]);

  const tryResume = useCallback(() => {
    const v = videoRef.current;
    if (!v || resumeDone.current || !part) return;
    const pos = part.resume_ms || 0;
    if (pos <= 5000) return;
    if (v.duration > 0 && pos / 1000 < v.duration - 10) {
      v.currentTime = pos / 1000;
      resumeDone.current = true;
      showOsd("이어보기");
    }
  }, [part, showOsd]);

  const attemptAutoPlay = useCallback(async () => {
    if (!shouldAutoPlayRef.current) return;
    const v = videoRef.current;
    if (!v) return;
    try {
      await v.play();
      shouldAutoPlayRef.current = false;
    } catch {
      try {
        v.muted = true;
        setMuted(true);
        await v.play();
        shouldAutoPlayRef.current = false;
        showOsd("자동 재생 (음소거)");
      } catch {
        /* 브라우저 정책으로 재생 차단 — 사용자가 직접 재생 */
      }
    }
  }, [showOsd]);

  const patchSubtitleOptions = useCallback((patch: Partial<SubtitleDisplayOptions>) => {
    setSubtitleOptions(prev => {
      const next = { ...prev, ...patch };
      saveSubtitleOptions(next);
      return next;
    });
  }, []);

  const goNextPart = useCallback(() => {
    const next = partIndex + 1;
    if (next < session.parts.length) {
      shouldAutoPlayRef.current = true;
      showOsd(`다음 영상 (${next + 1}/${session.parts.length})`);
      setPartIndex(next);
    } else {
      onClose();
    }
  }, [partIndex, session.parts.length, onClose, showOsd]);

  const selectPart = useCallback((index: number) => {
    shouldAutoPlayRef.current = true;
    setPartIndex(index);
  }, []);

  if (!part) {
    return null;
  }

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-[120] bg-black flex flex-col"
      onMouseMove={bumpControls}
      onClick={bumpControls}
    >
      <div className="relative flex-1 flex items-center justify-center min-h-0 bg-black">
        {streamReady && streamSrc ? (
        <video
          ref={videoRef}
          key={`${streamSrc}-${streamEpoch}`}
          src={streamSrc}
          className="max-w-full max-h-full w-full h-full object-contain"
          playsInline
          autoPlay
          preload="auto"
          onLoadedMetadata={() => {
            const v = videoRef.current;
            if (!v) return;
            setDuration(v.duration);
            setVideoSize({ w: v.videoWidth, h: v.videoHeight });
            tryResume();
            void attemptAutoPlay();
          }}
          onLoadedData={() => {
            const v = videoRef.current;
            if (!v || !Number.isFinite(v.duration) || v.duration <= 0) return;
            setDuration(v.duration);
            setVideoSize({ w: v.videoWidth, h: v.videoHeight });
            void attemptAutoPlay();
          }}
          onCanPlay={() => {
            void attemptAutoPlay();
          }}
          onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime ?? 0)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={goNextPart}
          onError={() => {
            const err = videoRef.current?.error;
            const errCode = err?.code;
            const detail =
              errCode === 4 ? " (코덱/컨테이너 미지원)"
              : errCode === 3 ? " (디코딩 오류)"
              : errCode === 2 ? " (네트워크 오류 — webapi 실행 여부 확인)"
              : "";
            setLoadError(`브라우저에서 이 형식을 재생할 수 없습니다 (MP4/H.264 권장)${detail}`);
          }}
          onDoubleClick={() => void toggleFullscreen()}
          onClick={e => {
            e.stopPropagation();
            const v = videoRef.current;
            if (!v) return;
            shouldAutoPlayRef.current = false;
            if (v.paused) void v.play();
            else v.pause();
          }}
        />
        ) : preparingProxy ? (
          <div className="flex flex-col items-center gap-3 text-center px-6">
            <div className="w-10 h-10 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin" />
            <p className="text-white text-sm font-medium">{proxyPreparingMessage(proxyReason ?? part.proxy_reason)}</p>
            <p className="text-slate-400 text-xs max-w-sm break-all">{part.filename}</p>
          </div>
        ) : null}

        <SubtitleOverlay
          cue={trackIndex >= 0 ? activeCue : null}
          videoWidth={videoSize.w}
          videoHeight={videoSize.h}
          display={subtitleOptions}
        />

        {osd && (
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 px-5 py-2.5 rounded-xl bg-black/70 text-white text-sm font-medium pointer-events-none">
            {osd}
          </div>
        )}

        {loadError && (
          <div className="absolute inset-x-0 bottom-24 flex justify-center px-6">
            <p className="text-amber-300 text-sm bg-black/80 px-4 py-2 rounded-lg">{loadError}</p>
          </div>
        )}
      </div>

      {/* 상단 바 */}
      <div
        className={cn(
          "absolute top-0 inset-x-0 flex items-center gap-3 px-4 py-3 bg-gradient-to-b from-black/80 to-transparent transition-opacity",
          showControls ? "opacity-100" : "opacity-0 pointer-events-none",
        )}
      >
        <div className="min-w-0 flex-1">
          <p className="text-2xl font-mono font-bold text-indigo-300 leading-tight truncate">{code}</p>
          <p className="text-lg text-[#d0d0e8] truncate leading-snug mt-0.5">
            {session.title || part.filename}
            {session.parts.length > 1 && (
              <span className="text-base text-slate-400 ml-2">
                ({partIndex + 1}/{session.parts.length})
              </span>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="w-9 h-9 rounded-lg bg-white/10 hover:bg-white/20 flex items-center justify-center"
          title="닫기 (Esc)"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* 하단 컨트롤 */}
      <div
        className={cn(
          "absolute bottom-0 inset-x-0 px-4 pb-4 pt-8 bg-gradient-to-t from-black/90 to-transparent transition-opacity",
          showControls ? "opacity-100" : "opacity-0 pointer-events-none",
        )}
      >
        <input
          type="range"
          min={0}
          max={duration || 1}
          step={0.1}
          value={currentTime}
          onChange={e => {
            const v = videoRef.current;
            if (!v) return;
            v.currentTime = parseFloat(e.target.value);
          }}
          className="w-full h-1 accent-indigo-500 cursor-pointer mb-3"
        />
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={() => {
              const v = videoRef.current;
              if (!v) return;
              shouldAutoPlayRef.current = false;
              if (v.paused) void v.play();
              else v.pause();
            }}
            className="w-10 h-10 rounded-full bg-white/15 hover:bg-white/25 flex items-center justify-center"
          >
            {playing ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
          </button>

          <span className="text-xs text-slate-300 tabular-nums min-w-[5.5rem]">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>

          <button
            type="button"
            onClick={() => setMuted(m => !m)}
            className="w-9 h-9 rounded-lg hover:bg-white/10 flex items-center justify-center"
          >
            {muted || volume === 0
              ? <VolumeX className="w-4 h-4" />
              : <Volume2 className="w-4 h-4" />}
          </button>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={muted ? 0 : volume}
            onChange={e => {
              const val = parseFloat(e.target.value);
              setVolume(val);
              setMuted(val === 0);
            }}
            className="w-24 h-1 accent-indigo-500"
          />

          {part.subtitle_tracks.length > 0 && (
            <div className="flex items-center gap-1.5 ml-auto min-w-0">
              <Subtitles className="w-4 h-4 text-slate-400 shrink-0" />
              <AppSelect
                value={trackIndex}
                onChange={setTrackIndex}
                placement="top"
                aria-label="자막 선택"
                className="max-w-[12rem]"
                options={[
                  { value: -1, label: "자막 끔" },
                  ...part.subtitle_tracks.map(t => ({
                    value: t.index,
                    label: `${t.label === "자맙" ? "자막" : t.label} (${t.ext.toUpperCase()})`,
                  })),
                ]}
              />
              <button
                type="button"
                onClick={() => setSubtitleSettingsOpen(o => !o)}
                className={cn(
                  "w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                  subtitleSettingsOpen
                    ? "bg-indigo-500/30 text-indigo-200"
                    : "hover:bg-white/10 text-slate-400",
                )}
                title="자막 크기·위치"
                aria-label="자막 크기·위치 설정"
              >
                <Settings2 className="w-4 h-4" />
              </button>
            </div>
          )}

          {session.parts.length > 1 && (
            <AppSelect
              value={partIndex}
              onChange={selectPart}
              placement="top"
              aria-label="영상 파트 선택"
              className="max-w-[min(20rem,42vw)]"
              options={session.parts.map((p, i) => ({
                value: i,
                label: p.filename,
              }))}
            />
          )}

          <button
            type="button"
            onClick={() => void toggleFullscreen()}
            className="w-9 h-9 rounded-lg hover:bg-white/10 flex items-center justify-center"
            title="전체화면 (F)"
          >
            {isFullscreen
              ? <Minimize className="w-4 h-4" />
              : <Maximize className="w-4 h-4" />}
          </button>
        </div>

        {subtitleSettingsOpen && part.subtitle_tracks.length > 0 && (
          <div className="mt-3 pt-3 border-t border-white/10 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <span className="w-10 shrink-0">크기</span>
              <input
                type="range"
                min={0.5}
                max={2}
                step={0.05}
                value={subtitleOptions.sizeScale}
                onChange={e => patchSubtitleOptions({ sizeScale: parseFloat(e.target.value) })}
                className="flex-1 h-1 accent-indigo-500 cursor-pointer"
              />
              <span className="w-10 text-right tabular-nums text-slate-300">
                {Math.round(subtitleOptions.sizeScale * 100)}%
              </span>
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <span className="w-10 shrink-0">위치</span>
              <input
                type="range"
                min={4}
                max={40}
                step={1}
                value={subtitleOptions.bottomPercent}
                onChange={e => patchSubtitleOptions({ bottomPercent: parseInt(e.target.value, 10) })}
                className="flex-1 h-1 accent-indigo-500 cursor-pointer"
              />
              <span className="w-10 text-right tabular-nums text-slate-300">
                {subtitleOptions.bottomPercent}%
              </span>
            </label>
          </div>
        )}

        <p className="text-[10px] text-slate-500 mt-2 hidden sm:block">
          Space 재생 · ←→ 탐색(Shift 30초/Ctrl 1분/Alt 5분) · ↑↓ 볼륨 · M 음소거 · F 전체화면 · 1-9 %이동 · Esc 닫기
        </p>
      </div>
    </div>
  );
}
