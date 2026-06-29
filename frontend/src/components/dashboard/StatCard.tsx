import type { LucideIcon } from "lucide-react";
import { TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { GlowCard, type GlowAccent } from "@/components/ui/GlowCard";
import { Sparkline } from "./Sparkline";

interface StatCardProps {
  label: string;
  value: string;
  delta?: string;
  icon: LucideIcon;
  accent?: GlowAccent;
  sparkline?: number[];
  children?: React.ReactNode;
  className?: string;
}

const ICON_BG: Record<GlowAccent, string> = {
  blue: "bg-blue-500/15 text-blue-400",
  green: "bg-emerald-500/15 text-emerald-400",
  orange: "bg-orange-500/15 text-orange-400",
  pink: "bg-rose-500/15 text-rose-400",
  purple: "bg-violet-500/15 text-violet-400",
  none: "bg-white/5 text-slate-300",
};

export function StatCard({
  label,
  value,
  delta,
  icon: Icon,
  accent = "blue",
  sparkline,
  children,
  className,
}: StatCardProps) {
  return (
    <GlowCard accent={accent} className={cn("space-y-5 h-full min-h-[160px] !p-6", className)}>
      <div className="flex items-start justify-between gap-3">
        <span className="text-base font-medium text-slate-300 leading-tight">{label}</span>
        <div
          className={cn(
            "w-11 h-11 rounded-xl flex items-center justify-center shrink-0 border border-white/[0.06]",
            ICON_BG[accent],
          )}
        >
          <Icon className="w-5 h-5" />
        </div>
      </div>
      {children ?? (
        <>
          <div>
            <p className="text-3xl font-bold tabular-nums leading-none text-white tracking-tight">
              {value}
            </p>
            {delta && (
              <p className="text-sm text-slate-400 mt-2 flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 shrink-0 text-emerald-400" />
                {delta}
              </p>
            )}
          </div>
          {sparkline && (
            <Sparkline
              values={sparkline}
              color={accent === "pink" ? "#f43f5e" : "#6366f1"}
            />
          )}
        </>
      )}
    </GlowCard>
  );
}
