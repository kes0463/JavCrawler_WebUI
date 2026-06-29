import { cn } from "@/lib/utils";

interface ArcGaugeProps {
  label: string;
  sublabel?: string;
  value: number;
  accent?: "blue" | "orange";
  className?: string;
}

const ACCENT = {
  blue: { stroke: "#3b82f6", glow: "rgba(59,130,246,0.35)" },
  orange: { stroke: "#f97316", glow: "rgba(249,115,22,0.35)" },
};

export function ArcGauge({
  label,
  sublabel,
  value,
  accent = "blue",
  className,
}: ArcGaugeProps) {
  const pct = Math.max(0, Math.min(100, value));
  const colors = ACCENT[accent];
  const r = 58;
  const cx = 80;
  const cy = 76;
  const startX = cx - r;
  const endX = cx + r;
  const circumference = Math.PI * r;
  const offset = circumference - (pct / 100) * circumference;

  return (
    <div className={cn("flex flex-col items-center", className)}>
      <svg width="160" height="96" viewBox="0 0 160 96" className="overflow-visible">
        <defs>
          <filter id={`glow-${accent}`}>
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path
          d={`M ${startX} ${cy} A ${r} ${r} 0 0 1 ${endX} ${cy}`}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth="11"
          strokeLinecap="round"
        />
        <path
          d={`M ${startX} ${cy} A ${r} ${r} 0 0 1 ${endX} ${cy}`}
          fill="none"
          stroke={colors.stroke}
          strokeWidth="11"
          strokeLinecap="round"
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={offset}
          filter={`url(#glow-${accent})`}
          style={{ transition: "stroke-dashoffset 0.6s ease" }}
        />
        <text
          x={cx}
          y={cy - 6}
          textAnchor="middle"
          className="fill-white text-2xl font-bold"
          style={{ fontSize: "28px", fontWeight: 700 }}
        >
          {pct}%
        </text>
      </svg>
      <p className="text-base font-semibold text-white mt-2">{label}</p>
      {sublabel && (
        <p className="text-sm text-slate-400 truncate max-w-full px-1 mt-0.5">{sublabel}</p>
      )}
    </div>
  );
}
