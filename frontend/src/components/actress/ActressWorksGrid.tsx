import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Square, SquareCheck, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  coverUrl,
  openLibraryFolder,
  previewUrl,
  startGrokStory,
  startGrokStoryBatch,
  toggleLibraryLike,
  toggleLibraryWatchLater,
} from "@/api/library";
import type { ActressWork } from "@/api/actress";
import type { ProcessingKind } from "@/api/processing";
import { PosterCard } from "@/components/library/PosterCard";
import { GlassCard } from "@/components/ui/GlassCard";
import { getScrollableAncestor, useInfiniteScrollNearEnd } from "@/hooks/useGlobalDragScroll";
import { useLibraryProcessingActions } from "@/hooks/useLibraryProcessingActions";
import { useSelection } from "@/hooks/useSelection";
import { usePlayer } from "@/contexts/PlayerContext";
import { useToast } from "@/contexts/ToastContext";

type WorkSortKey = "product_code" | "release_date" | "favorite_score" | "user_rating";

const SORT_OPTIONS: { value: WorkSortKey; label: string }[] = [
  { value: "product_code", label: "품번" },
  { value: "release_date", label: "출시일" },
  { value: "favorite_score", label: "좋아요" },
  { value: "user_rating", label: "내 점수" },
];

const PAGE_SIZE = 48;
const workKey = (w: ActressWork) => w.product_code.toUpperCase();

const controlClass =
  "h-10 px-3 text-base rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] focus:outline-none";

interface ActressWorksGridProps {
  works: ActressWork[];
  genres: string[];
  onWorkClick: (productCode: string) => void;
  onWorksChange?: (works: ActressWork[]) => void;
}

function compareWorks(a: ActressWork, b: ActressWork, key: WorkSortKey, asc: boolean): number {
  let cmp = 0;
  if (key === "product_code") {
    cmp = (a.product_code || "").localeCompare(b.product_code || "");
  } else if (key === "release_date") {
    cmp = (a.release_date || "").localeCompare(b.release_date || "");
  } else if (key === "favorite_score") {
    cmp = (a.favorite_score ?? 0) - (b.favorite_score ?? 0);
  } else {
    cmp = (a.user_rating ?? 0) - (b.user_rating ?? 0);
  }
  return asc ? cmp : -cmp;
}

export function ActressWorksGrid({
  works,
  genres,
  onWorkClick,
  onWorksChange,
}: ActressWorksGridProps) {
  const { showToast } = useToast();
  const { openPlayer } = usePlayer();
  const { enqueueLibraryProducts } = useLibraryProcessingActions();

  const [genreFilter, setGenreFilter] = useState("");
  const [sortKey, setSortKey] = useState<WorkSortKey>("release_date");
  const [sortAsc, setSortAsc] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const loadMoreSentinelRef = useRef<HTMLDivElement | null>(null);
  const [scrollRoot, setScrollRoot] = useState<HTMLElement | null>(null);

  const filtered = useMemo(() => {
    let list = works;
    if (genreFilter) {
      list = list.filter(w =>
        (w.genres_ko || "")
          .split(",")
          .map(g => g.trim())
          .includes(genreFilter),
      );
    }
    return [...list].sort((a, b) => compareWorks(a, b, sortKey, sortAsc));
  }, [works, genreFilter, sortKey, sortAsc]);

  const selection = useSelection(filtered, workKey);
  const selectionMode = selection.count > 0;

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

  const requestLoadMore = useCallback(() => {
    setVisibleCount(c => (c >= filtered.length ? c : Math.min(c + PAGE_SIZE, filtered.length)));
  }, [filtered.length]);

  useEffect(() => {
    const sentinel = loadMoreSentinelRef.current;
    if (!sentinel) return;
    setScrollRoot(getScrollableAncestor(sentinel));
  }, [filtered.length, visibleCount]);

  useInfiniteScrollNearEnd(scrollRoot, hasMore, requestLoadMore);

  useEffect(() => {
    if (!scrollRoot) return;
    const el = loadMoreSentinelRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) requestLoadMore();
      },
      { root: scrollRoot, rootMargin: "320px", threshold: 0 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [scrollRoot, requestLoadMore, filtered.length, visibleCount]);

  // 필터/정렬 변경 시 선택 초기화
  const filterKey = `${genreFilter}|${sortKey}|${sortAsc}`;
  const filterKeyRef = useRef(filterKey);
  useEffect(() => {
    if (filterKeyRef.current === filterKey) return;
    filterKeyRef.current = filterKey;
    selection.clearAll();
    setVisibleCount(PAGE_SIZE);
  }, [filterKey, selection.clearAll]);

  useEffect(() => {
    if (!selectionMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") selection.clearAll();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectionMode, selection.clearAll]);

  const resolveContextMenuProductCodes = useCallback((clickedCode: string) => {
    const key = clickedCode.toUpperCase();
    if (selection.count > 0 && selection.isSelectedKey(key)) {
      return selection.selectedKeys;
    }
    return [clickedCode];
  }, [selection.count, selection.isSelectedKey, selection.selectedKeys]);

  const patchWorkFlags = useCallback((productCode: string, flags: { user_liked: boolean; watch_later: boolean }) => {
    const pc = productCode.toUpperCase();
    onWorksChange?.(
      works.map(w =>
        w.product_code.toUpperCase() === pc
          ? { ...w, user_liked: flags.user_liked, watch_later: flags.watch_later }
          : w,
      ),
    );
  }, [onWorksChange, works]);

  const handleAddToProcessing = useCallback((codes: string[], kind: ProcessingKind) => {
    void enqueueLibraryProducts(codes, kind);
  }, [enqueueLibraryProducts]);

  const handleGrokStory = useCallback((codes: string[]) => {
    const run =
      codes.length === 1
        ? startGrokStory(codes[0], false)
        : startGrokStoryBatch(codes, false);
    void run
      .then(res => showToast(res.message, res.ok && res.queued > 0 ? "success" : res.ok ? "info" : "warn"))
      .catch(err => showToast(err instanceof Error ? err.message : "Grok 스토리 시작 실패", "error"));
  }, [showToast]);

  const handleToggleLike = useCallback((codes: string[]) => {
    void (async () => {
      try {
        for (const code of codes) {
          const res = await toggleLibraryLike(code);
          patchWorkFlags(code, res);
        }
        showToast(
          codes.length === 1 ? `${codes[0]}: 좋아요 토글` : `${codes.length}개 좋아요 토글`,
          "success",
        );
      } catch (err) {
        showToast(err instanceof Error ? err.message : "좋아요 변경 실패", "error");
      }
    })();
  }, [patchWorkFlags, showToast]);

  const handleToggleWatchLater = useCallback((codes: string[]) => {
    void (async () => {
      try {
        for (const code of codes) {
          const res = await toggleLibraryWatchLater(code);
          patchWorkFlags(code, res);
        }
        showToast(
          codes.length === 1 ? `${codes[0]}: 나중에 볼 토글` : `${codes.length}개 나중에 볼 토글`,
          "success",
        );
      } catch (err) {
        showToast(err instanceof Error ? err.message : "나중에 볼 변경 실패", "error");
      }
    })();
  }, [patchWorkFlags, showToast]);

  const handleOpenFolder = useCallback((productCode: string) => {
    openLibraryFolder(productCode)
      .then(res => showToast(`폴더 열림: ${res.path}`, "success"))
      .catch(err => showToast(err instanceof Error ? err.message : "폴더 열기 실패", "error"));
  }, [showToast]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <p className="text-lg font-semibold mr-2">
          출연작 <span className="text-slate-400 font-normal">{filtered.length}</span>
        </p>
        <select
          value={sortKey}
          onChange={e => setSortKey(e.target.value as WorkSortKey)}
          className={controlClass}
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setSortAsc(a => !a)}
          className={cn(controlClass, "hover:text-white transition-colors")}
        >
          {sortAsc ? "↑ 오름차순" : "↓ 내림차순"}
        </button>
      </div>

      {genres.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          <button
            type="button"
            onClick={() => setGenreFilter("")}
            className={cn(
              "px-2 py-0.5 rounded-full text-xs border transition-colors",
              !genreFilter
                ? "bg-violet-500/30 border-violet-500/50 text-violet-100"
                : "bg-white/[0.04] border-white/[0.08] text-slate-400 hover:bg-white/[0.08]",
            )}
          >
            전체
          </button>
          {genres.map(g => (
            <button
              key={g}
              type="button"
              onClick={() => setGenreFilter(prev => (prev === g ? "" : g))}
              className={cn(
                "px-2 py-0.5 rounded-full text-xs border transition-colors",
                genreFilter === g
                  ? "bg-indigo-500/30 border-indigo-500/50 text-indigo-100"
                  : "bg-indigo-500/15 border-transparent text-indigo-200 hover:bg-indigo-500/25",
              )}
            >
              {g}
            </button>
          ))}
        </div>
      )}

      {(selectionMode || filtered.length > 0) && (
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <button
            type="button"
            onClick={selection.allSelected ? selection.clearAll : selection.selectAll}
            className={cn(
              "h-9 px-3 text-sm rounded-xl border transition-colors flex items-center gap-1.5",
              selection.allSelected
                ? "bg-indigo-500/20 border-indigo-500/40 text-indigo-200"
                : "bg-bg-surface border-white/[0.08] text-muted-foreground hover:text-white",
            )}
          >
            {selection.allSelected
              ? <SquareCheck className="w-3.5 h-3.5 text-indigo-300" />
              : <Square className="w-3.5 h-3.5" />}
            {selection.allSelected ? "전체 해제" : "전체 선택"}
          </button>
          {selectionMode && (
            <GlassCard
              variant="accent"
              noPadding
              className="px-3 py-1.5 flex items-center gap-2 animate-slide-in"
            >
              <span className="text-sm font-medium text-indigo-300">
                {selection.count}개 선택됨
              </span>
              <span className="text-xs text-muted-foreground hidden sm:inline">
                우클릭으로 일괄 작업 · Esc 해제
              </span>
              <button
                type="button"
                title="선택 해제"
                onClick={selection.clearAll}
                className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:text-white hover:bg-white/[0.08]"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </GlassCard>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-3">
        {visible.map(w => {
          const hasFolder = !!(w.folder_path && w.folder_path.trim());
          const codeKey = workKey(w);
          return (
            <PosterCard
              key={w.product_code}
              productCode={w.product_code}
              coverSrc={w.product_code ? coverUrl(w.product_code, w.updated_at) : undefined}
              previewSrc={w.has_preview && w.product_code ? previewUrl(w.product_code, w.updated_at ?? "") : undefined}
              previewMedia={w.preview_media ?? undefined}
              hasPreview={!!w.has_preview}
              hasFolder={hasFolder}
              hasMeta={!!(w.title_ko || w.actors_ko)}
              title={w.title_ko || null}
              actors={w.actors_ko || null}
              genres={w.genres_ko || null}
              favoriteScore={Number(w.favorite_score) || 0}
              hasSubtitle={!!w.has_subtitle}
              hasHardcodedSubtitle={!!w.has_hardcoded_subtitle}
              hasMosaicRemoved={!!w.has_mosaic_removed}
              userLiked={!!w.user_liked}
              watchLater={!!w.watch_later}
              selected={selection.isSelectedKey(codeKey)}
              selectionMode={selectionMode}
              onLongPressSelect={() => selection.select(w)}
              onToggleSelect={() => selection.toggle(w)}
              resolveContextMenuProductCodes={resolveContextMenuProductCodes}
              onClick={() => onWorkClick(w.product_code)}
              onPlay={hasFolder ? () => void openPlayer(w.product_code) : undefined}
              onOpenFolder={() => handleOpenFolder(w.product_code)}
              onAddToProcessing={(kind, codes) => handleAddToProcessing(codes, kind)}
              onGrokStory={codes => handleGrokStory(codes)}
              onToggleLike={codes => handleToggleLike(codes)}
              onToggleWatchLater={codes => handleToggleWatchLater(codes)}
            />
          );
        })}
      </div>

      {filtered.length === 0 && (
        <p className="text-center text-slate-500 py-8 text-sm">출연작이 없습니다.</p>
      )}

      {hasMore && (
        <div ref={loadMoreSentinelRef} className="h-px w-full mt-4" aria-hidden />
      )}

      {!hasMore && filtered.length > 0 && (
        <p className="text-center text-sm text-slate-500 py-3">
          전체 {filtered.length.toLocaleString()}작품
        </p>
      )}
    </div>
  );
}
