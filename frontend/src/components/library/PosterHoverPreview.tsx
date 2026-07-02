import { useCallback, useEffect, useId, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import {
  claimPreviewHover,
  releasePreviewHover,
  subscribePreviewHover,
} from "@/lib/previewHoverLock";

const HOVER_DELAY_MS = 180;

interface PosterHoverPreviewProps {
  productCode: string;
  coverSrc?: string;
  previewSrc?: string;
  previewMedia?: "mp4" | "webp" | null;
  hasPreview?: boolean;
  alt: string;
  showCover: boolean;
  onCoverError?: () => void;
  className?: string;
}

export function PosterHoverPreview({
  productCode,
  coverSrc,
  previewSrc,
  previewMedia,
  hasPreview = false,
  alt,
  showCover,
  onCoverError,
  className,
}: PosterHoverPreviewProps) {
  const slotId = useId();
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hovering = useRef(false);
  const [previewActive, setPreviewActive] = useState(false);
  const [webpFallback, setWebpFallback] = useState(false);
  const [mediaReady, setMediaReady] = useState(false);
  const [mediaFailed, setMediaFailed] = useState(false);

  const clearHoverTimer = useCallback(() => {
    if (hoverTimer.current) {
      clearTimeout(hoverTimer.current);
      hoverTimer.current = null;
    }
  }, []);

  const deactivatePreview = useCallback(() => {
    clearHoverTimer();
    setPreviewActive(false);
    setMediaReady(false);
    setMediaFailed(false);
    releasePreviewHover(slotId);
  }, [clearHoverTimer, slotId]);

  useEffect(() => {
    return subscribePreviewHover(active => {
      if (active !== slotId) {
        setPreviewActive(false);
      }
    });
  }, [slotId]);

  useEffect(() => {
    return () => {
      clearHoverTimer();
      releasePreviewHover(slotId);
    };
  }, [clearHoverTimer, slotId]);

  const handleMouseEnter = () => {
    if (!hasPreview || !previewSrc) return;
    hovering.current = true;
    clearHoverTimer();
    hoverTimer.current = setTimeout(() => {
      if (!hovering.current) return;
      claimPreviewHover(slotId);
      setPreviewActive(true);
    }, HOVER_DELAY_MS);
  };

  const handleMouseLeave = () => {
    hovering.current = false;
    deactivatePreview();
  };

  useEffect(() => {
    setWebpFallback(false);
    setMediaReady(false);
    setMediaFailed(false);
  }, [previewSrc, previewMedia]);

  const showPreviewLayer = previewActive && hasPreview && !!previewSrc && !mediaFailed;
  const hideCover = showPreviewLayer && mediaReady;
  const showMp4Preview =
    showPreviewLayer && previewSrc && (previewMedia === "mp4" || (!previewMedia && !webpFallback));
  const showWebpPreview =
    showPreviewLayer && previewSrc && (previewMedia === "webp" || webpFallback);

  const handleMediaError = () => {
    if (previewMedia === "mp4") {
      setMediaFailed(true);
      setPreviewActive(false);
      return;
    }
    setWebpFallback(true);
    setMediaReady(false);
  };

  return (
    <div
      className={cn("relative w-full", className)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {showCover ? (
        <img
          src={coverSrc}
          alt={alt}
          draggable={false}
          loading="lazy"
          onError={onCoverError}
          className={cn(
            "w-full h-auto block object-contain pointer-events-none transition-opacity duration-150",
            hideCover ? "opacity-0" : "opacity-100",
          )}
        />
      ) : (
        <div className="aspect-[2/3] flex flex-col items-center justify-center gap-2 p-4 text-center">
          <span className="text-sm font-mono text-slate-500">{productCode || "NO IMG"}</span>
        </div>
      )}

      {showMp4Preview && (
        <video
          key={previewSrc}
          src={previewSrc}
          autoPlay
          loop
          muted
          playsInline
          preload="auto"
          onLoadedData={() => setMediaReady(true)}
          onCanPlay={() => setMediaReady(true)}
          onError={handleMediaError}
          className="absolute inset-0 w-full h-full object-cover pointer-events-none"
        />
      )}

      {showWebpPreview && (
        <img
          key={previewSrc}
          src={previewSrc}
          alt=""
          draggable={false}
          onLoad={() => setMediaReady(true)}
          onError={handleMediaError}
          className="absolute inset-0 w-full h-full object-cover pointer-events-none"
        />
      )}
    </div>
  );
}
