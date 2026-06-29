import { X, Loader2, CheckCircle, AlertCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { ProgressIndicator } from "@/components/ui/ProgressIndicator";

export interface QueueItem {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "error";
  progress?: number;
  message?: string;
}

interface QueueItemRowProps {
  item: QueueItem;
  onRemove?: (id: string) => void;
  disabled?: boolean;
}

function StatusIcon({ status }: { status: QueueItem["status"] }) {
  if (status === "running") return <Loader2 className="w-4 h-4 text-indigo-400 animate-spin shrink-0" />;
  if (status === "done")    return <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />;
  if (status === "error")   return <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />;
  return <Clock className="w-4 h-4 text-zinc-600 shrink-0" />;
}

const STATUS_LABEL: Record<QueueItem["status"], string> = {
  pending: "대기 중",
  running: "처리 중",
  done:    "완료",
  error:   "오류",
};

export function QueueItemRow({ item, onRemove, disabled }: QueueItemRowProps) {
  const isRunning = item.status === "running";
  const isDone    = item.status === "done";
  const isError   = item.status === "error";

  return (
    <div
      className={cn(
        "relative flex items-center gap-3 px-4 py-3 rounded-xl border",
        "transition-all duration-200 ease-spring overflow-hidden",
        "bg-bg-card",
        // 기본 border
        !isRunning && !isError && "border-white/[0.07]",
        // 실행 중: 인디고 글로우
        isRunning && [
          "border-indigo-500/25",
          "shadow-[0_0_0_1px_rgba(99,102,241,0.08),0_4px_20px_rgba(99,102,241,0.07)]",
        ],
        // 완료: 살짝 흐리게
        isDone && "border-white/[0.05] opacity-55",
        // 오류: 로즈 tint
        isError && "border-rose-500/20 bg-rose-950/20",
      )}
    >
      {/* 실행 중 좌측 액센트 바 */}
      {isRunning && (
        <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full bg-indigo-500 shadow-glow-sm" />
      )}

      <StatusIcon status={item.status} />

      <span className="font-mono text-base text-indigo-300/90 shrink-0 min-w-[7rem] truncate">
        {item.label}
      </span>

      <div className="flex-1 min-w-0 space-y-1.5">
        {isRunning ? (
          <>
            <p className="text-sm text-[#c8c8e0]/80 truncate">{item.message || "처리 중..."}</p>
            <ProgressIndicator value={item.progress ?? 0} size="sm" />
          </>
        ) : (
          <p className={cn(
            "text-sm truncate",
            isDone  && "text-emerald-400/80",
            isError && "text-rose-400",
            !isDone && !isError && "text-muted-foreground/70",
          )}>
            {item.message || STATUS_LABEL[item.status]}
          </p>
        )}
      </div>

      {isRunning && (
        <span className="text-sm tabular-nums text-indigo-400 font-medium shrink-0 min-w-[2.5rem] text-right">
          {item.progress ?? 0}%
        </span>
      )}

      {!isRunning && onRemove && (
        <button
          onClick={() => onRemove(item.id)}
          disabled={disabled}
          className={cn(
            "w-6 h-6 rounded-lg shrink-0 flex items-center justify-center",
            "text-zinc-600 hover:text-zinc-300 hover:bg-white/[0.07]",
            "transition-all duration-150",
            "disabled:opacity-25 disabled:pointer-events-none",
          )}
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}
