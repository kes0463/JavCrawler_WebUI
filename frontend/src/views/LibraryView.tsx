import { useState, useEffect, useCallback, useRef } from "react";
import { Search, SlidersHorizontal, FolderOpen, X, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchLibrary, fetchLibraryStats, coverUrl } from "@/api/library";
import type { LibraryItem, LibraryStats, LibraryQuery } from "@/api/library";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";

const SORT_OPTIONS = [
  { label: "최근 수정", value: "updated_at" },
  { label: "발매일", value: "release_date" },
  { label: "품번", value: "product_code" },
  { label: "제목", value: "title_ko" },
] as const;

export default function LibraryView() {
  const [query, setQuery] = useState<LibraryQuery>({
    q: "", page: 1, per_page: 48, sort: "updated_at", order: "desc",
  });
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const appendRef = useRef(false);

  const refreshStats = useCallback(() => {
    setStatsLoading(true);
    fetchLibraryStats()
      .then(setStats)
      .finally(() => setStatsLoading(false));
  }, []);

  useEffect(() => { refreshStats(); }, [refreshStats]);

  // 목록 로드
  const loadItems = useCallback((q: LibraryQuery, append = false) => {
    setLoading(true);
    fetchLibrary(q)
      .then(({ items: newItems, total: t }) => {
        setItems(prev => append ? [...prev, ...newItems] : newItems);
        setTotal(t);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const append = appendRef.current;
    appendRef.current = false;
    loadItems(query, append);
  }, [query, loadItems]);

  const [searchText, setSearchText] = useState(query.q ?? "");

  const handleSearch = (value: string) => {
    setSearchText(value);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setQuery(q => ({ ...q, q: value, page: 1 }));
    }, 350);
  };

  const handleLoadMore = () => {
    appendRef.current = true;
    setQuery(q => ({ ...q, page: (q.page ?? 1) + 1 }));
  };

  const hasMore = items.length < total;

  return (
    <div className="space-y-5">

      {/* ── 통계 바 ── */}
      <div className="flex items-center gap-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 flex-1">
          {statsLoading
            ? [0,1,2,3].map(i => <GlassCard key={i}><Skeleton className="h-8 w-full" /></GlassCard>)
            : [
                { label: "전체", value: stats?.total, color: "text-white" },
                { label: "메타데이터 완료", value: stats?.with_metadata, color: "text-emerald-400" },
                { label: "폴더 연결", value: stats?.with_folder, color: "text-indigo-400" },
                { label: "미수집", value: stats?.without_metadata, color: "text-amber-400" },
              ].map(({ label, value, color }) => (
                <GlassCard key={label} className="animate-scale-in">
                  <p className="text-[11px] text-muted-foreground">{label}</p>
                  <p className={cn("text-2xl font-bold tabular-nums mt-0.5", color)}>
                    {value?.toLocaleString() ?? "—"}
                  </p>
                </GlassCard>
              ))}
        </div>
        <button
          onClick={refreshStats}
          title="통계 새로고침"
          className="h-9 w-9 shrink-0 rounded-xl flex items-center justify-center bg-bg-surface border border-white/[0.08] text-muted-foreground hover:text-white hover:border-white/[0.16] transition-all"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", statsLoading && "animate-spin")} />
        </button>
      </div>

      {/* ── 검색 + 필터 ── */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="text"
            placeholder="품번, 제목, 배우 검색..."
            value={searchText}
            onChange={e => handleSearch(e.target.value)}
            className={cn(
              "w-full h-9 pl-9 pr-4 text-sm rounded-xl",
              "bg-bg-surface border border-white/[0.08] text-white placeholder:text-muted-foreground",
              "focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30",
              "transition-all duration-150",
            )}
          />
        </div>

        {/* 정렬 */}
        <select
          value={query.sort}
          onChange={e => setQuery(q => ({ ...q, sort: e.target.value as LibraryQuery["sort"], page: 1 }))}
          className="h-9 px-3 text-sm rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] focus:outline-none"
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <button
          onClick={() => setQuery(q => ({ ...q, order: q.order === "desc" ? "asc" : "desc", page: 1 }))}
          className="h-9 px-3 text-sm rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] hover:text-white transition-colors"
        >
          {query.order === "desc" ? "↓ 내림차순" : "↑ 오름차순"}
        </button>

        {/* 필터 토글 */}
        <button
          onClick={() => setQuery(q => ({ ...q, has_folder: q.has_folder === true ? undefined : true, page: 1 }))}
          className={cn(
            "h-9 px-3 text-sm rounded-xl border transition-colors flex items-center gap-1.5",
            query.has_folder
              ? "bg-indigo-500/20 border-indigo-500/40 text-indigo-300"
              : "bg-bg-surface border-white/[0.08] text-muted-foreground hover:text-white",
          )}
        >
          <FolderOpen className="w-3.5 h-3.5" />
          폴더 있음
        </button>

        <button
          onClick={() => setQuery(q => ({
            ...q,
            has_metadata: q.has_metadata === false ? undefined : false,
            page: 1,
          }))}
          className={cn(
            "h-9 px-3 text-sm rounded-xl border transition-colors flex items-center gap-1.5",
            query.has_metadata === false
              ? "bg-amber-500/20 border-amber-500/40 text-amber-300"
              : "bg-bg-surface border-white/[0.08] text-muted-foreground hover:text-white",
          )}
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          미수집만
        </button>

        {/* 총 건수 */}
        <span className="text-xs text-muted-foreground ml-auto">
          {total.toLocaleString()}건
        </span>
      </div>

      {/* ── 그리드 ── */}
      <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-2">
        {items.map((item, i) => (
          <PosterCard
            key={item.id}
            item={item}
            delay={(i % 48) * 15}
            onClick={() => setSelectedCode(item.product_code)}
          />
        ))}
        {loading && [0,1,2,3,4,5,6,7].map(i => (
          <div key={i} className="aspect-[2/3] rounded-xl bg-bg-card border border-white/[0.06] animate-pulse" />
        ))}
      </div>

      {/* ── 더 보기 ── */}
      {!loading && hasMore && (
        <div className="flex justify-center pt-2">
          <button
            onClick={handleLoadMore}
            className="px-6 py-2 text-sm rounded-xl bg-bg-surface border border-white/[0.08] text-muted-foreground hover:text-white hover:border-white/[0.16] transition-all"
          >
            더 보기 ({(total - items.length).toLocaleString()}건 남음)
          </button>
        </div>
      )}

      {/* ── 상세 패널 ── */}
      {selectedCode && (
        <DetailPanel code={selectedCode} onClose={() => setSelectedCode(null)} />
      )}
    </div>
  );
}

// ── PosterCard ────────────────────────────────────────────────────

function PosterCard({
  item,
  delay,
  onClick,
}: {
  item: LibraryItem;
  delay: number;
  onClick: () => void;
}) {
  const [imgError, setImgError] = useState(false);

  return (
    <button
      onClick={onClick}
      style={{ animationDelay: `${delay}ms` }}
      className={cn(
        "relative aspect-[2/3] rounded-xl border border-white/[0.06]",
        "bg-bg-card hover:border-white/[0.14] hover:scale-[1.03]",
        "transition-all duration-150 animate-scale-in overflow-hidden",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50",
      )}
    >
      {/* 표지 이미지 */}
      {item.product_code && !imgError ? (
        <img
          src={coverUrl(item.product_code)}
          alt={item.product_code}
          loading="lazy"
          onError={() => setImgError(true)}
          className="absolute inset-0 w-full h-full object-cover"
        />
      ) : null}

      {/* 폴백 / 오버레이 */}
      <div className={cn(
        "absolute inset-0 flex flex-col items-center justify-end p-1.5",
        "bg-gradient-to-t from-black/80 via-black/20 to-transparent",
      )}>
        <span className="text-[8px] font-mono font-bold text-indigo-300 text-center leading-tight">
          {item.product_code}
        </span>
        {!item.title_ko && (
          <span className="text-[7px] text-amber-400 mt-0.5">미수집</span>
        )}
      </div>

      {/* 폴더 있음 표시 */}
      {item.folder_path && (
        <div className="absolute top-1 right-1 w-3 h-3 rounded-full bg-indigo-500/70 flex items-center justify-center">
          <FolderOpen className="w-2 h-2 text-white" />
        </div>
      )}
    </button>
  );
}

// ── DetailPanel ───────────────────────────────────────────────────

import { fetchLibraryDetail } from "@/api/library";
import type { LibraryItemDetail } from "@/api/library";

function DetailPanel({ code, onClose }: { code: string; onClose: () => void }) {
  const [detail, setDetail] = useState<LibraryItemDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchLibraryDetail(code)
      .then(setDetail)
      .finally(() => setLoading(false));
  }, [code]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <GlassCard
        variant="strong"
        className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto animate-scale-in"
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-7 h-7 rounded-full bg-white/[0.06] hover:bg-white/[0.12] flex items-center justify-center transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>

        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : detail ? (
          <div className="flex gap-5">
            {/* 표지 */}
            <div className="w-32 shrink-0">
              <img
                src={coverUrl(detail.product_code)}
                alt={detail.product_code}
                onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
                className="w-full rounded-lg object-cover"
              />
            </div>

            {/* 정보 */}
            <div className="flex-1 space-y-3 min-w-0">
              <div>
                <p className="text-[10px] font-mono text-indigo-400">{detail.product_code}</p>
                <h2 className="text-base font-semibold text-white leading-snug mt-0.5">
                  {detail.title_ko || detail.title_ja || "—"}
                </h2>
                {detail.title_ja && detail.title_ko && (
                  <p className="text-xs text-muted-foreground mt-0.5 leading-snug">{detail.title_ja}</p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                <InfoRow label="배우" value={detail.actors_ko || detail.actors_ja} />
                <InfoRow label="장르" value={detail.genres_ko || detail.genres_ja} />
                <InfoRow label="제작사" value={detail.maker_ko || detail.maker_ja} />
                <InfoRow label="발매일" value={detail.release_date} />
                <InfoRow label="폴더" value={detail.folder_path} mono />
              </div>

              {detail.synopsis_ko && (
                <div>
                  <p className="text-[10px] text-muted-foreground mb-1">시놉시스</p>
                  <p className="text-xs text-[#c8c8e0] leading-relaxed line-clamp-6">
                    {detail.synopsis_ko}
                  </p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">불러오기 실패</p>
        )}
      </GlassCard>
    </div>
  );
}

function InfoRow({ label, value, mono = false }: { label: string; value?: string | null; mono?: boolean }) {
  if (!value) return null;
  return (
    <div className="col-span-2">
      <span className="text-muted-foreground">{label}: </span>
      <span className={cn("text-[#c8c8e0]", mono && "font-mono text-[10px]")}>{value}</span>
    </div>
  );
}
