import { cn } from "@/lib/utils";
import { useStickToBottomScroll } from "@/hooks/useStickToBottomScroll";

export interface LogEntry {
  id: string | number;
  text: string;
  level?: "info" | "warn" | "error" | "debug" | "success";
  ts?: string;
}

interface LogPanelProps {
  entries: LogEntry[];
  autoScroll?: boolean;
  maxHeight?: string;
  className?: string;
}

const LEVEL_CONFIG: Record<string, { color: string; prefix: string }> = {
  info:    { color: "text-[#c8c8e0]",    prefix: "[INFO]" },
  warn:    { color: "text-amber-400",    prefix: "[WARN]" },
  error:   { color: "text-rose-400",     prefix: "[ERR ]" },
  debug:   { color: "text-zinc-500",     prefix: "[DBG ]" },
  success: { color: "text-emerald-400",  prefix: "[ OK ]" },
};

export function LogPanel({ entries, autoScroll = true, maxHeight = "240px", className }: LogPanelProps) {
  const { containerRef, onScroll } = useStickToBottomScroll(entries, autoScroll);

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      className={cn(
        "rounded-xl border border-white/[0.06] bg-bg-base overflow-y-auto no-scrollbar font-mono text-sm",
        className,
      )}
      style={{ maxHeight }}
    >
      {entries.length === 0 ? (
        <div className="flex items-center justify-center h-16 text-muted-foreground text-base">
          로그 없음
        </div>
      ) : (
        <div className="p-3 space-y-0.5">
          {entries.map(e => {
            const { color, prefix } = LEVEL_CONFIG[e.level ?? "info"];
            return (
              <div key={e.id} className="flex gap-2 leading-relaxed">
                {e.ts && <span className="text-zinc-600 shrink-0">{e.ts}</span>}
                <span className={cn("shrink-0", color)}>{prefix}</span>
                <span className={cn("break-all", color)}>{e.text}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
