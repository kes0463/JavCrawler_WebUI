import { memo, useEffect, useRef, useState, useCallback } from "react";
import { Bookmark, Check, FolderOpen, Heart, MoreVertical, Play } from "lucide-react";
import { cn } from "@/lib/utils";
import { PosterHoverPreview } from "@/components/library/PosterHoverPreview";
import { PosterCardContextMenu } from "@/components/library/PosterCardContextMenu";
import type { ProcessingKind } from "@/api/processing";

/** 길게 눌러 선택 모드 진입 (ms) */
export const POSTER_LONG_PRESS_MS = 2000;

interface PosterCardProps {
  productCode: string;
  coverSrc?: string;
  previewSrc?: string;
  previewMedia?: "mp4" | "webp" | null;
  hasPreview?: boolean;
  hasFolder?: boolean;
  hasMeta?: boolean;
  title?: string | null;
  actors?: string | null;
  genres?: string | null;
  delay?: number;
  sceneCount?: number;
  favoriteScore?: number;
  hasSubtitle?: boolean;
  hasHardcodedSubtitle?: boolean;
  hasMosaicRemoved?: boolean;
  userLiked?: boolean;
  watchLater?: boolean;
  selected?: boolean;
  selectionMode?: boolean;
  /** 2초 길게 누르기 → 선택 모드 진입 */
  onLongPressSelect?: () => void;
  /** 선택 모드에서 클릭 시 토글 */
  onToggleSelect?: () => void;
  /**
   * 우클릭/메뉴 시 대상 품번 목록.
   * 선택 모드에서 이 카드가 선택된 경우 전체 선택 목록을 반환하면 됨.
   */
  resolveContextMenuProductCodes?: (clickedCode: string) => string[];
  onClick?: () => void;
  onOpenFolder?: () => void;
  onPlay?: () => void;
  onActorClick?: (name: string) => void;
  onAddToProcessing?: (kind: ProcessingKind, codes: string[]) => void;
  onGrokStory?: (codes: string[]) => void;
  onToggleLike?: (codes: string[]) => void;
  onToggleWatchLater?: (codes: string[]) => void;
}

function parseActorNames(actors: string): string[] {
  return actors.split(",").map(s => s.trim()).filter(Boolean);
}

export const PosterCard = memo(function PosterCard({
  productCode,
  coverSrc,
  previewSrc,
  previewMedia,
  hasPreview = false,
  hasFolder,
  hasMeta = true,
  title,
  actors,
  genres,
  delay = 0,
  sceneCount = 0,
  favoriteScore = 0,
  hasSubtitle = false,
  hasHardcodedSubtitle = false,
  hasMosaicRemoved = false,
  userLiked = false,
  watchLater = false,
  selected = false,
  selectionMode = false,
  onLongPressSelect,
  onToggleSelect,
  resolveContextMenuProductCodes,
  onClick,
  onOpenFolder,
  onPlay,
  onActorClick,
  onAddToProcessing,
  onGrokStory,
  onToggleLike,
  onToggleWatchLater,
}: PosterCardProps) {
  const [imgError, setImgError] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPos, setMenuPos] = useState({ x: 0, y: 0 });
  const [menuCodes, setMenuCodes] = useState<string[]>([productCode]);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);
  const pointerStart = useRef<{ x: number; y: number } | null>(null);

  const clearLongPress = useCallback(() => {
    if (longPressTimer.current != null) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
    pointerStart.current = null;
  }, []);

  const openMenuAt = useCallback((clientX: number, clientY: number) => {
    const codes =
      resolveContextMenuProductCodes?.(productCode) ?? [productCode];
    setMenuCodes(codes.length > 0 ? codes : [productCode]);
    setMenuPos({ x: clientX, y: clientY });
    setMenuOpen(true);
  }, [productCode, resolveContextMenuProductCodes]);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    clearLongPress();
    openMenuAt(e.clientX, e.clientY);
  }, [clearLongPress, openMenuAt]);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0 || !onLongPressSelect) return;
    longPressFired.current = false;
    pointerStart.current = { x: e.clientX, y: e.clientY };
    clearLongPress();
    longPressTimer.current = setTimeout(() => {
      longPressFired.current = true;
      longPressTimer.current = null;
      onLongPressSelect();
    }, POSTER_LONG_PRESS_MS);
  }, [clearLongPress, onLongPressSelect]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!pointerStart.current || longPressTimer.current == null) return;
    const dx = Math.abs(e.clientX - pointerStart.current.x);
    const dy = Math.abs(e.clientY - pointerStart.current.y);
    if (dx > 12 || dy > 12) clearLongPress();
  }, [clearLongPress]);

  const handlePointerUpOrCancel = useCallback(() => {
    clearLongPress();
  }, [clearLongPress]);

  useEffect(() => () => clearLongPress(), [clearLongPress]);

  const showImage = coverSrc && !imgError;

  useEffect(() => {
    setImgError(false);
  }, [coverSrc]);

  const handleActivate = useCallback(() => {
    if (longPressFired.current) {
      longPressFired.current = false;
      return;
    }
    if (selectionMode) {
      onToggleSelect?.();
      return;
    }
    onClick?.();
  }, [selectionMode, onToggleSelect, onClick]);

  return (
    <div
      role="button"
      tabIndex={0}
      data-poster-card
      data-no-drag-scroll
      aria-pressed={selectionMode ? selected : undefined}
      onClick={e => {
        e.stopPropagation();
        handleActivate();
      }}
      onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleActivate();
        }
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUpOrCancel}
      onPointerCancel={handlePointerUpOrCancel}
      onPointerLeave={handlePointerUpOrCancel}
      onContextMenu={handleContextMenu}
      style={delay > 0 ? { animationDelay: `${delay}ms` } : undefined}
      className={cn(
        "group flex flex-col rounded-xl border overflow-hidden cursor-pointer",
        "bg-bg-card hover:shadow-hover",
        "transition-all duration-200 text-left",
        delay > 0 && "animate-scale-in",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50",
        selected
          ? "border-indigo-400/70 ring-2 ring-indigo-400/40 shadow-[0_0_0_1px_rgba(129,140,248,0.35)]"
          : "border-white/[0.08] hover:border-white/[0.16]",
      )}
    >
      <div className="relative w-full bg-[#0a0a12]">
        <PosterHoverPreview
          productCode={productCode}
          coverSrc={coverSrc}
          previewSrc={previewSrc}
          previewMedia={previewMedia}
          hasPreview={hasPreview}
          alt={productCode}
          showCover={!!showImage}
          onCoverError={() => setImgError(true)}
        />

        {selected && (
          <div className="absolute top-2.5 left-2.5 z-20 w-7 h-7 rounded-full bg-indigo-500 flex items-center justify-center shadow-lg">
            <Check className="w-4 h-4 text-white" strokeWidth={3} />
          </div>
        )}

        <div className="absolute top-2.5 right-2.5 flex flex-col gap-1.5 z-10 items-end">
          {hasFolder && onPlay && (
            <button
              type="button"
              title="재생"
              onClick={e => {
                e.stopPropagation();
                onPlay();
              }}
              className="w-8 h-8 rounded-full bg-emerald-500/90 hover:bg-emerald-400 flex items-center justify-center shadow-lg transition-colors"
            >
              <Play className="w-4 h-4 text-white ml-0.5" />
            </button>
          )}
          {hasFolder && (
            <button
              type="button"
              title="폴더 열기"
              onClick={e => {
                e.stopPropagation();
                onOpenFolder?.();
              }}
              className="w-8 h-8 rounded-full bg-indigo-500/80 hover:bg-indigo-400 flex items-center justify-center shadow-lg transition-colors"
            >
              <FolderOpen className="w-4 h-4 text-white" />
            </button>
          )}
          {onAddToProcessing && (
            <button
              type="button"
              title="메뉴"
              onClick={e => {
                e.stopPropagation();
                const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
                openMenuAt(rect.right, rect.bottom + 4);
              }}
              className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center shadow-lg transition-all",
                "bg-black/50 hover:bg-black/70 text-white/90 hover:text-white",
                "opacity-0 group-hover:opacity-100",
                selectionMode && "opacity-100",
              )}
            >
              <MoreVertical className="w-4 h-4" />
            </button>
          )}
        </div>

        {(sceneCount > 0 || userLiked || watchLater) && (
          <div className={cn(
            "absolute flex flex-col items-start gap-1.5 max-w-[70%]",
            selected ? "top-11 left-2.5" : "top-2.5 left-2.5",
          )}>
            {sceneCount > 0 && (
              <div className="px-2.5 py-1 rounded-lg bg-violet-500/90 text-white text-base font-bold shadow-lg">
                씬 {sceneCount}
              </div>
            )}
            {userLiked && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-500/95 text-white text-sm font-bold shadow-lg">
                <Heart className="w-3.5 h-3.5 fill-current" />
                좋아요
              </span>
            )}
            {watchLater && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-sky-500/95 text-white text-sm font-bold shadow-lg">
                <Bookmark className="w-3.5 h-3.5 fill-current" />
                나중에
              </span>
            )}
          </div>
        )}

        {favoriteScore > 0 && (
          <div className="absolute bottom-2.5 left-2.5 px-2.5 py-1 rounded-lg bg-rose-500/90 text-white text-base font-bold shadow-lg flex items-center gap-1 tabular-nums">
            <Heart className="w-3.5 h-3.5 fill-current shrink-0" />
            {favoriteScore.toLocaleString()}
          </div>
        )}

        {(hasSubtitle || hasHardcodedSubtitle || hasMosaicRemoved) && (
          <div className="absolute bottom-2.5 right-2.5 flex flex-col items-end gap-1.5 max-w-[85%]">
            {hasHardcodedSubtitle && (
              <span className="px-3.5 py-2 rounded-lg bg-amber-500/95 text-white text-lg font-bold shadow-lg leading-tight">
                자체자막
              </span>
            )}
            {hasMosaicRemoved && (
              <span className="px-3.5 py-2 rounded-lg bg-cyan-500/95 text-white text-lg font-bold shadow-lg leading-tight">
                모파
              </span>
            )}
            {hasSubtitle && (
              <span className="px-3.5 py-2 rounded-lg bg-emerald-500/95 text-white text-lg font-bold shadow-lg leading-tight">
                자막
              </span>
            )}
          </div>
        )}
      </div>

      {onAddToProcessing && (
        <PosterCardContextMenu
          open={menuOpen}
          x={menuPos.x}
          y={menuPos.y}
          productCodes={menuCodes}
          hasFolder={!!hasFolder && menuCodes.length === 1}
          onClose={() => setMenuOpen(false)}
          onAddStt={() => onAddToProcessing("stt", menuCodes)}
          onAddSubtitle={() => onAddToProcessing("subtitle", menuCodes)}
          onGrokStory={onGrokStory ? () => onGrokStory(menuCodes) : undefined}
          onToggleLike={onToggleLike ? () => onToggleLike(menuCodes) : undefined}
          onToggleWatchLater={onToggleWatchLater ? () => onToggleWatchLater(menuCodes) : undefined}
          userLiked={userLiked}
          watchLater={watchLater}
          onPlay={menuCodes.length === 1 ? onPlay : undefined}
          onOpenFolder={menuCodes.length === 1 ? onOpenFolder : undefined}
          onOpenDetail={menuCodes.length === 1 ? () => onClick?.() : undefined}
        />
      )}

      <div className="px-3.5 pt-2 pb-2.5 border-t border-white/[0.06] bg-bg-panel/80">
        <p className="text-2xl font-mono font-bold text-indigo-300 leading-tight break-all">
          {productCode}
        </p>
        {!hasMeta && (
          <p className="text-lg font-medium text-amber-400 mt-1">미수집</p>
        )}
        {title && hasMeta && (
          <p className="text-lg text-[#d0d0e8] mt-1 line-clamp-2 leading-snug group-hover:text-white">
            {title}
          </p>
        )}
        {actors && hasMeta && (
          <p className="text-base text-muted-foreground mt-1 line-clamp-1 leading-snug group-hover:text-[#c8c8e0]">
            {onActorClick
              ? parseActorNames(actors).map((name, i, arr) => (
                  <span key={`${name}-${i}`}>
                    <button
                      type="button"
                      onClick={e => {
                        e.stopPropagation();
                        onActorClick(name);
                      }}
                      className="hover:text-violet-300 hover:underline underline-offset-2"
                    >
                      {name}
                    </button>
                    {i < arr.length - 1 && ", "}
                  </span>
                ))
              : actors}
          </p>
        )}
        {genres && hasMeta && (
          <p className="text-base text-indigo-300/90 mt-0.5 line-clamp-1 leading-snug group-hover:text-indigo-200">
            {genres}
          </p>
        )}
      </div>
    </div>
  );
});
