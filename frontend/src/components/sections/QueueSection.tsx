import { cn } from "@/lib/utils";
import type { Queue, QueueItem } from "@/lib/types";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton, SkeletonText } from "@/components/ui/Skeleton";

interface QueueSectionProps {
  data: Queue[] | null;
  loading: boolean;
}

export function QueueSection({ data, loading }: QueueSectionProps) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map(i => (
          <GlassCard key={i} className="space-y-2.5">
            <div className="flex items-center gap-2">
              <Skeleton className="w-2 h-2 rounded-full" />
              <Skeleton className="h-2.5 w-20" />
            </div>
            <SkeletonText lines={2} />
          </GlassCard>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {data?.map((q, i) => (
        <GlassCard
          key={q.id}
          hoverable
          className="space-y-2.5 animate-slide-in"
          style={{ animationDelay: `${i * 80}ms` } as React.CSSProperties}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ background: q.color }} />
              <span className="text-sm font-medium">{q.label}</span>
            </div>
            <span className="text-xs text-muted-foreground">{q.items.length}건</span>
          </div>
          <div className="space-y-1.5">
            {q.items.map(item => (
              <QueueRow key={item.code} item={item} color={q.color} />
            ))}
          </div>
        </GlassCard>
      ))}
    </div>
  );
}

// ── QueueRow ─────────────────────────────────────────────────────────

interface QueueRowProps {
  item: QueueItem;
  color: string;
}

function QueueRow({ item, color }: QueueRowProps) {
  const isProcessing = item.status === "processing";
  return (
    <div className="flex items-center gap-2 text-xs">
      <span
        className={cn("w-1.5 h-1.5 rounded-full shrink-0", isProcessing && "animate-pulse")}
        style={{ background: isProcessing ? color : "rgba(255,255,255,0.18)" }}
      />
      <span className="font-mono text-indigo-400 shrink-0 w-[72px] truncate">{item.code}</span>
      <span className="text-muted-foreground truncate flex-1">{item.title}</span>
      {isProcessing && (
        <span className="text-[10px] shrink-0 tabular-nums font-medium" style={{ color }}>
          {item.progress}%
        </span>
      )}
    </div>
  );
}
