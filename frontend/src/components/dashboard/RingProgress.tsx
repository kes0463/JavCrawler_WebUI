import { cn } from "@/lib/utils";

interface RingProgressProps {
  value: number;
  label: string;
  detail?: string;
  className?: string;
}

export function RingProgress({ value, label, detail, className }: RingProgressProps) {
  const pct = Math.max(0, Math.min(100, value));
  const r = 46;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  const size = 112;

  return (
    <div className={cn("flex items-center gap-6", className)}>
      <div className="relative shrink-0">
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth="9"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="#10b981"
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
            style={{
              transition: "stroke-dashoffset 0.6s ease",
              filter: "drop-shadow(0 0 8px rgba(16,185,129,0.45))",
            }}
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-xl font-bold text-emerald-400">
          {pct.toFixed(1)}%
        </span>
      </div>
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-400 mb-1.5">{label}</p>
        {detail && <p className="text-base font-semibold text-slate-200">{detail}</p>}
      </div>
    </div>
  );
}
