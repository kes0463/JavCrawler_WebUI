import { useCallback, useEffect, useRef, useState } from "react";
import { Search, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/contexts/ToastContext";
import { useNavigation } from "@/contexts/NavigationContext";
import {
  createActress,
  fetchActressProfile,
  fetchActressWorks,
  fetchActresses,
  mergeActresses,
  type ActressListItem,
  type ActressProfile,
  type ActressSort,
  type ActressWork,
} from "@/api/actress";
import { ActressCard } from "@/components/actress/ActressCard";
import { ActressDetailPanel } from "@/components/actress/ActressDetailPanel";
import { AddActressDialog, type ActressCreatePayload } from "@/components/actress/AddActressDialog";
import { MergeActressDialog } from "@/components/actress/MergeActressDialog";
import { LibraryDetailPanel } from "@/components/library/LibraryDetailPanel";
import { fetchApiStatus } from "@/api/client";
import { useHorizontalSplit } from "@/hooks/useHorizontalSplit";
import { useInfiniteScrollNearEnd } from "@/hooks/useGlobalDragScroll";
import { usePlayer } from "@/contexts/PlayerContext";

const SORT_OPTIONS: { value: ActressSort; label: string }[] = [
  { value: "name", label: "이름" },
  { value: "works", label: "작품수" },
  { value: "favorite", label: "즐겨찾기" },
  { value: "score", label: "점수" },
  { value: "recent", label: "최근" },
];

const PER_PAGE = 96;
/** 분할 패널 목록: 상세 진입 시 grid-cols-4 기준 카드 크기를 고정, 패널 너비에 따라 열 개수만 변경 */
const ACTRESS_SPLIT_DEFAULT_COLUMNS = 4;
const ACTRESS_LIST_GRID_GAP = 12;

function actressSplitCardWidth(panelWidth: number): number {
  return Math.floor(
    (panelWidth - (ACTRESS_SPLIT_DEFAULT_COLUMNS - 1) * ACTRESS_LIST_GRID_GAP) / ACTRESS_SPLIT_DEFAULT_COLUMNS,
  );
}

function actressSplitColumnCount(panelWidth: number, cardWidth: number): number {
  return Math.max(
    1,
    Math.floor((panelWidth + ACTRESS_LIST_GRID_GAP) / (cardWidth + ACTRESS_LIST_GRID_GAP)),
  );
}

export default function ActressView() {
  const { showToast } = useToast();
  const {
    actressDetailId,
    actressListEpoch,
    openActressByName,
    pendingActressCreateName,
    clearPendingActressCreate,
    closeActressDetail,
  } = useNavigation();
  const { openPlayer } = usePlayer();

  const [items, setItems] = useState<ActressListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<ActressSort>("name");
  const [ascending, setAscending] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [profile, setProfile] = useState<ActressProfile | null>(null);
  const [works, setWorks] = useState<ActressWork[]>([]);
  const [workGenres, setWorkGenres] = useState<string[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [addPrefill, setAddPrefill] = useState<string | null>(null);
  const [showMerge, setShowMerge] = useState(false);
  const [workDetailCode, setWorkDetailCode] = useState<string | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadMoreSentinelRef = useRef<HTMLDivElement | null>(null);
  const listScrollRef = useRef<HTMLDivElement | null>(null);
  const [listScrollEl, setListScrollEl] = useState<HTMLDivElement | null>(null);
  const loadingMoreRef = useRef(false);
  const apiWarnedRef = useRef(false);
  const apiCheckedRef = useRef(false);
  const { width: listWidth, onPointerDown: onSplitPointerDown } = useHorizontalSplit({
    initialWidth: 340,
    minWidth: 260,
    maxWidth: 560,
    storageKey: "javstory_actress_list_width",
  });
  const splitCardWidthRef = useRef<number | null>(null);
  const [splitCardWidth, setSplitCardWidth] = useState<number | null>(null);
  const actressListEpochRef = useRef(actressListEpoch);

  useEffect(() => {
    const epochChanged = actressListEpochRef.current !== actressListEpoch;
    actressListEpochRef.current = actressListEpoch;
    if (epochChanged) {
      setSelectedId(null);
      return;
    }
    if (actressDetailId != null) {
      setSelectedId(actressDetailId);
    }
  }, [actressDetailId, actressListEpoch]);

  useEffect(() => {
    if (selectedId == null) {
      splitCardWidthRef.current = null;
      setSplitCardWidth(null);
      return;
    }
    if (splitCardWidthRef.current == null) {
      const width = actressSplitCardWidth(listWidth);
      splitCardWidthRef.current = width;
      setSplitCardWidth(width);
    }
  }, [selectedId, listWidth]);

  useEffect(() => {
    if (apiCheckedRef.current) return;
    apiCheckedRef.current = true;
    fetchApiStatus()
      .then(s => {
        if (s.actress_count == null) {
          showToast(
            "구버전 webapi가 실행 중입니다. start_web.bat으로 webapi를 재시작해 주세요.",
            "warn",
          );
        }
      })
      .catch(() => { /* ignore */ });
  }, [showToast]);

  const loadList = useCallback((pageNum: number, append = false) => {
    if (append) {
      loadingMoreRef.current = true;
      setLoadingMore(true);
    } else {
      setLoading(true);
    }
    setLoadError(null);
    fetchActresses(query, sort, ascending ? "asc" : "desc", pageNum, PER_PAGE)
      .then(r => {
        if (!append && !apiWarnedRef.current && r.items.length === 0 && r.total === 0) {
          apiWarnedRef.current = true;
          showToast(
            "배우 데이터가 비어 있습니다. start_web.bat으로 webapi를 실행했는지 확인해 주세요.",
            "warn",
          );
        }
        setItems(prev => append ? [...prev, ...r.items] : r.items);
        setTotal(r.total);
        setPage(pageNum);
      })
      .catch(e => {
        const msg = String((e as Error).message || e);
        setLoadError(msg);
        if (!append) setItems([]);
        showToast(msg, "error");
      })
      .finally(() => {
        setLoading(false);
        setLoadingMore(false);
        loadingMoreRef.current = false;
      });
  }, [query, sort, ascending, showToast]);

  useEffect(() => {
    loadList(1, false);
  }, [query, sort, ascending, loadList]);

  useEffect(() => {
    if (pendingActressCreateName) {
      setAddPrefill(pendingActressCreateName);
      setShowAdd(true);
      showToast(`"${pendingActressCreateName}" 배우 프로필이 없습니다. 새로 추가해 주세요.`, "info");
      clearPendingActressCreate();
    }
  }, [pendingActressCreateName, clearPendingActressCreate, showToast]);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setQuery(searchInput), 300);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [searchInput]);

  const requestLoadMore = useCallback(() => {
    if (loading || loadingMoreRef.current) return;
    if (items.length >= total || total === 0) return;
    loadList(page + 1, true);
  }, [loading, items.length, total, page, loadList]);

  const hasMoreItems = !loading && items.length < total && total > 0;
  useInfiniteScrollNearEnd(listScrollEl, hasMoreItems, requestLoadMore);

  const checkLoadMore = useCallback(() => {
    if (loading || loadingMoreRef.current || items.length >= total || total === 0) return;
    const root = listScrollRef.current;
    const el = loadMoreSentinelRef.current;
    if (!root || !el) return;
    const rootRect = root.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    if (elRect.top <= rootRect.bottom + 480) {
      requestLoadMore();
    }
  }, [loading, items.length, total, requestLoadMore]);

  useEffect(() => {
    const root = listScrollEl;
    const el = loadMoreSentinelRef.current;
    if (!root || !el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) requestLoadMore();
      },
      { root, rootMargin: "480px", threshold: 0 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [requestLoadMore, items.length, total, listScrollEl]);

  useEffect(() => {
    if (loading || loadingMore) return;
    const id = requestAnimationFrame(() => checkLoadMore());
    return () => cancelAnimationFrame(id);
  }, [items.length, loading, loadingMore, total, checkLoadMore]);

  useEffect(() => {
    const root = listScrollEl;
    if (!root) return;
    const onScroll = () => checkLoadMore();
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => root.removeEventListener("scroll", onScroll);
  }, [checkLoadMore, listScrollEl]);

  const loadDetail = useCallback((id: number) => {
    setDetailLoading(true);
    Promise.all([fetchActressProfile(id), fetchActressWorks(id)])
      .then(([p, bundle]) => {
        setProfile(p);
        setWorks(bundle.works);
        setWorkGenres(bundle.genres);
      })
      .catch(e => showToast(String(e.message || e), "error"))
      .finally(() => setDetailLoading(false));
  }, [showToast]);

  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
    else {
      setProfile(null);
      setWorks([]);
      setWorkGenres([]);
    }
  }, [selectedId, loadDetail]);

  const handleSelect = (id: number) => {
    setSelectedId(id);
    closeActressDetail();
  };

  const handleBack = () => {
    setSelectedId(null);
    closeActressDetail();
  };

  const handleCreate = async (payload: ActressCreatePayload) => {
    try {
      const p = await createActress(payload);
      setShowAdd(false);
      setAddPrefill(null);
      loadList(1, false);
      setSelectedId(p.id);
      showToast("배우가 추가되었습니다.", "success");
    } catch (e) {
      showToast(String((e as Error).message || e), "error");
      throw e;
    }
  };

  const handleMerge = async (mergeId: number) => {
    if (!profile) return;
    try {
      const res = await mergeActresses(profile.id, mergeId);
      setProfile(res.profile);
      loadList(1, false);
      loadDetail(profile.id);
      showToast("배우 프로필을 합쳤습니다.", "success");
    } catch (e) {
      showToast(String((e as Error).message || e), "error");
      throw e;
    }
  };

  const refreshList = () => loadList(1, false);

  const listToolbar = (
    <div className="flex flex-wrap items-center gap-2 shrink-0 pb-3">
      <div className="relative flex-1 min-w-[180px]">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          placeholder="이름·장르·별명 검색…"
          className={cn(
            "w-full h-10 pl-10 pr-4 text-base rounded-xl",
            "bg-bg-surface border border-white/[0.08] text-white placeholder:text-muted-foreground",
            "focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30",
            "transition-all duration-150",
          )}
        />
      </div>
      <select
        value={sort}
        onChange={e => setSort(e.target.value as ActressSort)}
        className="h-10 px-3 text-base rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] focus:outline-none"
      >
        {SORT_OPTIONS.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => setAscending(a => !a)}
        className="h-10 px-3 text-base rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] hover:text-white transition-colors"
      >
        {ascending ? "↑ 오름차순" : "↓ 내림차순"}
      </button>
      <button
        type="button"
        onClick={() => {
          setAddPrefill(null);
          setShowAdd(true);
        }}
        className="h-10 inline-flex items-center gap-1.5 px-3 rounded-xl bg-violet-500/20 border border-violet-500/30 text-violet-200 hover:bg-violet-500/30 transition-colors"
      >
        <Plus className="w-4 h-4" /> 추가
      </button>
    </div>
  );

  const effectiveSplitCardWidth = splitCardWidth ?? actressSplitCardWidth(listWidth);
  const splitColumnCount = actressSplitColumnCount(listWidth, effectiveSplitCardWidth);
  const listGridClass = cn(
    "grid gap-3 w-full",
    !selectedId && "grid-cols-4 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10",
  );
  const listGridStyle = selectedId
    ? {
        gridTemplateColumns: `repeat(auto-fill, minmax(${effectiveSplitCardWidth}px, ${effectiveSplitCardWidth}px))`,
      }
    : undefined;

  const listBody = (
    <>
      {!loading && total > 0 && (
        <p className="text-sm text-slate-400 mb-2 shrink-0">
          배우 {total.toLocaleString()}명
          {query ? ` · "${query}" 검색` : ""}
        </p>
      )}

      {loading && items.length === 0 ? (
        <div className={listGridClass} style={listGridStyle}>
          {(selectedId
            ? Array.from({ length: splitColumnCount * 3 }, (_, i) => i)
            : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
          ).map(i => (
            <Skeleton key={i} className="aspect-[3/4] rounded-xl" />
          ))}
        </div>
      ) : loadError && items.length === 0 ? (
        <div className="text-center py-12 space-y-3">
          <p className="text-rose-300">배우 목록을 불러오지 못했습니다.</p>
          <p className="text-sm text-slate-500">{loadError}</p>
          <button
            type="button"
            onClick={() => loadList(1, false)}
            className="px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5"
          >
            다시 시도
          </button>
        </div>
      ) : !loading && items.length === 0 ? (
        <p className="text-center text-slate-500 py-12">등록된 배우가 없습니다.</p>
      ) : (
        <>
          <div className={listGridClass} style={listGridStyle}>
            {items.map(item => (
              <ActressCard
                key={item.id}
                item={item}
                selected={selectedId === item.id}
                onClick={() => handleSelect(item.id)}
              />
            ))}
          </div>
          <div ref={loadMoreSentinelRef} className="h-px w-full" aria-hidden />
          {loadingMore && (
            <p className="text-center text-sm text-slate-500 py-2">더 불러오는 중…</p>
          )}
          {!loadingMore && items.length >= total && items.length > 0 && (
            <p className="text-center text-sm text-slate-500 py-2 pb-4">
              전체 {total.toLocaleString()}명 표시됨
            </p>
          )}
        </>
      )}
    </>
  );

  return (
    <div className="flex h-[calc(100vh-6.25rem)] min-h-0 -my-5 overflow-hidden">
      <div
        className={cn(
          "flex flex-col min-h-0 min-w-0",
          selectedId
            ? "hidden lg:flex shrink-0"
            : "flex flex-1 w-full",
        )}
        style={selectedId ? { width: listWidth } : undefined}
      >
        <div className="shrink-0 pb-3">{listToolbar}</div>
        <div
          ref={(el) => {
            listScrollRef.current = el;
            setListScrollEl(el);
          }}
          className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden app-scroll pr-1"
        >
          {listBody}
        </div>
      </div>

      {selectedId && (
        <>
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="목록 너비 조절"
            onPointerDown={onSplitPointerDown}
            className="hidden lg:block w-1.5 shrink-0 cursor-col-resize rounded-full bg-white/[0.06] hover:bg-violet-500/40 active:bg-violet-500/60 transition-colors"
          />

          <GlassCard className="flex flex-1 min-w-0 min-h-0 flex-col overflow-hidden">
            <ActressDetailPanel
              profile={profile}
              works={works}
              workGenres={workGenres}
              loading={detailLoading}
              onBack={handleBack}
              onProfileChange={setProfile}
              onRefresh={() => selectedId && loadDetail(selectedId)}
              onListRefresh={refreshList}
              onWorkClick={setWorkDetailCode}
              onMergeClick={() => setShowMerge(true)}
              onError={msg => showToast(msg, "error")}
              onSuccess={msg => showToast(msg, "success")}
            />
          </GlassCard>
        </>
      )}

      <AddActressDialog
        open={showAdd}
        prefillName={addPrefill}
        onClose={() => {
          setShowAdd(false);
          setAddPrefill(null);
        }}
        onCreate={handleCreate}
      />

      <MergeActressDialog
        open={showMerge}
        profile={profile}
        onClose={() => setShowMerge(false)}
        onMerge={handleMerge}
      />

      {workDetailCode && (
        <LibraryDetailPanel
          code={workDetailCode}
          onClose={() => setWorkDetailCode(null)}
          onPlay={() => void openPlayer(workDetailCode)}
          onActorClick={async name => {
            setWorkDetailCode(null);
            try {
              await openActressByName(name);
            } catch (e) {
              showToast(e instanceof Error ? e.message : "배우 정보를 불러오지 못했습니다.", "error");
            }
          }}
        />
      )}
    </div>
  );
}
