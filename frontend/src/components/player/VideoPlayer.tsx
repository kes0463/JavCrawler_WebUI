import { useCallback, useEffect, useMemo, useRef, useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
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
import Hls from "hls.js";
import {
  fetchSubtitleCues,
  hlsPlaylistUrl,
  preparePlaybackStream,
  streamUrl,
  waitForPlaybackStream,
  type PlaybackInfo,
  type StreamPrepareResult,
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
      return "HEVC → H.264 HLS 변환 중… (GPU 가속 시도)";
    case "fragmented":
      return "스트리밍 재생용 HLS 변환 중…";
    case "container":
      return "브라우저 재생용 HLS 변환 중… (H.264는 remux 우선)";
    case "codec":
      return "브라우저 호환 HLS로 변환 중…";
    default:
      return "브라우저 재생용 HLS 변환 중…";
  }
}

function formatEta(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "";
  if (sec < 60) return `약 ${Math.ceil(sec)}초 남음`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  if (m < 60) return `약 ${m}분 ${s}초 남음`;
  const h = Math.floor(m / 60);
  return `약 ${h}시간 ${m % 60}분 남음`;
}

interface VideoPlayerProps {
  session: PlaybackInfo;
  onClose: () => void;
}

export function VideoPlayer({ session, onClose }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const seekBarRef = useRef<HTMLDivElement>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resumeDone = useRef(false);
  const shouldAutoPlayRef = useRef(true);
  const isScrubbingRef = useRef(false);
  const seekTargetRef = useRef<number | null>(null);
  const wasPlayingBeforeSeekRef = useRef(false);
  const seekInProgressRef = useRef(false);

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
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [scrubTime, setScrubTime] = useState(0);
  const [showControls, setShowControls] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [osd, setOsd] = useState<string | null>(null);
  const [videoSize, setVideoSize] = useState({ w: 0, h: 0 });
  const [loadError, setLoadError] = useState<string | null>(null);
  const [proxyReady, setProxyReady] = useState(false);
  const [streamEpoch, setStreamEpoch] = useState(0);
  const [preparingProxy, setPreparingProxy] = useState(false);
  const [proxyReason, setProxyReason] = useState<string | null>(null);
  const [proxyProgress, setProxyProgress] = useState<number | null>(null);
  const [proxyEtaSec, setProxyEtaSec] = useState<number | null>(null);
  // 전체 HLS 변환 완료 여부(점진적 재생: 재생 시작 후에도 백그라운드 변환이 이어짐)
  const [proxyComplete, setProxyComplete] = useState(false);
  const [subtitleOptions, setSubtitleOptions] = useState<SubtitleDisplayOptions>(loadSubtitleOptions);
  const [subtitleSettingsOpen, setSubtitleSettingsOpen] = useState(false);
  const [seekLoading, setSeekLoading] = useState(false);

  const part = session.parts[partIndex] ?? session.parts[0];
  const code = session.product_code;
  const needsProxyWait = useMemo(() => {
    if (!part) return false;
    return (
      part.stream_mode === "hls"
      || part.needs_proxy === true
      || part.proxy_ready === false
      || /\.(ts|avi|mkv|wmv|mov)$/i.test(part.filename)
    );
  }, [part]);
  const isHlsMode = needsProxyWait;
  const streamReady = !needsProxyWait || proxyReady;
  const streamSrc = useMemo(
    () => (streamReady && part && !isHlsMode ? streamUrl(code, part.index) : undefined),
    [streamReady, part, code, isHlsMode],
  );
  const hlsSrc = useMemo(
    () => (streamReady && part && isHlsMode ? hlsPlaylistUrl(code, part.index) : undefined),
    [streamReady, part, code, isHlsMode],
  );

  const showOsd = useCallback((msg: string) => {
    setOsd(msg);
    window.setTimeout(() => setOsd(null), 1200);
  }, []);

  const CONTROLS_IDLE_MS = 2800;

  const clearHideTimer = useCallback(() => {
    if (hideTimer.current) {
      clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
  }, []);

  const scheduleHideChrome = useCallback(() => {
    clearHideTimer();
    hideTimer.current = setTimeout(() => {
      const v = videoRef.current;
      // 일시정지 중에는 컨트롤·제목 유지
      if (v?.paused) return;
      setShowControls(false);
    }, CONTROLS_IDLE_MS);
  }, [clearHideTimer]);

  /** 영상 위 마우스 이동·키보드 조작 시 표시 + 유휴 타이머 재시작 */
  const revealChrome = useCallback(() => {
    setShowControls(true);
    scheduleHideChrome();
  }, [scheduleHideChrome]);

  /** 컨트롤/제목 위에 있으면 숨김 타이머를 멈춰 유지 (컨테이너로 버블링 차단) */
  const onChromeEnter = useCallback((e: ReactMouseEvent) => {
    e.stopPropagation();
    setShowControls(true);
    clearHideTimer();
  }, [clearHideTimer]);

  const onChromeMove = useCallback((e: ReactMouseEvent) => {
    e.stopPropagation();
    setShowControls(true);
    clearHideTimer();
  }, [clearHideTimer]);

  const onChromeLeave = useCallback(() => {
    scheduleHideChrome();
  }, [scheduleHideChrome]);

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

  const rememberPlayStateForSeek = useCallback(() => {
    const v = videoRef.current;
    wasPlayingBeforeSeekRef.current = v != null && !v.paused;
  }, []);

  const resumeAfterSeek = useCallback(() => {
    const v = videoRef.current;
    if (!v || !wasPlayingBeforeSeekRef.current) return;

    const attemptPlay = () => {
      if (!wasPlayingBeforeSeekRef.current) return;
      void v.play()
        .then(() => {
          wasPlayingBeforeSeekRef.current = false;
        })
        .catch(() => {
          /* seek 완료 전이면 onSeeked/canplay에서 재시도 */
        });
    };

    if (v.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) {
      attemptPlay();
      return;
    }
    v.addEventListener("canplay", attemptPlay, { once: true });
  }, []);

  const seekBy = useCallback((deltaSec: number, label: string) => {
    const v = videoRef.current;
    if (!v) return;
    rememberPlayStateForSeek();
    const next = Math.max(0, Math.min(v.duration || 0, v.currentTime + deltaSec));
    v.currentTime = next;
    setCurrentTime(next);
    setScrubTime(next);
    showOsd(label);
    revealChrome();
  }, [showOsd, revealChrome, rememberPlayStateForSeek]);

  const pointerToSeekTime = useCallback((clientX: number) => {
    const bar = seekBarRef.current;
    if (!bar || !Number.isFinite(duration) || duration <= 0) return 0;
    const rect = bar.getBoundingClientRect();
    if (rect.width <= 0) return 0;
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return ratio * duration;
  }, [duration]);

  const commitSeek = useCallback((time: number) => {
    const v = videoRef.current;
    if (!v || !Number.isFinite(duration) || duration <= 0) return;
    const next = Math.max(0, Math.min(duration, time));
    seekTargetRef.current = next;
    v.currentTime = next;
    setCurrentTime(next);
    setScrubTime(next);
  }, [duration]);

  const handleSeekPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    if (!Number.isFinite(duration) || duration <= 0) return;
    rememberPlayStateForSeek();
    const t = pointerToSeekTime(e.clientX);
    isScrubbingRef.current = true;
    setIsScrubbing(true);
    setScrubTime(t);
    revealChrome();
    e.currentTarget.setPointerCapture(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
  }, [duration, pointerToSeekTime, revealChrome, rememberPlayStateForSeek]);

  const handleSeekPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!isScrubbingRef.current) return;
    setScrubTime(pointerToSeekTime(e.clientX));
    e.preventDefault();
  }, [pointerToSeekTime]);

  const handleSeekPointerUp = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!isScrubbingRef.current) return;
    const t = pointerToSeekTime(e.clientX);
    seekInProgressRef.current = true;
    setSeekLoading(true);
    commitSeek(t);
    isScrubbingRef.current = false;
    setIsScrubbing(false);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    e.preventDefault();
    e.stopPropagation();
  }, [pointerToSeekTime, commitSeek]);

  const displayTime = isScrubbing ? scrubTime : currentTime;
  const progressPct = duration > 0
    ? Math.max(0, Math.min(100, (displayTime / duration) * 100))
    : 0;

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
        revealChrome();
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
        revealChrome();
        break;
      case "ArrowDown":
        prevent();
        setVolume(vol => {
          const next = Math.max(0, vol - 0.05);
          showOsd(`🔊 ${Math.round(next * 100)}%`);
          return next;
        });
        revealChrome();
        break;
      case "m":
      case "M":
        prevent();
        setMuted(m => {
          showOsd(m ? "🔊 음소거 해제" : "🔇 음소거");
          return !m;
        });
        revealChrome();
        break;
      case "Home":
        prevent();
        rememberPlayStateForSeek();
        v.currentTime = 0;
        showOsd("⏮ 처음으로");
        revealChrome();
        break;
      default:
        if (/^[1-9]$/.test(key) && v.duration > 0) {
          prevent();
          rememberPlayStateForSeek();
          const pct = parseInt(key, 10) / 10;
          v.currentTime = v.duration * pct;
          showOsd(`▶ ${parseInt(key, 10) * 10}%`);
          revealChrome();
        }
        break;
    }
  }, [onClose, toggleFullscreen, seekBy, showOsd, revealChrome, rememberPlayStateForSeek]);

  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  useEffect(() => {
    return () => {
      if (hideTimer.current) clearTimeout(hideTimer.current);
    };
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
      setProxyComplete(true);
      return () => {
        cancelled = true;
      };
    }

    setProxyReady(false);
    setProxyComplete(false);
    setProxyReason(part.proxy_reason ?? null);
    setProxyProgress(null);
    setProxyEtaSec(null);
    const run = async () => {
      setPreparingProxy(true);
      try {
        await waitForPlaybackStream(code, part.index, info => {
          if (cancelled) return;
          setProxyReason(info.proxyReason);
          setProxyProgress(info.progress);
          setProxyEtaSec(info.etaSec);
          if (info.complete) setProxyComplete(true);
        });
        if (cancelled) return;
        setLoadError(null);
        setProxyReady(true);
        setStreamEpoch(e => e + 1);
        setPreparingProxy(false);

        // 재생은 시작됐다. 재인코딩 소스는 서버가 백그라운드에서 나머지 구간을 계속
        // 변환하고(시크하면 그 지점부터 우선 변환), 완료될 때까지 진행률만 가볍게
        // 폴링한다 — 플레이어는 다시 만들지 않는다.
        while (!cancelled) {
          await new Promise(r => setTimeout(r, 3000));
          if (cancelled) break;
          let info: StreamPrepareResult;
          try {
            info = await preparePlaybackStream(code, part.index);
          } catch {
            continue;
          }
          if (cancelled) break;
          setProxyProgress(info.progress ?? null);
          setProxyEtaSec(info.eta_sec ?? null);
          if (info.complete || info.status === "ready") {
            setProxyProgress(100);
            setProxyEtaSec(null);
            setProxyComplete(true);
            break;
          }
          if (info.status === "failed") {
            // 이미 재생 중이므로 플레이어를 내리지 않고 안내만 한다.
            setProxyComplete(true);
            setLoadError(info.error || "백그라운드 변환이 중단되었습니다");
            break;
          }
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
    if (!streamReady || !hlsSrc) return;
    const v = videoRef.current;
    if (!v) return;

    const canNativeHls = v.canPlayType("application/vnd.apple.mpegurl") !== "";
    if (canNativeHls) {
      v.src = hlsSrc;
      return () => {
        v.removeAttribute("src");
        v.load();
      };
    }

    if (!Hls.isSupported()) {
      setLoadError("HLS 재생을 지원하지 않는 브라우저입니다");
      return;
    }

    // startPosition: 0 — 항상 맨 앞부터 재생(재생목록은 완전한 VOD).
    // fragLoadPolicy — 온디맨드 변환에서 아직 인코딩 안 된 세그먼트는 서버가
    // (30초 대기 후에도 안 되면) 503을 주므로, 치명적 오류로 만들지 말고 넉넉히
    // 재시도하며 기다린다(시크 지점 우선 변환이 끝나면 다음 재시도에서 성공).
    const hls = new Hls({
      enableWorker: true,
      startPosition: 0,
      fragLoadPolicy: {
        default: {
          maxTimeToFirstByteMs: 45_000,
          maxLoadTimeMs: 60_000,
          timeoutRetry: { maxNumRetry: 6, retryDelayMs: 500, maxRetryDelayMs: 4_000 },
          errorRetry: { maxNumRetry: 12, retryDelayMs: 1_000, maxRetryDelayMs: 8_000 },
        },
      },
    });
    let recoverCount = 0;
    hls.loadSource(hlsSrc);
    hls.attachMedia(v);
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (!data.fatal) return;
      // 네트워크/미디어 오류는 몇 번 자체 복구를 시도한다(세그먼트 지연 대응).
      if (data.type === Hls.ErrorTypes.NETWORK_ERROR && recoverCount < 4) {
        recoverCount += 1;
        window.setTimeout(() => hls.startLoad(), 1_500);
        return;
      }
      if (data.type === Hls.ErrorTypes.MEDIA_ERROR && recoverCount < 4) {
        recoverCount += 1;
        hls.recoverMediaError();
        return;
      }
      setLoadError("HLS 재생 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");
    });
    return () => {
      hls.destroy();
    };
  }, [streamReady, hlsSrc, streamEpoch]);

  useEffect(() => {
    if (!streamReady || isHlsMode) return;
    const timer = window.setTimeout(() => {
      const v = videoRef.current;
      if (!v || loadError) return;
      if (!Number.isFinite(v.duration) || v.duration <= 0) {
        setLoadError("영상 메타데이터를 읽지 못했습니다. 새로고침 후 다시 시도해 주세요.");
      }
    }, 20_000);
    return () => window.clearTimeout(timer);
  }, [streamReady, isHlsMode, code, partIndex, loadError]);

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
      className="fixed inset-0 z-[120] bg-black isolate electron-no-drag"
      data-no-drag-scroll
      onMouseMove={revealChrome}
    >
      {/* 영상 레이어 — 하드웨어 합성 레이어가 오버레이를 덮지 않도록 z-0 */}
      <div className="absolute inset-0 z-0 flex items-center justify-center bg-black">
        {streamReady && (streamSrc || hlsSrc) ? (
        <video
          ref={videoRef}
          key={`${code}-${part.index}-${streamEpoch}-${isHlsMode ? "hls" : "direct"}`}
          src={streamSrc}
          className="relative z-0 max-w-full max-h-full w-full h-full object-contain"
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
          onDurationChange={() => {
            // 점진적 재생: 변환이 진행되며 재생목록이 커지면 duration도 커진다.
            // 탐색바 길이를 갱신하고, 아직 못 한 이어보기 점프를 재시도한다.
            const v = videoRef.current;
            if (!v || !Number.isFinite(v.duration) || v.duration <= 0) return;
            setDuration(v.duration);
            if (!resumeDone.current) tryResume();
          }}
          onCanPlay={() => {
            void attemptAutoPlay();
          }}
          onTimeUpdate={() => {
            if (isScrubbingRef.current) return;
            const v = videoRef.current;
            if (!v) return;
            const target = seekTargetRef.current;
            if (target != null) {
              if (Math.abs(v.currentTime - target) > 0.35) return;
              seekTargetRef.current = null;
            }
            setCurrentTime(v.currentTime);
          }}
          onSeeked={() => {
            const v = videoRef.current;
            if (!v || isScrubbingRef.current) return;
            seekTargetRef.current = null;
            setCurrentTime(v.currentTime);
            resumeAfterSeek();
          }}
          onPlaying={() => {
            if (seekInProgressRef.current) {
              seekInProgressRef.current = false;
              setSeekLoading(false);
            }
          }}
          onPlay={() => {
            setPlaying(true);
            scheduleHideChrome();
          }}
          onPause={() => {
            setPlaying(false);
            clearHideTimer();
            setShowControls(true);
          }}
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
          <div className="flex flex-col items-center gap-3 text-center px-6 w-full max-w-sm">
            <div className="w-10 h-10 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin" />
            <p className="text-white text-sm font-medium">{proxyPreparingMessage(proxyReason ?? part.proxy_reason)}</p>
            {proxyProgress != null && (
              <div className="w-full">
                <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-indigo-400 transition-[width] duration-500"
                    style={{ width: `${Math.max(2, Math.min(100, proxyProgress))}%` }}
                  />
                </div>
                <div className="mt-1.5 flex items-center justify-between text-xs text-slate-400 tabular-nums">
                  <span>{Math.floor(proxyProgress)}%</span>
                  {proxyEtaSec != null && proxyEtaSec > 0 && <span>{formatEta(proxyEtaSec)}</span>}
                </div>
              </div>
            )}
            <p className="text-slate-400 text-xs max-w-sm break-all">{part.filename}</p>
          </div>
        ) : null}
      </div>

      {/* 점진적 재생: 재생 중에도 백그라운드에서 나머지 구간을 HLS 변환 중 —
          화면 최상단에 얇은 진행 표시만 둔다(클릭 통과). */}
      {proxyReady && !proxyComplete && proxyProgress != null && (
        <div
          className="absolute top-0 inset-x-0 z-40 h-0.5 bg-white/10 pointer-events-none"
          title={
            `변환 중 ${Math.floor(proxyProgress)}%`
            + (proxyEtaSec != null && proxyEtaSec > 0 ? ` · ${formatEta(proxyEtaSec)}` : "")
          }
        >
          <div
            className="h-full bg-indigo-400 transition-[width] duration-700"
            style={{ width: `${Math.max(2, Math.min(100, proxyProgress))}%` }}
          />
        </div>
      )}

      {/* 자막·OSD — 영상 위, 컨트롤 아래 */}
      <div className="absolute inset-0 z-10 pointer-events-none">
        <SubtitleOverlay
          cue={trackIndex >= 0 ? activeCue : null}
          videoWidth={videoSize.w}
          videoHeight={videoSize.h}
          display={subtitleOptions}
        />
        {seekLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/30 pointer-events-none">
            <div className="w-10 h-10 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          </div>
        )}
        {osd && (
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 px-5 py-2.5 rounded-xl bg-black/70 text-white text-sm font-medium">
            {osd}
          </div>
        )}
        {loadError && (
          <div className="absolute inset-x-0 bottom-24 flex justify-center px-6 pointer-events-none">
            <p className="text-amber-300 text-sm bg-black/80 px-4 py-2 rounded-lg">{loadError}</p>
          </div>
        )}
      </div>

      {/* 상단 바 — 숨김 시 pointer-events-none (영상 위 마우스 이동으로 재표시).
          표시 중일 때만 프레임리스 창 드래그(electron-drag)를 켠다. */}
      <div
        className={cn(
          "absolute top-0 inset-x-0 z-30 flex items-center gap-3 px-4 py-3 min-h-[4.5rem] bg-gradient-to-b from-black/80 to-transparent transition-opacity",
          showControls ? "opacity-100 electron-drag" : "opacity-0 pointer-events-none",
        )}
        onMouseEnter={onChromeEnter}
        onMouseMove={onChromeMove}
        onMouseLeave={onChromeLeave}
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
          className="w-9 h-9 rounded-lg bg-white/10 hover:bg-white/20 flex items-center justify-center shrink-0 electron-no-drag"
          title="닫기 (Esc)"
          tabIndex={showControls ? 0 : -1}
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* 하단 컨트롤 — 숨김 시 클릭 통과, 표시는 컨테이너 mousemove로 복구 */}
      <div
        className={cn(
          "absolute bottom-0 inset-x-0 z-30 px-4 pb-4 pt-8 min-h-[6.5rem] bg-gradient-to-t from-black/90 to-transparent transition-opacity",
          showControls ? "opacity-100" : "opacity-0 pointer-events-none",
        )}
        onMouseEnter={onChromeEnter}
        onMouseMove={onChromeMove}
        onMouseLeave={onChromeLeave}
      >
        <div>
        <div
          ref={seekBarRef}
          role="slider"
          aria-label="재생 위치"
          aria-valuemin={0}
          aria-valuemax={duration || 0}
          aria-valuenow={displayTime}
          tabIndex={-1}
          className="relative flex items-center h-4 mb-3 cursor-pointer touch-none select-none outline-none [-webkit-tap-highlight-color:transparent]"
          onPointerDown={handleSeekPointerDown}
          onPointerMove={handleSeekPointerMove}
          onPointerUp={handleSeekPointerUp}
          onPointerCancel={handleSeekPointerUp}
          onKeyDown={e => {
            if (!Number.isFinite(duration) || duration <= 0) return;
            const step = e.shiftKey ? 30 : e.ctrlKey ? 60 : 5;
            if (e.key === "ArrowLeft") {
              e.preventDefault();
              rememberPlayStateForSeek();
              commitSeek(displayTime - step);
            } else if (e.key === "ArrowRight") {
              e.preventDefault();
              rememberPlayStateForSeek();
              commitSeek(displayTime + step);
            }
          }}
        >
          <div className="relative w-full h-1 rounded-full bg-white/20 overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full bg-indigo-400",
                isScrubbing ? "transition-none" : "transition-[width] duration-75 ease-linear",
              )}
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <div
            className={cn(
              "pointer-events-none absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-indigo-400 shadow",
              isScrubbing ? "opacity-100" : "opacity-0",
            )}
            style={{
              left: `clamp(0px, calc(${progressPct}% - 6px), calc(100% - 12px))`,
              transition: isScrubbing ? "none" : undefined,
            }}
          />
        </div>
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
            {formatTime(displayTime)} / {formatTime(duration)}
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
    </div>
  );
}
