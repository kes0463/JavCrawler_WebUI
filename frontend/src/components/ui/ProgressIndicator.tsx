import { cn } from "@/lib/utils";

interface ProgressIndicatorProps {
  value: number;
  total?: number;
  showLabel?: boolean;
  size?: "sm" | "md" | "lg";
  variant?: "default" | "accent" | "success" | "warning";
  className?: string;
}

const VARIANT_COLORS = {
  default: "bg-indigo-500",
  accent:  "bg-violet-500",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
};

export function ProgressIndicator({
  value,
  total = 100,
  showLabel = false,
  size = "md",
  variant = "default",
  className,
}: ProgressIndicatorProps) {
  const pct = Math.min(100, Math.max(0, total > 0 ? (value / total) * 100 : 0));

  return (
    <div className={cn("w-full", className)}>
      {showLabel && (
        <div className="flex justify-between text-sm text-muted-foreground mb-1">
          <span>{value.toLocaleString()} / {total.toLocaleString()}</span>
          <span>{Math.round(pct)}%</span>
        </div>
      )}
      <div
        className={cn(
          "w-full rounded-full overflow-hidden bg-white/[0.06]",
          size === "sm" && "h-1",
          size === "md" && "h-1.5",
          size === "lg" && "h-2.5",
        )}
      >
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500 ease-out",
            VARIANT_COLORS[variant],
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
