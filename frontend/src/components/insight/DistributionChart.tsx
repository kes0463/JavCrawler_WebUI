import { GlassCard } from "@/components/ui/GlassCard";
import type { DistributionBlock } from "@/api/insight";

const COLORS = ["bg-indigo-500", "bg-violet-500", "bg-rose-500", "bg-amber-500", "bg-emerald-500"];

interface DistributionChartProps {
  distribution: DistributionBlock;
  title?: string;
}

function BarGroup({ label, items }: { label: string; items: { name: string; count: number }[] }) {
  const top = items.slice(0, 8);
  const max = Math.max(...top.map(i => i.count), 1);
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-slate-400">{label}</h3>
      {top.length === 0 ? (
        <p className="text-xs text-slate-600">—</p>
      ) : (
        top.map((item, i) => (
          <div key={item.name} className="space-y-0.5">
            <div className="flex justify-between text-xs">
              <span className="text-slate-300 truncate pr-2">{item.name}</span>
              <span className="text-slate-500 tabular-nums">{item.count}</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
              <div
                className={`h-full rounded-full ${COLORS[i % COLORS.length]}`}
                style={{ width: `${(item.count / max) * 100}%` }}
              />
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export function DistributionChart({ distribution, title = "라이브러리 수집 현황" }: DistributionChartProps) {
  return (
    <GlassCard className="space-y-5">
      <h2 className="text-lg font-semibold text-[#d0d0e8]">{title}</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <BarGroup label="장르" items={distribution.genres ?? []} />
        <BarGroup label="배우" items={distribution.actors ?? []} />
        <BarGroup label="제작사" items={distribution.makers ?? []} />
      </div>
    </GlassCard>
  );
}
