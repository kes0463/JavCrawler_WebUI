import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Bookmark, FileAudio, FolderOpen, Heart, Languages, Play, ScanEye, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PosterCardContextMenuProps {
  open: boolean;
  x: number;
  y: number;
  productCode: string;
  hasFolder: boolean;
  onClose: () => void;
  onAddStt: () => void;
  onAddSubtitle: () => void;
  onGrokStory?: () => void;
  onToggleLike?: () => void;
  onToggleWatchLater?: () => void;
  userLiked?: boolean;
  watchLater?: boolean;
  onPlay?: () => void;
  onOpenFolder?: () => void;
  onOpenDetail: () => void;
}

function MenuItem({
  icon,
  label,
  onClick,
  className,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={e => {
        e.stopPropagation();
        onClick();
      }}
      className={cn(
        "w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left rounded-lg",
        "text-[#d0d0e8] hover:bg-white/[0.08] hover:text-white transition-colors",
        className,
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function MenuDivider() {
  return <div className="my-1 border-t border-white/[0.08]" />;
}

export function PosterCardContextMenu({
  open,
  x,
  y,
  productCode,
  hasFolder,
  onClose,
  onAddStt,
  onAddSubtitle,
  onGrokStory,
  onToggleLike,
  onToggleWatchLater,
  userLiked = false,
  watchLater = false,
  onPlay,
  onOpenFolder,
  onOpenDetail,
}: PosterCardContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onPointer = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onPointer);
    };
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  const pad = 8;
  const menuW = 220;
  const menuH = 280;
  const left = Math.min(x, window.innerWidth - menuW - pad);
  const top = Math.min(y, window.innerHeight - menuH - pad);

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-[200] min-w-[220px] py-1.5 px-1.5 rounded-xl border border-white/[0.10] bg-bg-panel/95 shadow-xl backdrop-blur-md"
      style={{ left, top }}
      onClick={e => e.stopPropagation()}
      onContextMenu={e => e.preventDefault()}
    >
      <p className="px-3 py-1.5 text-xs font-mono text-indigo-300 truncate">{productCode}</p>
      <MenuDivider />
      <MenuItem
        icon={<FileAudio className="w-4 h-4 text-indigo-300 shrink-0" />}
        label="STT 큐에 추가"
        onClick={() => {
          onClose();
          onAddStt();
        }}
      />
      <MenuItem
        icon={<Languages className="w-4 h-4 text-violet-300 shrink-0" />}
        label="번역 큐에 추가"
        onClick={() => {
          onClose();
          onAddSubtitle();
        }}
      />
      {onGrokStory && (
        <MenuItem
          icon={<Sparkles className="w-4 h-4 text-amber-300 shrink-0" />}
          label="Grok 스토리 생성"
          onClick={() => {
            onClose();
            onGrokStory();
          }}
        />
      )}
      {onToggleLike && (
        <MenuItem
          icon={<Heart className={cn("w-4 h-4 shrink-0", userLiked ? "text-rose-400 fill-current" : "text-rose-300")} />}
          label={userLiked ? "좋아요 해제" : "좋아요"}
          onClick={() => {
            onClose();
            onToggleLike();
          }}
        />
      )}
      {onToggleWatchLater && (
        <MenuItem
          icon={<Bookmark className={cn("w-4 h-4 shrink-0", watchLater ? "text-sky-400 fill-current" : "text-sky-300")} />}
          label={watchLater ? "나중에 볼 해제" : "나중에 볼"}
          onClick={() => {
            onClose();
            onToggleWatchLater();
          }}
        />
      )}
      {(hasFolder && (onPlay || onOpenFolder)) && (
        <>
          <MenuDivider />
          {onPlay && (
            <MenuItem
              icon={<Play className="w-4 h-4 text-emerald-300 shrink-0" />}
              label="재생"
              onClick={() => {
                onClose();
                onPlay();
              }}
            />
          )}
          {onOpenFolder && (
            <MenuItem
              icon={<FolderOpen className="w-4 h-4 text-indigo-300 shrink-0" />}
              label="폴더 열기"
              onClick={() => {
                onClose();
                onOpenFolder();
              }}
            />
          )}
        </>
      )}
      <MenuDivider />
      <MenuItem
        icon={<ScanEye className="w-4 h-4 text-muted-foreground shrink-0" />}
        label="상세 보기"
        onClick={() => {
          onClose();
          onOpenDetail();
        }}
      />
    </div>,
    document.body,
  );
}
