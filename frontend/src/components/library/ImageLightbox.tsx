import { useEffect } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ImageLightboxNavigation {
  index: number;
  total: number;
  onPrevious: () => void;
  onNext: () => void;
}

export interface ImageLightboxProps {
  open: boolean;
  src: string;
  alt: string;
  onClose: () => void;
  zIndex?: number;
  ariaLabel?: string;
  navigation?: ImageLightboxNavigation;
}

export function ImageLightbox({
  open,
  src,
  alt,
  onClose,
  zIndex = 60,
  ariaLabel = "이미지 확대",
  navigation,
}: ImageLightboxProps) {
  const canPrev = navigation ? navigation.index > 0 : false;
  const canNext = navigation ? navigation.index < navigation.total - 1 : false;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        e.preventDefault();
        onClose();
        return;
      }
      if (!navigation) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        if (canPrev) {
          e.stopPropagation();
          e.preventDefault();
          navigation.onPrevious();
        }
        return;
      }
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        if (canNext) {
          e.stopPropagation();
          e.preventDefault();
          navigation.onNext();
        }
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose, navigation, canPrev, canNext]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/90 p-4 animate-fade-in"
      style={{ zIndex }}
      onClick={e => {
        e.stopPropagation();
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
    >
      <div className="absolute top-4 left-4 right-4 flex items-center justify-between gap-3 pointer-events-none">
        {navigation ? (
          <span className="px-3 py-1.5 rounded-lg bg-black/60 text-sm text-slate-200 tabular-nums pointer-events-auto">
            {navigation.index + 1} / {navigation.total}
          </span>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={e => {
            e.stopPropagation();
            onClose();
          }}
          className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-colors pointer-events-auto"
          aria-label="닫기"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {navigation && canPrev && (
        <button
          type="button"
          onClick={e => {
            e.stopPropagation();
            navigation.onPrevious();
          }}
          className="absolute left-3 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-colors"
          aria-label="이전 스냅샷"
        >
          <ChevronLeft className="w-6 h-6" />
        </button>
      )}

      {navigation && canNext && (
        <button
          type="button"
          onClick={e => {
            e.stopPropagation();
            navigation.onNext();
          }}
          className="absolute right-3 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-colors"
          aria-label="다음 스냅샷"
        >
          <ChevronRight className="w-6 h-6" />
        </button>
      )}

      <img
        key={src}
        src={src}
        alt={alt}
        draggable={false}
        onClick={e => e.stopPropagation()}
        className={cn(
          "max-w-[min(96vw,1200px)] max-h-[92vh] w-auto h-auto object-contain rounded-lg shadow-2xl",
          navigation && "mx-14",
        )}
      />
    </div>,
    document.body,
  );
}
