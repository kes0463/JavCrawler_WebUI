import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { coverUrl } from "@/api/library";
import type { ActressWork } from "@/api/actress";
import { getScrollableAncestor, useInfiniteScrollNearEnd } from "@/hooks/useGlobalDragScroll";

type WorkSortKey = "product_code" | "release_date" | "favorite_score" | "user_rating";

const SORT_OPTIONS: { value: WorkSortKey; label: string }[] = [
  { value: "product_code", label: "품번" },
  { value: "release_date", label: "출시일" },
  { value: "favorite_score", label: "좋아요" },
  { value: "user_rating", label: "내 점수" },
];

const PAGE_SIZE = 48;

const controlClass =
  "h-10 px-3 text-base rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] focus:outline-none";

interface ActressWorksGridProps {
  works: ActressWork[];
  genres: string[];
  onWorkClick: (productCode: string) => void;
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

export function ActressWorksGrid({ works, genres, onWorkClick }: ActressWorksGridProps) {
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

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <p className="text-lg font-semibold mr-2">
          출연작 <span className="text-slate-400 font-normal">{filtered.length}</span>
        </p>
        <select
          value={sortKey}
          onChange={e => {
            setSortKey(e.target.value as WorkSortKey);
            setVisibleCount(PAGE_SIZE);
          }}
          className={controlClass}
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => {
            setSortAsc(a => !a);
            setVisibleCount(PAGE_SIZE);
          }}
          className={cn(controlClass, "hover:text-white transition-colors")}
        >
          {sortAsc ? "↑ 오름차순" : "↓ 내림차순"}
        </button>
      </div>

      {genres.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          <button
            type="button"
            onClick={() => {
              setGenreFilter("");
              setVisibleCount(PAGE_SIZE);
            }}
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
              onClick={() => {
                setGenreFilter(prev => (prev === g ? "" : g));
                setVisibleCount(PAGE_SIZE);
              }}
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

      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-3">
        {visible.map(w => (
          <button
            key={w.product_code}
            type="button"
            onClick={() => onWorkClick(w.product_code)}
            className="text-left rounded-xl border border-white/[0.08] overflow-hidden hover:border-violet-500/30 transition-colors"
          >
            <div className="aspect-video bg-black/40">
              <img
                src={coverUrl(w.product_code)}
                alt=""
                draggable={false}
                className="w-full h-full object-cover pointer-events-none"
                loading="lazy"
              />
            </div>
            <div className="p-2">
              <p className="font-mono text-xs text-violet-300">{w.product_code}</p>
              <p className="text-sm truncate">{w.title_ko || "—"}</p>
              {w.release_date && (
                <p className="text-xs text-slate-500 mt-0.5">{w.release_date}</p>
              )}
            </div>
          </button>
        ))}
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
