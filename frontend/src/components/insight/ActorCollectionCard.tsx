import { GlassCard } from "@/components/ui/GlassCard";
import { ProgressIndicator } from "@/components/ui/ProgressIndicator";
import type { ActorCollections } from "@/api/insight";

interface ActorCollectionCardProps {
  data: ActorCollections;
}

export function ActorCollectionCard({ data }: ActorCollectionCardProps) {
  const actors = data.actors ?? [];
  if (!data.has_data && !actors.length) {
    return (
      <GlassCard>
        <h2 className="text-lg font-semibold text-[#d0d0e8] mb-2">배우별 컬렉션</h2>
        <p className="text-sm text-slate-500">배우별 시청 데이터가 없습니다.</p>
      </GlassCard>
    );
  }

  return (
    <GlassCard className="space-y-4">
      <h2 className="text-lg font-semibold text-[#d0d0e8]">배우별 컬렉션 완성도</h2>
      <div className="space-y-3">
        {actors.map(row => {
          const pct = Math.round((row.completion_rate ?? (row.total ? row.watched / row.total : 0)) * 100);
          return (
            <div key={row.name} className="space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-slate-200 truncate pr-2">{row.name}</span>
                <span className="text-muted-foreground tabular-nums shrink-0">
                  {row.watched}/{row.total}편
                  {(row.remaining ?? row.unwatched ?? 0) > 0 &&
                    ` · ${row.remaining ?? row.unwatched} 미감상`}
                </span>
              </div>
              <ProgressIndicator value={pct} size="sm" />
            </div>
          );
        })}
      </div>
    </GlassCard>
  );
}
