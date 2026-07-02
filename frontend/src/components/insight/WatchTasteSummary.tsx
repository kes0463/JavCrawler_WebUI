import { GlassCard } from "@/components/ui/GlassCard";
import { ProgressIndicator } from "@/components/ui/ProgressIndicator";

export interface WatchSummaryItem {
  name: string;
  count: number;
  share_pct?: number;
}

export interface WatchSummary {
  watched_count?: number;
  has_data?: boolean;
  top_genres?: WatchSummaryItem[];
  top_actors?: WatchSummaryItem[];
  scene_tags?: { tag?: string; count?: number }[];
  empty_message?: string;
}

interface WatchTasteSummaryProps {
  summary: WatchSummary;
}

export function WatchTasteSummary({ summary }: WatchTasteSummaryProps) {
  if (!summary.has_data) {
    return (
      <GlassCard>
        <h2 className="text-lg font-semibold text-[#d0d0e8] mb-2">시청 기록 요약</h2>
        <p className="text-sm text-slate-500">{summary.empty_message ?? "시청 이력이 없습니다."}</p>
      </GlassCard>
    );
  }

  const genres = summary.top_genres ?? [];
  const actors = summary.top_actors ?? [];

  return (
    <GlassCard className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-[#d0d0e8]">시청 기록 요약</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          실제로 재생한 {summary.watched_count ?? 0}편 기준 — 자주 본 장르·배우입니다.
        </p>
      </div>

      {genres.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-slate-400">자주 본 장르</h3>
          {genres.map(g => (
            <div key={g.name} className="space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-slate-200">{g.name}</span>
                <span className="text-slate-500 tabular-nums">{g.share_pct ?? 0}% · {g.count}회</span>
              </div>
              <ProgressIndicator value={g.share_pct ?? 0} size="sm" />
            </div>
          ))}
        </div>
      )}

      {actors.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-slate-400">자주 본 배우</h3>
          {actors.map(a => (
            <div key={a.name} className="space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-slate-200">{a.name}</span>
                <span className="text-slate-500 tabular-nums">{a.share_pct ?? 0}% · {a.count}편</span>
              </div>
              <ProgressIndicator value={a.share_pct ?? 0} size="sm" />
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
