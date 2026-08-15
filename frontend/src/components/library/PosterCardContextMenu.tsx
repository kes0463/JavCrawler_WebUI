import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Bookmark, Download, FileAudio, FolderOpen, Heart, Languages, Play, RefreshCw, ScanEye, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PosterCardContextMenuProps {
  open: boolean;
  x: number;
  y: number;
  /** 단일 또는 다중 선택 품번 */
  productCodes: string[];
  hasFolder: boolean;
  onClose: () => void;
  onAddStt: () => void;
  onAddSubtitle: () => void;
  onCrawl?: () => void;
  onRecrawl?: () => void;
  onGrokStory?: () => void;
  onToggleLike?: () => void;
  onToggleWatchLater?: () => void;
  userLiked?: boolean;
  watchLater?: boolean;
  onPlay?: () => void;
  onOpenFolder?: () => void;
  onOpenDetail?: () => void;
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
  productCodes,
  hasFolder,
  onClose,
  onAddStt,
  onAddSubtitle,
  onCrawl,
  onRecrawl,
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
  const codes = productCodes.map(c => c.trim().toUpperCase()).filter(Boolean);
  const multi = codes.length > 1;
  const labelPrefix = multi ? `${codes.length}개` : (codes[0] || "");

  // 실제 렌더된 메뉴 크기를 재서 화면 밖으로 넘치지 않게 위치를 보정한다.
  // (항목 개수에 따라 높이가 달라지므로 고정값 가정은 어긋남을 유발한다.)
  const [pos, setPos] = useState({ left: x, top: y });

  useLayoutEffect(() => {
    if (!open) return;
    const el = menuRef.current;
    if (!el) return;
    const pad = 8;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const left = Math.max(pad, Math.min(x, window.innerWidth - w - pad));
    const top = Math.max(pad, Math.min(y, window.innerHeight - h - pad));
    setPos({ left, top });
  }, [open, x, y, codes.length]);

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

  if (!open || typeof document === "undefined" || codes.length === 0) return null;

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-[200] min-w-[220px] py-1.5 px-1.5 rounded-xl border border-white/[0.10] bg-bg-panel/95 shadow-xl backdrop-blur-md"
      style={{ left: pos.left, top: pos.top }}
      onClick={e => e.stopPropagation()}
      onContextMenu={e => e.preventDefault()}
    >
      <p className="px-3 py-1.5 text-xs font-mono text-indigo-300 truncate" title={codes.join(", ")}>
        {multi ? `${codes.length}개 선택` : codes[0]}
      </p>
      <MenuDivider />
      <MenuItem
        icon={<FileAudio className="w-4 h-4 text-indigo-300 shrink-0" />}
        label={multi ? `${labelPrefix} STT 큐에 추가` : "STT 큐에 추가"}
        onClick={() => {
          onClose();
          onAddStt();
        }}
      />
      <MenuItem
        icon={<Languages className="w-4 h-4 text-violet-300 shrink-0" />}
        label={multi ? `${labelPrefix} 번역 큐에 추가` : "번역 큐에 추가"}
        onClick={() => {
          onClose();
          onAddSubtitle();
        }}
      />
      {onGrokStory && (
        <MenuItem
          icon={<Sparkles className="w-4 h-4 text-amber-300 shrink-0" />}
          label={multi ? `${labelPrefix} Grok 스토리` : "Grok 스토리 생성"}
          onClick={() => {
            onClose();
            onGrokStory();
          }}
        />
      )}
      {(onCrawl || onRecrawl) && <MenuDivider />}
      {onCrawl && (
        <MenuItem
          icon={<Download className="w-4 h-4 text-emerald-300 shrink-0" />}
          label={multi ? `${labelPrefix} 크롤링` : "크롤링"}
          onClick={() => {
            onClose();
            onCrawl();
          }}
        />
      )}
      {onRecrawl && (
        <MenuItem
          icon={<RefreshCw className="w-4 h-4 text-orange-300 shrink-0" />}
          label={multi ? `${labelPrefix} 재크롤링` : "재크롤링"}
          onClick={() => {
            onClose();
            onRecrawl();
          }}
        />
      )}
      {onToggleLike && (
        <MenuItem
          icon={<Heart className={cn("w-4 h-4 shrink-0", !multi && userLiked ? "text-rose-400 fill-current" : "text-rose-300")} />}
          label={multi ? `${labelPrefix} 좋아요 토글` : (userLiked ? "좋아요 해제" : "좋아요")}
          onClick={() => {
            onClose();
            onToggleLike();
          }}
        />
      )}
      {onToggleWatchLater && (
        <MenuItem
          icon={<Bookmark className={cn("w-4 h-4 shrink-0", !multi && watchLater ? "text-sky-400 fill-current" : "text-sky-300")} />}
          label={multi ? `${labelPrefix} 나중에 볼 토글` : (watchLater ? "나중에 볼 해제" : "나중에 볼")}
          onClick={() => {
            onClose();
            onToggleWatchLater();
          }}
        />
      )}
      {!multi && hasFolder && (onPlay || onOpenFolder) && (
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
      {!multi && onOpenDetail && (
        <>
          <MenuDivider />
          <MenuItem
            icon={<ScanEye className="w-4 h-4 text-muted-foreground shrink-0" />}
            label="상세 보기"
            onClick={() => {
              onClose();
              onOpenDetail();
            }}
          />
        </>
      )}
    </div>,
    document.body,
  );
}
