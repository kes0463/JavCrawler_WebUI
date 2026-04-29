import { cn } from "@/lib/utils";

export type StatusType =
  | "pending"
  | "running"
  | "done"
  | "error"
  | "warning"
  | "info"
  | "active"
  | "inactive";

const STATUS_CONFIG: Record<StatusType, { label: string; classes: string; dot: string }> = {
  pending:  { label: "대기",   classes: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20",   dot: "bg-zinc-400" },
  running:  { label: "진행",   classes: "bg-indigo-500/15 text-indigo-300 border-indigo-500/25", dot: "bg-indigo-400 animate-pulse" },
  done:     { label: "완료",   classes: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20", dot: "bg-emerald-400" },
  error:    { label: "오류",   classes: "bg-rose-500/15 text-rose-400 border-rose-500/20",   dot: "bg-rose-400" },
  warning:  { label: "경고",   classes: "bg-amber-500/15 text-amber-400 border-amber-500/20", dot: "bg-amber-400" },
  info:     { label: "정보",   classes: "bg-sky-500/15 text-sky-400 border-sky-500/20",      dot: "bg-sky-400" },
  active:   { label: "활성",   classes: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20", dot: "bg-emerald-400 animate-pulse" },
  inactive: { label: "비활성", classes: "bg-zinc-500/10 text-zinc-500 border-zinc-500/15",  dot: "bg-zinc-500" },
};

interface StatusBadgeProps {
  status: StatusType;
  label?: string;
  showDot?: boolean;
  className?: string;
}

export function StatusBadge({ status, label, showDot = true, className }: StatusBadgeProps) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-medium",
        cfg.classes,
        className,
      )}
    >
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />}
      {label ?? cfg.label}
    </span>
  );
}
