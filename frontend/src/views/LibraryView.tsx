import { useState, useEffect, useCallback, useRef } from "react";
import { Search, SlidersHorizontal, FolderOpen, FolderX, RefreshCw, Subtitles, Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchLibraryListed, fetchLibraryGenresResilient, fetchLibraryStats, coverUrl, previewUrl, openLibraryFolder, hasRealLibraryMetadata, clearLibraryGenreScanCache, probeLibraryGenreFilterSupport, prefetchLibraryClientIndex, isClientLibraryIndexReady, warmupLibraryEmbeddings } from "@/api/library";
import type { LibraryItem, LibraryStats, LibraryQuery, LibraryGenreItem, LibrarySearchMode } from "@/api/library";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { PosterCard } from "@/components/library/PosterCard";
import { GenreFilterBar, GenreFilterChipPanel } from "@/components/library/GenreFilterPanel";
import { LibraryDetailPanel } from "@/components/library/LibraryDetailPanel";
import { useToast } from "@/contexts/ToastContext";
import { usePlayer } from "@/contexts/PlayerContext";
import { useNavigation } from "@/contexts/NavigationContext";
import { useLibraryProcessingActions } from "@/hooks/useLibraryProcessingActions";
import type { ProcessingKind } from "@/api/processing";
import { getScrollableAncestor, useInfiniteScrollNearEnd } from "@/hooks/useGlobalDragScroll";
import {
  isLibrarySessionFresh,
  loadLibrarySession,
  useLibrarySessionCache,
} from "@/hooks/useLibrarySessionCache";

const SORT_OPTIONS = [
  { label: "최근 수정", value: "updated_at" },
  { label: "발매일", value: "release_date" },
  { label: "품번", value: "product_code" },
  { label: "제목", value: "title_ko" },
  { label: "좋아요", value: "favorite_score" },
] as const;

const LIBRARY_PAGE_SIZE = 64;
const LIBRARY_PREFETCH_MARGIN_PX = 1600;
const STATS_SESSION_KEY = "javstory.library.stats.v1";

const DEFAULT_QUERY: LibraryQuery = {
  q: "",
  page: 1,
  per_page: LIBRARY_PAGE_SIZE,
  sort: "updated_at",
  order: "desc",
};

function loadStatsSession(): LibraryStats | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STATS_SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as LibraryStats;
  } catch {
    return null;
  }
}

function saveStatsSession(stats: LibraryStats) {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(STATS_SESSION_KEY, JSON.stringify(stats));
  } catch {
    /* ignore */
  }
}

function bootFromSession() {
  const session = loadLibrarySession();
  if (!session?.items.length) {
    return {
      query: DEFAULT_QUERY,
      items: [] as LibraryItem[],
      total: 0,
      scrollTop: 0,
      fromSession: false,
    };
  }
  return {
    query: { ...DEFAULT_QUERY, ...session.query, page: session.query.page ?? 1 },
    items: session.items,
    total: session.total,
    scrollTop: session.scrollTop,
    fromSession: isLibrarySessionFresh(session, session.query),
  };
}

export default function LibraryView() {
  const boot = useRef(bootFromSession()).current;
  const { showToast } = useToast();
  const { openPlayer } = usePlayer();
  const { libraryDetailSku, openLibraryDetail, closeLibraryDetail, openActressByName, currentView } = useNavigation();
  const { enqueueLibraryProducts } = useLibraryProcessingActions();

  const [query, setQuery] = useState<LibraryQuery>(boot.query);
  const [items, setItems] = useState<LibraryItem[]>(boot.items);
  const [total, setTotal] = useState(boot.total);
  const [stats, setStats] = useState<LibraryStats | null>(() => loadStatsSession());
  const [loading, setLoading] = useState(!boot.items.length);
  const [statsLoading, setStatsLoading] = useState(!loadStatsSession());
  const [statsRefreshing, setStatsRefreshing] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const appendRef = useRef(false);
  const apiWarnedRef = useRef(false);
  const loadMoreSentinelRef = useRef<HTMLDivElement | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [scrollRoot, setScrollRoot] = useState<HTMLElement | null>(null);
  const [coverRev, setCoverRev] = useState<Record<string, number>>({});
  const [genreOptions, setGenreOptions] = useState<LibraryGenreItem[]>([]);
  const [genresLoading, setGenresLoading] = useState(false);
  const [genreOpen, setGenreOpen] = useState(false);
  const [genreFiltering, setGenreFiltering] = useState(false);
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [searchModeUsed, setSearchModeUsed] = useState<string | null>(null);
  const genreApiWarnedRef = useRef(false);
  const skipInitialFetchRef = useRef(boot.fromSession);
  const pendingScrollRef = useRef(boot.scrollTop);
  const suppressCardAnimRef = useRef(boot.fromSession);
  const queryFilterKeyRef = useRef(
    JSON.stringify({ ...query, page: undefined }),
  );

  const { clearSession, restoreScroll } = useLibrarySessionCache(
    query,
    items,
    total,
    scrollRoot,
  );

  const refreshStats = useCallback((showSkeleton = true) => {
    if (showSkeleton && !stats) setStatsLoading(true);
    else setStatsRefreshing(true);
    fetchLibraryStats()
      .then(next => {
        setStats(next);
        saveStatsSession(next);
      })
      .finally(() => {
        setStatsLoading(false);
        setStatsRefreshing(false);
      });
  }, [stats]);

  useEffect(() => {
    const run = () => refreshStats(!stats);
    if (typeof requestIdleCallback !== "undefined") {
      const id = requestIdleCallback(run);
      return () => cancelIdleCallback(id);
    }
    const t = window.setTimeout(run, 0);
    return () => window.clearTimeout(t);
  }, [refreshStats, stats]);

  useEffect(() => {
    if (currentView !== "library") return;
    prefetchLibraryClientIndex();
    let cancelled = false;
    setGenresLoading(true);
    fetchLibraryGenresResilient()
      .then(({ genres, source }) => {
        if (cancelled) return;
        setGenreOptions(genres);
        if (source === "bootstrap" && !genreApiWarnedRef.current) {
          genreApiWarnedRef.current = true;
          showToast(
            "장르 목록을 라이브러리 전체에서 집계했습니다. webapi 재시작 시 더 빠르게 로드됩니다.",
            "info",
          );
        }
      })
      .catch(() => {
        if (!cancelled) setGenreOptions([]);
      })
      .finally(() => {
        if (!cancelled) setGenresLoading(false);
      });
    return () => { cancelled = true; };
  }, [currentView, showToast]);

  const handleCloseDetail = useCallback(() => {
    closeLibraryDetail();
  }, [closeLibraryDetail]);

  const handleActorClick = useCallback(async (name: string) => {
    closeLibraryDetail();
    try {
      await openActressByName(name);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "배우 정보를 불러오지 못했습니다.", "error");
    }
  }, [closeLibraryDetail, openActressByName, showToast]);

  const loadItems = useCallback((
    q: LibraryQuery,
    append = false,
    opts?: { silent?: boolean },
  ) => {
    const silent = opts?.silent ?? false;
    if (!silent) {
      if (append) setLoadingMore(true);
      else setLoading(true);
    }

    const apiQuery: LibraryQuery = {
      ...q,
      include_total: append ? false : true,
    };

    const run = async () => {
      const needsClientGenre =
        (q.genres?.length ?? 0) > 0 && !(await probeLibraryGenreFilterSupport());
      if (needsClientGenre && !append && !silent && !isClientLibraryIndexReady()) {
        setGenreFiltering(true);
      }

      try {
        const res = await fetchLibraryListed(apiQuery);
        const { items: newItems, total: t } = res;
        if (!append) {
          setSearchMessage(res.search_message ?? null);
          setSearchModeUsed(res.search_mode ?? null);
        }
        if (
          !append && !apiWarnedRef.current && newItems.length > 0
          && !("favorite_score" in newItems[0])
        ) {
          apiWarnedRef.current = true;
          showToast(
            "레거시 API에 연결된 것 같습니다. start_web.bat으로 webapi를 재시작해 주세요.",
            "warn",
          );
        }

        if (append) {
          setItems(prev => [...prev, ...newItems]);
          if (t > 0) setTotal(t);
        } else if (silent && (q.page ?? 1) === 1) {
          setItems(prev => {
            if (prev.length === 0) return newItems;
            const next = [...prev];
            newItems.forEach((item, i) => {
              next[i] = item;
            });
            return next.length >= newItems.length ? next : newItems;
          });
          if (t > 0) setTotal(t);
        } else {
          setItems(newItems);
          setTotal(t);
        }
      } catch (err) {
        if (!append && !silent) {
          setItems([]);
          setTotal(0);
          setSearchMessage(null);
          setSearchModeUsed(null);
        }
        if (!silent) {
          showToast(err instanceof Error ? err.message : "라이브러리 목록을 불러오지 못했습니다.", "error");
        }
      } finally {
        setGenreFiltering(false);
        setLoading(false);
        setLoadingMore(false);
      }
    };

    void run();
  }, [showToast]);

  useEffect(() => {
    const append = appendRef.current;
    appendRef.current = false;

    const filterKey = JSON.stringify({ ...query, page: undefined });
    const filterChanged = filterKey !== queryFilterKeyRef.current;
    if (filterChanged) {
      queryFilterKeyRef.current = filterKey;
      clearLibraryGenreScanCache();
      clearSession();
      skipInitialFetchRef.current = false;
      suppressCardAnimRef.current = false;
    }

    if (skipInitialFetchRef.current) {
      skipInitialFetchRef.current = false;
      loadItems({ ...query, page: 1 }, false, { silent: true });
      return;
    }

    loadItems(query, append);
  }, [query, loadItems, clearSession]);

  const [searchText, setSearchText] = useState(query.q ?? "");

  const handleSearch = (value: string) => {
    setSearchText(value);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setQuery(q => ({ ...q, q: value, page: 1 }));
    }, 350);
  };

  const requestLoadMore = useCallback(() => {
    if (loading || loadingMore || appendRef.current) return;
    if (items.length >= total) return;
    appendRef.current = true;
    setQuery(q => ({ ...q, page: (q.page ?? 1) + 1 }));
  }, [loading, loadingMore, items.length, total]);

  const hasMoreItems = !loading && items.length < total;
  useInfiniteScrollNearEnd(scrollRoot, hasMoreItems, requestLoadMore);

  useEffect(() => {
    if (currentView !== "library") return;
    const sentinel = loadMoreSentinelRef.current;
    if (!sentinel) return;
    setScrollRoot(getScrollableAncestor(sentinel));
  }, [currentView, items.length, loading]);

  useEffect(() => {
    if (!scrollRoot || currentView !== "library") return;
    scrollRoot.dataset.infiniteNearEndPx = String(LIBRARY_PREFETCH_MARGIN_PX);
    return () => {
      delete scrollRoot.dataset.infiniteNearEndPx;
    };
  }, [scrollRoot, currentView]);

  useEffect(() => {
    if (!scrollRoot || currentView !== "library") return;
    const el = loadMoreSentinelRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) requestLoadMore();
      },
      { root: scrollRoot, rootMargin: `${LIBRARY_PREFETCH_MARGIN_PX}px`, threshold: 0 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [requestLoadMore, items.length, total, scrollRoot, currentView]);

  useEffect(() => {
    if (currentView !== "library" || loading || loadingMore || appendRef.current) return;
    if (items.length >= total || total === 0) return;
    const el = loadMoreSentinelRef.current;
    const root = scrollRoot;
    if (!el || !root) return;
    const rootRect = root.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    if (elRect.top <= rootRect.bottom + LIBRARY_PREFETCH_MARGIN_PX) {
      requestLoadMore();
    }
  }, [currentView, items.length, loading, loadingMore, total, scrollRoot, requestLoadMore]);

  useEffect(() => {
    if (currentView !== "library" || !scrollRoot) return;
    if (pendingScrollRef.current > 0) {
      restoreScroll(pendingScrollRef.current, scrollRoot);
      pendingScrollRef.current = 0;
    }
  }, [currentView, scrollRoot, restoreScroll, items.length]);

  const handlePlay = useCallback((productCode: string) => {
    void openPlayer(productCode);
  }, [openPlayer]);

  const handleAddToProcessing = useCallback((productCode: string, kind: ProcessingKind) => {
    void enqueueLibraryProducts([productCode], kind);
  }, [enqueueLibraryProducts]);

  const handleDetailSaved = useCallback((updated: LibraryItem) => {
    const pc = updated.product_code.toUpperCase();
    setCoverRev(prev => ({ ...prev, [pc]: Date.now() }));
    setItems(prev =>
      prev.map(item =>
        item.product_code.toUpperCase() === pc
          ? { ...item, ...updated }
          : item,
      ),
    );
    refreshStats(false);
  }, [refreshStats]);

  const coverCacheKey = useCallback((item: LibraryItem) => {
    const pc = item.product_code.toUpperCase();
    return coverRev[pc] ?? item.updated_at ?? item.cover_image_local_path ?? undefined;
  }, [coverRev]);

  const handleOpenFolder = useCallback((productCode: string) => {
    openLibraryFolder(productCode)
      .then(res => showToast(`폴더 열림: ${res.path}`, "success"))
      .catch(err => showToast(err instanceof Error ? err.message : "폴더 열기 실패", "error"));
  }, [showToast]);

  const updateQueryFilter = useCallback((patch: Partial<LibraryQuery>) => {
    setQuery(q => ({ ...q, ...patch, page: 1 }));
  }, []);

  const toggleGenre = useCallback((name: string) => {
    setQuery(q => {
      const current = q.genres ?? [];
      const adding = !current.includes(name);
      const next = adding
        ? [...current, name]
        : current.filter(g => g !== name);
      if (adding) setGenreOpen(true);
      return {
        ...q,
        genres: next.length ? next : undefined,
        page: 1,
      };
    });
  }, []);

  const clearGenres = useCallback(() => {
    updateQueryFilter({ genres: undefined, genre_mode: undefined });
  }, [updateQueryFilter]);

  return (
    <div className="space-y-5">

      <div className="flex items-center gap-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 flex-1">
          {statsLoading && !stats
            ? [0, 1, 2, 3].map(i => <GlassCard key={i}><Skeleton className="h-8 w-full" /></GlassCard>)
            : [
                { label: "전체", value: stats?.total, color: "text-white" },
                { label: "메타데이터 완료", value: stats?.with_metadata, color: "text-emerald-400" },
                { label: "폴더 연결", value: stats?.with_folder, color: "text-indigo-400" },
                { label: "미수집", value: stats?.without_metadata, color: "text-amber-400" },
              ].map(({ label, value, color }) => (
                <GlassCard key={label} className="animate-scale-in">
                  <p className="text-sm text-muted-foreground">{label}</p>
                  <p className={cn("text-3xl font-bold tabular-nums mt-0.5", color)}>
                    {value?.toLocaleString() ?? "—"}
                  </p>
                </GlassCard>
              ))}
        </div>
        <button
          onClick={() => refreshStats(false)}
          title="통계 새로고침"
          className="h-9 w-9 shrink-0 rounded-xl flex items-center justify-center bg-bg-surface border border-white/[0.08] text-muted-foreground hover:text-white hover:border-white/[0.16] transition-all"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", statsRefreshing && "animate-spin")} />
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder={
              (query.search_mode ?? "auto") === "hybrid"
                ? "자연어로 검색… 예: 비 오는 날 실외"
                : (query.search_mode ?? "auto") === "keyword"
                  ? "품번, 제목, 배우 검색..."
                  : "품번·배우 또는 자연어 검색..."
            }
            value={searchText}
            onChange={e => handleSearch(e.target.value)}
            className={cn(
              "w-full h-10 pl-10 pr-4 text-base rounded-xl",
              "bg-bg-surface border border-white/[0.08] text-white placeholder:text-muted-foreground",
              "focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30",
              "transition-all duration-150",
            )}
          />
        </div>

        <select
          value={query.search_mode ?? "auto"}
          onChange={e => updateQueryFilter({ search_mode: e.target.value as LibrarySearchMode })}
          title="검색 모드"
          className="h-10 px-3 text-base rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] focus:outline-none"
        >
          <option value="auto">자동</option>
          <option value="keyword">키워드</option>
          <option value="hybrid">자연어</option>
        </select>

        <select
          value={query.sort}
          onChange={e => updateQueryFilter({ sort: e.target.value as LibraryQuery["sort"] })}
          className="h-10 px-3 text-base rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] focus:outline-none"
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <button
          onClick={() => updateQueryFilter({ order: query.order === "desc" ? "asc" : "desc" })}
          className="h-10 px-3 text-base rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] hover:text-white transition-colors"
        >
          {query.order === "desc" ? "↓ 내림차순" : "↑ 오름차순"}
        </button>

        <button
          onClick={() => updateQueryFilter({
            has_folder: query.has_folder === true ? undefined : true,
          })}
          className={cn(
            "h-10 px-3 text-base rounded-xl border transition-colors flex items-center gap-1.5",
            query.has_folder === true
              ? "bg-indigo-500/20 border-indigo-500/40 text-indigo-300"
              : "bg-bg-surface border-white/[0.08] text-muted-foreground hover:text-white",
          )}
        >
          <FolderOpen className="w-3.5 h-3.5" />
          폴더 있음
        </button>

        <button
          onClick={() => updateQueryFilter({
            has_folder: query.has_folder === false ? undefined : false,
          })}
          className={cn(
            "h-10 px-3 text-base rounded-xl border transition-colors flex items-center gap-1.5",
            query.has_folder === false
              ? "bg-orange-500/20 border-orange-500/40 text-orange-300"
              : "bg-bg-surface border-white/[0.08] text-muted-foreground hover:text-white",
          )}
        >
          <FolderX className="w-3.5 h-3.5" />
          폴더 없음
        </button>

        <button
          onClick={() => updateQueryFilter({
            has_metadata: query.has_metadata === false ? undefined : false,
          })}
          className={cn(
            "h-10 px-3 text-base rounded-xl border transition-colors flex items-center gap-1.5",
            query.has_metadata === false
              ? "bg-amber-500/20 border-amber-500/40 text-amber-300"
              : "bg-bg-surface border-white/[0.08] text-muted-foreground hover:text-white",
          )}
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          미수집만
        </button>

        <button
          onClick={() => updateQueryFilter({
            has_subtitle: query.has_subtitle ? undefined : true,
          })}
          className={cn(
            "h-10 px-3 text-base rounded-xl border transition-colors flex items-center gap-1.5",
            query.has_subtitle
              ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300"
              : "bg-bg-surface border-white/[0.08] text-muted-foreground hover:text-white",
          )}
        >
          <Subtitles className="w-3.5 h-3.5" />
          자막·자체자막
        </button>

        <button
          onClick={() => updateQueryFilter({
            has_mosaic_removed: query.has_mosaic_removed ? undefined : true,
          })}
          className={cn(
            "h-10 px-3 text-base rounded-xl border transition-colors flex items-center gap-1.5",
            query.has_mosaic_removed
              ? "bg-cyan-500/20 border-cyan-500/40 text-cyan-300"
              : "bg-bg-surface border-white/[0.08] text-muted-foreground hover:text-white",
          )}
        >
          <Layers className="w-3.5 h-3.5" />
          모자이크 제거
        </button>

        <GenreFilterBar
          open={genreOpen}
          onOpenChange={setGenreOpen}
          genres={genreOptions}
          selected={query.genres ?? []}
          mode={query.genre_mode ?? "and"}
          loading={genresLoading}
          onToggleGenre={toggleGenre}
          onModeChange={mode => updateQueryFilter({ genre_mode: mode })}
          onClear={clearGenres}
        />

        <span className="text-sm text-muted-foreground ml-auto tabular-nums">
          {items.length.toLocaleString()} / {total.toLocaleString()}건
          {searchModeUsed === "hybrid" && (query.q || "").trim() ? " · 자연어" : null}
        </span>
      </div>

      {searchMessage && (query.q || "").trim() && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-sm text-amber-100/90">
          <span className="flex-1 min-w-0">{searchMessage}</span>
          {searchMessage.includes("워밍업") && (
            <button
              type="button"
              className="shrink-0 h-8 px-3 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-100 text-xs"
              onClick={() => {
                void warmupLibraryEmbeddings(12)
                  .then(res => showToast(res.message, res.ok ? "success" : "warn"))
                  .catch(err => showToast(err instanceof Error ? err.message : "워밍업 실패", "error"));
              }}
            >
              임베딩 워밍업
            </button>
          )}
        </div>
      )}

      {genreOpen && (
        <GenreFilterChipPanel
          genres={genreOptions}
          selected={query.genres ?? []}
          mode={query.genre_mode ?? "and"}
          loading={genresLoading}
          onToggleGenre={toggleGenre}
          onModeChange={mode => updateQueryFilter({ genre_mode: mode })}
          onClear={clearGenres}
        />
      )}

      {genreFiltering && (
        <p className="text-sm text-violet-300/90 text-center py-1 animate-pulse">
          장르 필터 적용 중…
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 w-full">
        {items.map((item, i) => {
          const hasMeta = hasRealLibraryMetadata(item);
          const delay =
            !suppressCardAnimRef.current
            && items.length <= LIBRARY_PAGE_SIZE
            && i < 48
              ? (i % 48) * 15
              : 0;
          return (
          <PosterCard
            key={`${item.id}-${item.cover_image_local_path ?? ""}-${coverRev[item.product_code.toUpperCase()] ?? ""}`}
            productCode={item.product_code}
            coverSrc={item.product_code ? coverUrl(item.product_code, coverCacheKey(item)) : undefined}
            previewSrc={item.has_preview && item.product_code ? previewUrl(item.product_code, item.updated_at ?? "") : undefined}
            previewMedia={item.preview_media ?? undefined}
            hasPreview={!!item.has_preview}
            hasFolder={!!item.folder_path}
            hasMeta={hasMeta}
            title={hasMeta ? item.title_ko : null}
            actors={item.actors_ko || item.actors_ja}
            genres={item.genres_ko}
            sceneCount={item.scene_count ?? 0}
            favoriteScore={Number(item.favorite_score) || 0}
            hasSubtitle={!!item.has_subtitle}
            hasHardcodedSubtitle={!!item.has_hardcoded_subtitle}
            hasMosaicRemoved={!!item.has_mosaic_removed}
            delay={delay}
            onClick={() => openLibraryDetail(item.product_code)}
            onPlay={item.folder_path ? () => handlePlay(item.product_code) : undefined}
            onOpenFolder={() => handleOpenFolder(item.product_code)}
            onAddToProcessing={kind => handleAddToProcessing(item.product_code, kind)}
            onActorClick={handleActorClick}
          />
          );
        })}
        {loading && items.length === 0 && [0, 1, 2, 3, 4, 5, 6].map(i => (
          <div key={i} className="rounded-xl border border-white/[0.06] overflow-hidden animate-pulse">
            <div className="aspect-[2/3] bg-bg-card" />
            <div className="h-24 bg-bg-panel border-t border-white/[0.06]" />
          </div>
        ))}
      </div>

      <div ref={loadMoreSentinelRef} className="h-1" aria-hidden />

      {loadingMore && (
        <div className="flex justify-center py-4">
          <RefreshCw className="w-5 h-5 text-muted-foreground animate-spin" />
        </div>
      )}

      {!loading && !loadingMore && items.length >= total && items.length > 0 && (
        <p className="text-center text-sm text-muted-foreground py-2">
          전체 {total.toLocaleString()}건 표시됨
        </p>
      )}

      {currentView === "library" && libraryDetailSku && (
        <LibraryDetailPanel
          code={libraryDetailSku}
          onClose={handleCloseDetail}
          onPlay={() => handlePlay(libraryDetailSku)}
          onSaved={handleDetailSaved}
          onActorClick={handleActorClick}
        />
      )}
    </div>
  );
}
