import { GlassCard } from "@/components/ui/GlassCard";
import type { DistributionBlock, InsightStats } from "@/api/insight";

interface InsightKpiGridProps {
  stats: Partial<InsightStats>;
  distribution?: DistributionBlock;
}

function formatNum(n: number) {
  return n.toLocaleString("ko-KR");
}

export function InsightKpiGrid({ stats, distribution }: InsightKpiGridProps) {
  const safe = {
    total: stats?.total ?? 0,
    completed: stats?.completed ?? 0,
    completion_rate: stats?.completion_rate ?? 0,
    avg_rating: stats?.avg_rating ?? 0,
    rated_count: stats?.rated_count ?? 0,
    watched_count: stats?.watched_count ?? 0,
    total_watch_hours: stats?.total_watch_hours ?? 0,
  };
  const actorCount = distribution?.actors?.length ?? 0;
  const completionPct = Math.round(safe.completion_rate * 100);

  const cards = [
    { label: "전체 작품", value: formatNum(safe.total), sub: "라이브러리", icon: "📚", color: "text-white" },
    { label: "평균 별점", value: safe.avg_rating ? safe.avg_rating.toFixed(1) : "—", sub: `${safe.rated_count}편 평가`, icon: "⭐", color: "text-amber-400" },
    { label: "시청 완료율", value: `${completionPct}%`, sub: `${safe.completed} / ${safe.watched_count}편`, icon: "✅", color: "text-emerald-400" },
    { label: "총 시청", value: `${safe.total_watch_hours.toFixed(1)}h`, sub: actorCount ? `배우 ${actorCount}명` : "시청 시간", icon: "⏱", color: "text-indigo-400" },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map(({ label, value, sub, icon, color }) => (
        <GlassCard key={label} hoverable>
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm text-muted-foreground">{label}</p>
              <p className={`text-3xl font-bold tabular-nums mt-1 ${color}`}>{value}</p>
              <p className="text-sm text-muted-foreground mt-0.5">{sub}</p>
            </div>
            <span className="text-3xl">{icon}</span>
          </div>
        </GlassCard>
      ))}
    </div>
  );
}
