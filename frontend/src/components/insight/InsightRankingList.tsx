import type { ReactNode } from "react";
import { ProgressIndicator } from "@/components/ui/ProgressIndicator";
import { GlassCard } from "@/components/ui/GlassCard";

interface RankRow {
  name: string;
  score?: number;
  count?: number;
}

interface InsightRankingListProps {
  title: string;
  icon?: ReactNode;
  items: RankRow[];
  scoreLabel?: string;
  showCount?: boolean;
  maxItems?: number;
}

export function InsightRankingList({
  title,
  icon,
  items,
  scoreLabel = "취향",
  showCount = false,
  maxItems = 8,
}: InsightRankingListProps) {
  const rows = items.slice(0, maxItems);
  const maxScore = Math.max(...rows.map(r => r.score ?? 0), 1);
  const maxCount = Math.max(...rows.map(r => r.count ?? 0), 1);

  return (
    <GlassCard className="space-y-3">
      <div className="flex items-center gap-2">
        {icon}
        <h2 className="text-lg font-semibold text-[#d0d0e8]">{title}</h2>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500 py-4 text-center">데이터가 없습니다.</p>
      ) : (
        <div className="space-y-2.5">
          {rows.map((row, i) => {
            const pct = showCount
              ? Math.round(((row.count ?? 0) / maxCount) * 100)
              : Math.round(((row.score ?? 0) / maxScore) * 100);
            return (
              <div key={`${row.name}-${i}`} className="space-y-1">
                <div className="flex justify-between text-base">
                  <span className="text-[#c8c8e0] truncate pr-2">{row.name}</span>
                  <span className="text-muted-foreground tabular-nums shrink-0">
                    {showCount ? row.count : row.score}
                    {!showCount && scoreLabel ? ` ${scoreLabel}` : ""}
                  </span>
                </div>
                <ProgressIndicator value={pct} size="sm" />
              </div>
            );
          })}
        </div>
      )}
    </GlassCard>
  );
}
