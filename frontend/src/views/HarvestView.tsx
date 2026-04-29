import { useState, useEffect, useRef, useCallback } from "react";
import { Plus, Play, Trash2, X, Loader2, CheckCircle, AlertCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  fetchQueue, addToQueue, removeFromQueue, startHarvest, clearQueue, createHarvestWS,
} from "@/api/harvest";
import type { HarvestItem, HarvestQueueResponse } from "@/api/harvest";
import { GlassCard } from "@/components/ui/GlassCard";
import { ActionButton } from "@/components/ui/ActionButton";

export default function HarvestView() {
  const [state, setState] = useState<HarvestQueueResponse>({ items: [], running: false });
  const [input, setInput] = useState("");
  const [adding, setAdding] = useState(false);
  const [starting, setStarting] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  // 초기 로드 + WebSocket 연결
  useEffect(() => {
    fetchQueue().then(setState);

    const ws = createHarvestWS((event) => {
      if (event.type === "state") {
        setState({ items: event.items, running: event.running });
      } else if (event.type === "queue_started") {
        setState(s => ({ ...s, running: true }));
      } else if (event.type === "queue_finished") {
        setState(s => ({ ...s, running: false }));
        fetchQueue().then(setState); // 최종 상태 동기화
      } else if (event.type === "item_started") {
        setState(s => ({
          ...s,
          items: s.items.map(i => i.id === event.id ? { ...i, status: "running", progress: 0 } : i),
        }));
      } else if (event.type === "item_done") {
        setState(s => ({
          ...s,
          items: s.items.map(i => i.id === event.id ? { ...i, status: "done", progress: 100 } : i),
        }));
      } else if (event.type === "item_error") {
        setState(s => ({
          ...s,
          items: s.items.map(i => i.id === event.id ? { ...i, status: "error", message: event.message } : i),
        }));
      } else if (event.type === "progress") {
        setState(s => ({
          ...s,
          items: s.items.map(i => i.id === event.id ? { ...i, progress: event.progress, message: event.message } : i),
        }));
      }
    });

    wsRef.current = ws;
    return () => ws.close();
  }, []);

  const handleAdd = useCallback(async () => {
    const codes = input.split(/[\s,\n]+/).map(c => c.trim().toUpperCase()).filter(Boolean);
    if (!codes.length) return;
    setAdding(true);
    try {
      const res = await addToQueue(codes);
      setState(res);
      setInput("");
    } finally {
      setAdding(false);
    }
  }, [input]);

  const handleStart = useCallback(async () => {
    setStarting(true);
    try {
      await startHarvest();
    } catch (e) {
      alert(e instanceof Error ? e.message : "실패");
    } finally {
      setStarting(false);
    }
  }, []);

  const handleRemove = useCallback(async (id: string) => {
    await removeFromQueue(id);
    setState(s => ({ ...s, items: s.items.filter(i => i.id !== id) }));
  }, []);

  const handleClear = useCallback(async () => {
    await clearQueue();
    setState(s => ({ ...s, items: [] }));
  }, []);

  const pendingCount = state.items.filter(i => i.status === "pending").length;
  const doneCount = state.items.filter(i => i.status === "done").length;
  const errorCount = state.items.filter(i => i.status === "error").length;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

      {/* ── 입력 패널 ── */}
      <div className="space-y-4">
        <GlassCard className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            품번 입력
          </h3>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && e.ctrlKey) handleAdd(); }}
            placeholder={"STARS-001\nIPX-002\nMIDE-003\n\n여러 개는 줄바꿈 또는 쉼표로 구분\nCtrl+Enter로 추가"}
            rows={8}
            className={cn(
              "w-full px-3 py-2.5 text-sm rounded-xl resize-none",
              "bg-bg-base border border-white/[0.08] text-white placeholder:text-muted-foreground",
              "focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30",
              "transition-all duration-150",
            )}
          />
          <ActionButton
            variant="primary"
            className="w-full"
            loading={adding}
            icon={<Plus className="w-3.5 h-3.5" />}
            onClick={handleAdd}
            disabled={!input.trim()}
          >
            큐에 추가
          </ActionButton>
        </GlassCard>

        {/* 안내 */}
        <GlassCard variant="subtle" className="text-xs text-muted-foreground space-y-1.5">
          <p className="text-[#c8c8e0] font-medium">수집 순서</p>
          <ol className="space-y-1 list-decimal list-inside">
            <li>품번을 입력하고 큐에 추가</li>
            <li>큐 확인 후 수집 시작</li>
            <li>메타데이터 + 표지 자동 저장</li>
          </ol>
        </GlassCard>
      </div>

      {/* ── 큐 패널 ── */}
      <div className="lg:col-span-2 space-y-4">

        {/* 큐 헤더 */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">대기</span>
            <span className="text-white font-bold tabular-nums">{pendingCount}</span>
            <span className="text-muted-foreground">/ 완료</span>
            <span className="text-emerald-400 font-bold tabular-nums">{doneCount}</span>
            {errorCount > 0 && (
              <>
                <span className="text-muted-foreground">/ 오류</span>
                <span className="text-rose-400 font-bold tabular-nums">{errorCount}</span>
              </>
            )}
          </div>

          <div className="flex items-center gap-2 ml-auto">
            {!state.running && state.items.some(i => i.status !== "done") && (
              <ActionButton
                variant="ghost"
                size="sm"
                onClick={handleClear}
                disabled={state.running}
              >
                전체 삭제
              </ActionButton>
            )}
            <ActionButton
              variant="primary"
              size="sm"
              loading={starting || state.running}
              icon={state.running
                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                : <Play className="w-3.5 h-3.5" />}
              onClick={handleStart}
              disabled={state.running || pendingCount === 0}
            >
              {state.running ? "수집 중..." : "수집 시작"}
            </ActionButton>
          </div>
        </div>

        {/* 큐 목록 */}
        {state.items.length === 0 ? (
          <GlassCard variant="subtle" className="flex items-center justify-center h-48 text-muted-foreground text-sm">
            큐가 비어 있습니다
          </GlassCard>
        ) : (
          <div className="space-y-2">
            {state.items.map(item => (
              <QueueRow
                key={item.id}
                item={item}
                onRemove={handleRemove}
                disabled={state.running}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── QueueRow ─────────────────────────────────────────────────────

function QueueRow({
  item,
  onRemove,
  disabled,
}: {
  item: HarvestItem;
  onRemove: (id: string) => void;
  disabled: boolean;
}) {
  const isRunning = item.status === "running";
  const isDone = item.status === "done";
  const isError = item.status === "error";

  return (
    <GlassCard
      noPadding
      className={cn(
        "px-4 py-3 flex items-center gap-3 transition-all duration-200",
        isRunning && "border-indigo-500/30 bg-indigo-500/5",
        isDone && "border-emerald-500/20 opacity-70",
        isError && "border-rose-500/20 bg-rose-500/5",
      )}
    >
      {/* 상태 아이콘 */}
      <StatusIcon status={item.status} />

      {/* 품번 */}
      <span className="font-mono text-sm text-indigo-300 w-28 shrink-0">{item.target}</span>

      {/* 진행 메시지 / 상태 */}
      <div className="flex-1 min-w-0">
        {isRunning ? (
          <div className="space-y-1">
            <p className="text-xs text-[#c8c8e0] truncate">{item.message || "처리 중..."}</p>
            <div className="h-1 rounded-full bg-white/[0.06] overflow-hidden">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all duration-500"
                style={{ width: `${item.progress}%` }}
              />
            </div>
          </div>
        ) : (
          <p className={cn(
            "text-xs truncate",
            isDone && "text-emerald-400",
            isError && "text-rose-400",
            !isDone && !isError && "text-muted-foreground",
          )}>
            {item.message || statusLabel(item.status)}
          </p>
        )}
      </div>

      {/* 진행률 */}
      {isRunning && (
        <span className="text-xs tabular-nums text-indigo-400 shrink-0">{item.progress}%</span>
      )}

      {/* 삭제 버튼 */}
      {!isRunning && (
        <button
          onClick={() => onRemove(item.id)}
          disabled={disabled && isRunning}
          className="w-6 h-6 rounded-lg flex items-center justify-center text-muted-foreground hover:text-white hover:bg-white/[0.06] transition-colors shrink-0"
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </GlassCard>
  );
}

function StatusIcon({ status }: { status: HarvestItem["status"] }) {
  if (status === "running") return <Loader2 className="w-4 h-4 text-indigo-400 animate-spin shrink-0" />;
  if (status === "done") return <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />;
  if (status === "error") return <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />;
  return <Clock className="w-4 h-4 text-muted-foreground shrink-0" />;
}

function statusLabel(status: HarvestItem["status"]): string {
  if (status === "pending") return "대기 중";
  if (status === "done") return "완료";
  if (status === "error") return "오류";
  return "";
}
