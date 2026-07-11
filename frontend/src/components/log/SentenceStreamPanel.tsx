import { useMemo } from "react";
import { cn } from "@/lib/utils";
import type { SentenceLineEntry } from "@/api/processing";
import { useStickToBottomScroll } from "@/hooks/useStickToBottomScroll";

interface SentenceStreamPanelProps {
  entries: SentenceLineEntry[];
  autoScroll?: boolean;
  maxHeight?: string;
  className?: string;
}

function formatTime(sec?: number): string {
  if (sec == null || Number.isNaN(sec)) return "";
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

export function SentenceStreamPanel({
  entries,
  autoScroll = true,
  maxHeight = "280px",
  className,
}: SentenceStreamPanelProps) {
  const sortedEntries = useMemo(() => {
    return [...entries].sort((a, b) => {
      const ai = a.index ?? -1;
      const bi = b.index ?? -1;
      if (ai >= 0 && bi >= 0 && ai !== bi) return ai - bi;
      const as = a.start ?? Number.POSITIVE_INFINITY;
      const bs = b.start ?? Number.POSITIVE_INFINITY;
      if (as !== bs) return as - bs;
      return a.id.localeCompare(b.id);
    });
  }, [entries]);

  const { containerRef, onScroll } = useStickToBottomScroll(sortedEntries, autoScroll);

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      className={cn(
        "rounded-xl border border-white/[0.06] bg-bg-base overflow-y-auto no-scrollbar text-sm",
        className,
      )}
      style={{ maxHeight }}
    >
      {entries.length === 0 ? (
        <div className="flex items-center justify-center h-20 text-muted-foreground text-base px-4 text-center">
          STT 전사 또는 번역이 진행되면 문장이 여기에 표시됩니다
        </div>
      ) : (
        <div className="p-3 space-y-1.5">
          {sortedEntries.map(e => (
            <div key={e.id} className="flex gap-2 leading-relaxed">
              {e.ts && <span className="text-zinc-600 shrink-0 font-mono text-xs pt-0.5">{e.ts}</span>}
              <span className="text-zinc-500 shrink-0 font-mono text-xs pt-0.5 w-10 text-right">
                {formatTime(e.start)}
              </span>
              <span
                className={cn(
                  "break-all",
                  e.lang === "ja" ? "text-sky-300/90" : "text-[#c8c8e0]",
                )}
              >
                {e.text}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
