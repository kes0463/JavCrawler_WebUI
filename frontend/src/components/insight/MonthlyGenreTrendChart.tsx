import { GlassCard } from "@/components/ui/GlassCard";

interface GenreMonth {
  month: string;
  genres: { name: string; count: number }[];
}

interface MonthlyGenreTrendChartProps {
  items: GenreMonth[];
}

export function MonthlyGenreTrendChart({ items }: MonthlyGenreTrendChartProps) {
  if (!items.length) {
    return (
      <GlassCard>
        <h2 className="text-lg font-semibold text-[#d0d0e8] mb-2">월별 시청 장르</h2>
        <p className="text-sm text-slate-500">최근 시청 이력이 쌓이면 월별로 어떤 장르를 많이 봤는지 보여 드립니다.</p>
      </GlassCard>
    );
  }

  return (
    <GlassCard className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-[#d0d0e8]">월별 시청 장르</h2>
        <p className="text-sm text-muted-foreground mt-1">
          매달 실제로 재생한 작품의 장르 비중입니다. 시간이 지나며 선호가 바뀌었는지 확인할 수 있습니다.
        </p>
      </div>
      <div className="space-y-4">
        {items.map(row => {
          const total = (row.genres ?? []).reduce((s, g) => s + g.count, 0) || 1;
          return (
            <div key={row.month} className="space-y-2">
              <p className="text-sm font-medium text-slate-300">{row.month}</p>
              <div className="space-y-1.5">
                {(row.genres ?? []).map(g => (
                  <div key={g.name} className="flex items-center gap-3 text-sm">
                    <span className="text-slate-400 w-24 shrink-0 truncate">{g.name}</span>
                    <div className="flex-1 h-2 rounded-full bg-white/[0.06] overflow-hidden">
                      <div
                        className="h-full rounded-full bg-violet-500/80"
                        style={{ width: `${Math.round((g.count / total) * 100)}%` }}
                      />
                    </div>
                    <span className="text-slate-500 tabular-nums w-8 text-right">{g.count}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </GlassCard>
  );
}
