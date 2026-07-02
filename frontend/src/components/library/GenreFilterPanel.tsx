import { useMemo, useState } from "react";
import { ChevronDown, Search, Tag, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LibraryGenreItem } from "@/api/library";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";

interface GenreFilterSharedProps {
  genres: LibraryGenreItem[];
  selected: string[];
  mode: "and" | "or";
  loading?: boolean;
  onToggleGenre: (name: string) => void;
  onModeChange: (mode: "and" | "or") => void;
  onClear: () => void;
}

interface GenreFilterBarProps extends GenreFilterSharedProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function chipClass(active: boolean) {
  return cn(
    "px-3 py-1.5 rounded-full text-sm border transition-colors shrink-0",
    active
      ? "bg-violet-500/30 border-violet-500/50 text-violet-100 shadow-sm shadow-violet-500/10"
      : "bg-white/[0.04] border-white/[0.10] text-slate-300 hover:bg-white/[0.08] hover:text-white",
  );
}

function selectedChipClass() {
  return cn(
    "inline-flex items-center gap-1 h-10 px-2.5 rounded-xl text-sm border",
    "bg-violet-500/20 border-violet-500/40 text-violet-100 hover:bg-violet-500/30 transition-colors",
  );
}

/** 툴바: 접기/펼치기 버튼 + 선택된 장르 칩 */
export function GenreFilterBar({
  open,
  onOpenChange,
  selected,
  mode,
  onToggleGenre,
  onClear,
}: GenreFilterBarProps) {
  return (
    <>
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        className={cn(
          "h-10 px-3 text-base rounded-xl border transition-colors flex items-center gap-1.5 shrink-0",
          open || selected.length > 0
            ? "bg-violet-500/20 border-violet-500/40 text-violet-200"
            : "bg-bg-surface border-white/[0.08] text-muted-foreground hover:text-white",
        )}
      >
        <Tag className="w-3.5 h-3.5" />
        장르
        {selected.length > 0 && (
          <span className="px-1.5 py-0.5 rounded-md bg-violet-500/30 text-xs tabular-nums">
            {selected.length}
          </span>
        )}
        <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", open && "rotate-180")} />
      </button>

      {selected.map(name => (
        <button
          key={name}
          type="button"
          onClick={() => onToggleGenre(name)}
          className={selectedChipClass()}
        >
          {name}
          <X className="w-3 h-3 opacity-70" />
        </button>
      ))}

      {selected.length > 0 && (
        <button
          type="button"
          onClick={onClear}
          className="text-sm text-slate-500 hover:text-slate-300 underline underline-offset-2 shrink-0"
        >
          장르 초기화
        </button>
      )}

      {!open && selected.length > 0 && (
        <span className="text-xs text-muted-foreground shrink-0">
          {mode === "and" ? "모두 포함" : "하나라도 포함"}
        </span>
      )}
    </>
  );
}

/** 펼침 영역: 장르 검색 + 전체 장르 칩 */
export function GenreFilterChipPanel({
  genres,
  selected,
  mode,
  loading = false,
  onToggleGenre,
  onModeChange,
  onClear,
}: GenreFilterSharedProps) {
  const [filterText, setFilterText] = useState("");
  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const filtered = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    if (!q) return genres;
    return genres.filter(g => g.name.toLowerCase().includes(q));
  }, [filterText, genres]);

  const displayGenres = useMemo(() => {
    const byName = new Map(genres.map(g => [g.name, g]));
    const pinned = selected.map(name => byName.get(name) ?? { name, count: 0 });
    const pinnedNames = new Set(selected);
    const rest = filtered.filter(g => !pinnedNames.has(g.name));
    return [...pinned, ...rest];
  }, [filtered, genres, selected]);

  return (
    <GlassCard className="space-y-3 !p-4">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <p className="text-xs text-muted-foreground">
          {mode === "and"
            ? "칩을 눌러 선택 · 선택한 장르를 모두 포함하는 작품만 표시"
            : "칩을 눌러 선택 · 선택한 장르 중 하나라도 포함하는 작품 표시"}
        </p>
        <div className="flex rounded-full border border-white/10 overflow-hidden text-xs shrink-0">
          <button
            type="button"
            onClick={() => onModeChange("and")}
            className={cn(
              "px-3 py-1.5 transition-colors",
              mode === "and" ? "bg-violet-500/25 text-violet-100" : "text-slate-400 hover:text-white",
            )}
          >
            모두
          </button>
          <button
            type="button"
            onClick={() => onModeChange("or")}
            className={cn(
              "px-3 py-1.5 transition-colors",
              mode === "or" ? "bg-violet-500/25 text-violet-100" : "text-slate-400 hover:text-white",
            )}
          >
            하나라도
          </button>
        </div>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          placeholder="장르 검색..."
          value={filterText}
          onChange={e => setFilterText(e.target.value)}
          className={cn(
            "w-full h-9 pl-9 pr-3 text-sm rounded-full",
            "bg-bg-surface border border-white/[0.08] text-white placeholder:text-muted-foreground",
            "focus:outline-none focus:border-violet-500/40 focus:ring-1 focus:ring-violet-500/20",
          )}
        />
      </div>

      {loading ? (
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 14 }, (_, i) => (
            <Skeleton key={i} className="h-8 w-16 rounded-full" />
          ))}
        </div>
      ) : displayGenres.length === 0 ? (
        <p className="text-sm text-slate-500 py-3 text-center">일치하는 장르가 없습니다.</p>
      ) : (
        <div className="flex flex-wrap gap-2 max-h-52 overflow-y-auto -mx-1 px-1">
          <button
            type="button"
            onClick={onClear}
            className={chipClass(selected.length === 0)}
          >
            전체
          </button>
          {displayGenres.map(item => {
            const active = selectedSet.has(item.name);
            return (
              <button
                key={item.name}
                type="button"
                onClick={() => onToggleGenre(item.name)}
                className={chipClass(active)}
              >
                {item.name}
                <span className={cn("ml-1.5 text-xs tabular-nums", active ? "text-violet-200/80" : "text-slate-500")}>
                  {item.count}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </GlassCard>
  );
}

/** @deprecated use GenreFilterBar + GenreFilterChipPanel */
export function GenreFilterPanel(props: GenreFilterBarProps) {
  return (
    <>
      <GenreFilterBar {...props} />
      {props.open && <GenreFilterChipPanel {...props} />}
    </>
  );
}
