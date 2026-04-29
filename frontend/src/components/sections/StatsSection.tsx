import { cn } from "@/lib/utils";
import type { Stats } from "@/lib/types";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";

const STAT_ITEMS: { label: string; key: keyof Stats; color: string }[] = [
  { label: "전체", key: "total",      color: "text-white" },
  { label: "완료", key: "completed",  color: "text-emerald-400" },
  { label: "진행", key: "inProgress", color: "text-indigo-400" },
  { label: "대기", key: "pending",    color: "text-amber-400" },
];

interface StatsSectionProps {
  data: Stats | null;
  loading: boolean;
}

export function StatsSection({ data, loading }: StatsSectionProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {loading
        ? STAT_ITEMS.map((_, i) => (
            <GlassCard key={i} className="space-y-2.5">
              <Skeleton className="h-2.5 w-16" />
              <Skeleton className="h-7 w-24" />
            </GlassCard>
          ))
        : STAT_ITEMS.map(({ label, key, color }) => (
            <GlassCard key={key} className="animate-scale-in">
              <p className="text-[11px] text-muted-foreground">{label}</p>
              <p className={cn("text-2xl font-bold tabular-nums mt-0.5", color)}>
                {data?.[key]?.toLocaleString() ?? "—"}
              </p>
            </GlassCard>
          ))}
    </div>
  );
}
