import { cn } from "@/lib/utils";
import type { ToastLevel } from "@/contexts/ToastContext";

interface ToastNotificationProps {
  message: string;
  level?: ToastLevel;
  onDismiss?: () => void;
}

const LEVEL_CONFIG: Record<ToastLevel, { classes: string; icon: string }> = {
  info:    { classes: "bg-bg-panel/90 border-white/[0.10] text-[#d0d0e8]",        icon: "ℹ" },
  success: { classes: "bg-emerald-950/80 border-emerald-500/30 text-emerald-200", icon: "✓" },
  warn:    { classes: "bg-amber-950/80 border-amber-500/30 text-amber-200",       icon: "⚠" },
  error:   { classes: "bg-rose-950/80 border-rose-500/30 text-rose-200",          icon: "✕" },
};

export function ToastNotification({ message, level = "info", onDismiss }: ToastNotificationProps) {
  const cfg = LEVEL_CONFIG[level];

  return (
    <div
      className={cn(
        "flex items-center gap-2.5 px-4 py-3 rounded-xl border shadow-glass",
        "backdrop-blur-xl text-sm pointer-events-auto animate-fade-in",
        "min-w-[240px] max-w-[420px]",
        cfg.classes,
      )}
    >
      <span className="text-base shrink-0">{cfg.icon}</span>
      <span className="flex-1 leading-snug">{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="shrink-0 text-current opacity-40 hover:opacity-100 transition-opacity ml-1"
        >
          ✕
        </button>
      )}
    </div>
  );
}
