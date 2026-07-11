import { memo, useEffect, useState, useCallback } from "react";
import { FolderOpen, Heart, MoreVertical, Play } from "lucide-react";
import { cn } from "@/lib/utils";
import { PosterHoverPreview } from "@/components/library/PosterHoverPreview";
import { PosterCardContextMenu } from "@/components/library/PosterCardContextMenu";
import type { ProcessingKind } from "@/api/processing";

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
  onClick?: () => void;
  onOpenFolder?: () => void;
  onPlay?: () => void;
  onActorClick?: (name: string) => void;
  onAddToProcessing?: (kind: ProcessingKind) => void;
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
  onClick,
  onOpenFolder,
  onPlay,
  onActorClick,
  onAddToProcessing,
}: PosterCardProps) {
  const [imgError, setImgError] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPos, setMenuPos] = useState({ x: 0, y: 0 });

  const openMenuAt = useCallback((clientX: number, clientY: number) => {
    setMenuPos({ x: clientX, y: clientY });
    setMenuOpen(true);
  }, []);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    openMenuAt(e.clientX, e.clientY);
  }, [openMenuAt]);
  const showImage = coverSrc && !imgError;

  useEffect(() => {
    setImgError(false);
  }, [coverSrc]);

  return (
    <div
      role="button"
      tabIndex={0}
      data-poster-card
      data-no-drag-scroll
      onClick={e => {
        e.stopPropagation();
        onClick?.();
      }}
      onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick?.();
        }
      }}
      onContextMenu={handleContextMenu}
      style={delay > 0 ? { animationDelay: `${delay}ms` } : undefined}
      className={cn(
        "group flex flex-col rounded-xl border border-white/[0.08] overflow-hidden cursor-pointer",
        "bg-bg-card hover:border-white/[0.16] hover:shadow-hover",
        "transition-all duration-200 text-left",
        delay > 0 && "animate-scale-in",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50",
      )}
    >
      {/* 표지 — 높이는 이미지에 맞춤 (contain 여백으로 텍스트와 벌어지지 않게) */}
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

        {hasFolder && (
          <div className="absolute top-2.5 right-2.5 flex flex-col gap-1.5">
            {onPlay && (
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
          </div>
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
              "absolute w-8 h-8 rounded-full flex items-center justify-center shadow-lg transition-all",
              "bg-black/50 hover:bg-black/70 text-white/90 hover:text-white",
              "opacity-0 group-hover:opacity-100",
              sceneCount > 0 ? "top-12 left-2.5" : "top-2.5 left-2.5",
            )}
          >
            <MoreVertical className="w-4 h-4" />
          </button>
        )}

        {sceneCount > 0 && (
          <div className="absolute top-2.5 left-2.5 px-2.5 py-1 rounded-lg bg-violet-500/90 text-white text-base font-bold shadow-lg">
            씬 {sceneCount}
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
          productCode={productCode}
          hasFolder={!!hasFolder}
          onClose={() => setMenuOpen(false)}
          onAddStt={() => onAddToProcessing("stt")}
          onAddSubtitle={() => onAddToProcessing("subtitle")}
          onPlay={onPlay}
          onOpenFolder={onOpenFolder}
          onOpenDetail={() => onClick?.()}
        />
      )}

      {/* 품번 · 메타 */}
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
