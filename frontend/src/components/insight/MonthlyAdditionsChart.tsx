import { TrendingUp } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import type { MonthlyAddition } from "@/api/insight";

interface MonthlyAdditionsChartProps {
  items: MonthlyAddition[];
}

export function MonthlyAdditionsChart({ items }: MonthlyAdditionsChartProps) {
  const max = Math.max(...items.map(m => m.count), 1);

  return (
    <GlassCard className="space-y-4">
      <div className="flex items-center gap-2">
        <TrendingUp className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-lg font-semibold text-[#d0d0e8]">월별 라이브러리 추가</h2>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">추가 이력이 없습니다.</p>
      ) : (
        <div className="flex items-end gap-3 h-32">
          {items.map(({ month, label, count }) => {
            const height = Math.max(8, (count / max) * 100);
            const isMax = count === max && count > 0;
            return (
              <div key={month} className="flex-1 flex flex-col items-center gap-1.5 min-w-0">
                <span className="text-sm text-muted-foreground tabular-nums">{count}</span>
                <div
                  className={`w-full rounded-t-md transition-all duration-500 ${isMax ? "bg-accent" : "bg-accent/40"}`}
                  style={{ height: `${height}%` }}
                />
                <span className="text-sm text-muted-foreground truncate w-full text-center">{label}</span>
              </div>
            );
          })}
        </div>
      )}
    </GlassCard>
  );
}
