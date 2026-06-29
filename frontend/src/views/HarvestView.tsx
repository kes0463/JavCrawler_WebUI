import { useState, useEffect, useRef, useCallback } from "react";
import {
  Plus, Play, Trash2, X, Loader2, CheckCircle, AlertCircle, Clock,
  FolderOpen, FolderTree, Heart, RotateCcw, Ban, Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  fetchQueue, addToQueue, removeFromQueue, startHarvest, clearQueue, createHarvestWS,
  queueFolder, queueFolders, queueParentFolder, startStaged, cancelHarvestItem, clearFinished,
  patchHarvestSettings, harvestFavorites, parseHarvestCodes, isPlausibleHarvestCode,
  pickFoldersDialog,
} from "@/api/harvest";
import type { HarvestItem, HarvestQueueResponse, LogEntry } from "@/api/harvest";
import { extractFolderPathsFromDataTransfer } from "@/lib/folderPaths";
import { GlassCard } from "@/components/ui/GlassCard";
import { ActionButton } from "@/components/ui/ActionButton";
import { LogPanel } from "@/components/log/LogPanel";
import { useToast } from "@/contexts/ToastContext";
import { useNavigation } from "@/contexts/NavigationContext";

let logSeq = 0;

export default function HarvestView() {
  const { showToast } = useToast();
  const { currentView } = useNavigation();
  const [state, setState] = useState<HarvestQueueResponse>({ items: [], running: false, grok_enabled: false });
  const [input, setInput] = useState("");
  const [folderPath, setFolderPath] = useState("");
  const [autoStart, setAutoStart] = useState(true);
  const [grokEnabled, setGrokEnabled] = useState(false);
  const [adding, setAdding] = useState(false);
  const [starting, setStarting] = useState(false);
  const [folderBusy, setFolderBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const dragDepthRef = useRef(0);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [favRunning, setFavRunning] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchQueue().then(snap => {
      setState(snap);
      if (snap.grok_enabled !== undefined) setGrokEnabled(snap.grok_enabled);
    });

    const ws = createHarvestWS((event) => {
      if (event.type === "state") {
        setState(s => ({
          ...s,
          items: event.items,
          running: event.running,
          grok_enabled: event.grok_enabled ?? s.grok_enabled,
        }));
        if (event.grok_enabled !== undefined) setGrokEnabled(event.grok_enabled);
      } else if (event.type === "queue_started") {
        setState(s => ({ ...s, running: true }));
        fetchQueue().then(setState);
      } else if (event.type === "queue_finished") {
        setState(s => ({ ...s, running: false }));
        fetchQueue().then(setState);
      } else if (event.type === "item_started") {
        setState(s => ({
          ...s,
          items: s.items.map(i => i.id === event.id ? { ...i, status: "running", progress: 0 } : i),
        }));
      } else if (event.type === "item_done") {
        setState(s => ({
          ...s,
          items: s.items.map(i => i.id === event.id ? {
            ...i,
            status: "done",
            progress: event.progress ?? 100,
            message: event.message || "완료",
          } : i),
        }));
      } else if (event.type === "item_error") {
        setState(s => ({
          ...s,
          items: s.items.map(i => i.id === event.id ? { ...i, status: "error", message: event.message } : i),
        }));
      } else if (event.type === "item_cancelled") {
        setState(s => ({ ...s, items: s.items.filter(i => i.id !== event.id) }));
      } else if (event.type === "progress") {
        setState(s => ({
          ...s,
          items: s.items.map(i => i.id === event.id ? { ...i, progress: event.progress, message: event.message } : i),
        }));
      } else if (event.type === "log") {
        const level = (["info", "warn", "error", "debug", "success"].includes(event.level)
          ? event.level
          : "info") as LogEntry["level"];
        setLogs(prev => [...prev.slice(-199), {
          id: `log-${++logSeq}`,
          level,
          text: event.text,
          ts: event.ts,
        }]);
      } else if (event.type === "folder_planned") {
        showToast(`폴더 ${event.count}건 스테이징 (${event.path})`, "info");
        fetchQueue().then(setState);
      } else if (event.type === "harvest_alert") {
        showToast(event.message, "success");
      } else if (event.type === "favorites_started") {
        setFavRunning(true);
        showToast(`♥ 좋아요 수집 시작 (${event.total}건)`, "info");
      } else if (event.type === "favorites_finished") {
        setFavRunning(false);
        showToast(
          `♥ 완료: 갱신 ${event.updated} / 0점 ${event.zero} / 실패 ${event.failed}`,
          event.failed ? "warn" : "success",
        );
      } else if (event.type === "favorites_error") {
        setFavRunning(false);
        showToast(event.message, "error");
      }
    });

    wsRef.current = ws;
    return () => ws.close();
  }, [showToast]);

  // 다른 탭(라이브러리 재크롤 등)에서 큐가 바뀐 뒤 Harvest로 돌아올 때 동기화
  useEffect(() => {
    if (currentView !== "harvest") return;
    fetchQueue().then(snap => {
      setState(snap);
      if (snap.grok_enabled !== undefined) setGrokEnabled(snap.grok_enabled);
    });
  }, [currentView]);

  const handleAdd = useCallback(async () => {
    const codes = parseHarvestCodes(input);
    if (!codes.length) return;
    const valid = codes.filter(isPlausibleHarvestCode);
    const invalid = codes.filter(c => !isPlausibleHarvestCode(c));
    if (invalid.length) {
      showToast(`올바르지 않은 품번: ${invalid.join(", ")} (예: STARS-001)`, "warn");
    }
    if (!valid.length) return;
    setAdding(true);
    try {
      const res = await addToQueue(valid, autoStart);
      setState(res);
      setInput("");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "추가 실패", "error");
    } finally {
      setAdding(false);
    }
  }, [input, autoStart, showToast]);

  const handleStart = useCallback(async () => {
    const pending = state.items.filter(i => i.status === "pending" && !i.staged);
    const staged = state.items.filter(i => i.staged && i.status === "pending");
    if (!pending.length && !staged.length) {
      showToast("큐에 실행할 항목이 없습니다", "warn");
      return;
    }
    setStarting(true);
    try {
      if (staged.length) {
        await startStaged();
      } else {
        await startHarvest();
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "시작 실패", "error");
    } finally {
      setStarting(false);
    }
  }, [state.items, showToast]);

  const handleQueueFolders = useCallback(async (paths: string[]) => {
    const normalized = [...new Set(paths.map(p => p.trim()).filter(Boolean))];
    if (!normalized.length) {
      showToast("드롭된 경로를 인식하지 못했습니다 (Windows 탐색기에서 폴더를 드롭하세요)", "warn");
      return;
    }
    setFolderBusy(true);
    try {
      const res = await queueFolders(normalized);
      setState(res);
      if (res.warnings?.length) {
        showToast(res.warnings.join("\n"), "warn");
      } else {
        showToast(`${normalized.length}개 폴더 큐에 스테이징`, "info");
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "폴더 큐 실패", "error");
    } finally {
      setFolderBusy(false);
    }
  }, [showToast]);

  const handleBrowseFolders = useCallback(async () => {
    setFolderBusy(true);
    try {
      const paths = await pickFoldersDialog();
      if (!paths.length) return;
      await handleQueueFolders(paths);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "폴더 선택 실패", "error");
    } finally {
      setFolderBusy(false);
    }
  }, [handleQueueFolders, showToast]);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragDepthRef.current += 1;
    if (dragDepthRef.current === 1) setDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setDragging(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragDepthRef.current = 0;
    setDragging(false);
    const paths = extractFolderPathsFromDataTransfer(e.dataTransfer);
    void handleQueueFolders(paths);
  }, [handleQueueFolders]);

  const handleQueueFolder = useCallback(async (parent: boolean) => {
    const path = folderPath.trim();
    if (!path) return;
    setFolderBusy(true);
    try {
      const res = parent ? await queueParentFolder(path) : await queueFolder(path);
      setState(res);
      if (res.warnings?.length) {
        showToast(res.warnings.join("\n"), "warn");
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "폴더 큐 실패", "error");
    } finally {
      setFolderBusy(false);
    }
  }, [folderPath, showToast]);

  const handleRemove = useCallback(async (id: string) => {
    await removeFromQueue(id);
    setState(s => ({ ...s, items: s.items.filter(i => i.id !== id) }));
  }, []);

  const handleCancel = useCallback(async (id: string) => {
    try {
      await cancelHarvestItem(id);
      showToast("취소 요청됨", "info");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "취소 실패", "error");
    }
  }, [showToast]);

  const handleClearFinished = useCallback(async () => {
    await clearFinished();
    setState(s => ({ ...s, items: s.items.filter(i => i.status !== "done" && i.status !== "error") }));
  }, []);

  const handleClear = useCallback(async () => {
    await clearQueue();
    setState(s => ({ ...s, items: [] }));
  }, []);

  const handleGrokToggle = useCallback(async (enabled: boolean) => {
    setGrokEnabled(enabled);
    try {
      const res = await patchHarvestSettings(enabled);
      setState(res);
    } catch (e) {
      setGrokEnabled(!enabled);
      showToast(e instanceof Error ? e.message : "설정 저장 실패", "error");
    }
  }, [showToast]);

  const handleFavorites = useCallback(async (mode: "all" | "missing") => {
    try {
      await harvestFavorites(mode);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "좋아요 수집 실패", "error");
    }
  }, [showToast]);

  const pendingCount = state.items.filter(i => i.status === "pending" && !i.staged).length;
  const stagedCount = state.items.filter(i => i.staged && i.status === "pending").length;
  const doneCount = state.items.filter(i => i.status === "done").length;
  const errorCount = state.items.filter(i => i.status === "error").length;
  const canStart = pendingCount > 0 || stagedCount > 0;

  return (
    <div
      className="relative"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {dragging && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 pointer-events-none">
          <div className="max-w-lg w-full mx-6 px-8 py-10 rounded-2xl border-2 border-accent/60 bg-bg-panel/95 text-center shadow-xl">
            <Upload className="w-10 h-10 mx-auto mb-3 text-accent-light" />
            <p className="text-lg font-semibold text-white">폴더를 여기로 드롭하면 큐에 추가됩니다</p>
            <p className="text-sm text-muted-foreground mt-2">추가 후 「수집 시작」을 눌러 실행하세요</p>
          </div>
        </div>
      )}

    <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">

      {/* ── 입력 패널 ── */}
      <div className="space-y-4">
        <GlassCard className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            품번 입력
          </h3>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && e.ctrlKey) handleAdd(); }}
            placeholder={"STARS-001\nIPX-002\n\nCtrl+Enter로 추가"}
            rows={6}
            className={cn(
              "w-full px-3 py-2.5 text-base rounded-xl resize-none",
              "bg-bg-base border border-white/[0.08] text-white placeholder:text-muted-foreground",
              "focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30",
            )}
          />
          <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={autoStart}
              onChange={e => setAutoStart(e.target.checked)}
              className="rounded border-white/20"
            />
            추가 시 즉시 수집 시작
          </label>
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

        <GlassCard className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            폴더 경로
          </h3>
          <div
            className={cn(
              "rounded-xl border-2 border-dashed px-4 py-5 text-center transition-colors",
              dragging
                ? "border-accent/50 bg-accent/10"
                : "border-white/[0.10] bg-bg-base/50",
            )}
          >
            <Upload className={cn(
              "w-7 h-7 mx-auto mb-2",
              dragging ? "text-accent-light" : "text-muted-foreground",
            )} />
            <p className="text-sm text-[#d0d0e8]">폴더를 드래그&드롭</p>
            <p className="text-sm text-muted-foreground mt-1">또는 아래에서 경로 입력 · 찾아보기</p>
          </div>
          <input
            type="text"
            value={folderPath}
            onChange={e => setFolderPath(e.target.value)}
            placeholder="D:\Media\JAV\STARS-001"
            className={cn(
              "w-full px-3 py-2.5 text-base rounded-xl",
              "bg-bg-base border border-white/[0.08] text-white placeholder:text-muted-foreground",
              "focus:outline-none focus:border-accent/50",
            )}
          />
          <div className="flex gap-2 flex-wrap">
            <ActionButton
              variant="secondary"
              size="sm"
              className="flex-1 min-w-[7rem]"
              loading={folderBusy}
              icon={<FolderOpen className="w-3.5 h-3.5" />}
              onClick={() => void handleBrowseFolders()}
            >
              찾아보기
            </ActionButton>
            <ActionButton
              variant="ghost"
              size="sm"
              className="flex-1 min-w-[7rem]"
              loading={folderBusy}
              icon={<FolderOpen className="w-3.5 h-3.5" />}
              onClick={() => handleQueueFolder(false)}
              disabled={!folderPath.trim()}
            >
              폴더 큐
            </ActionButton>
            <ActionButton
              variant="ghost"
              size="sm"
              className="flex-1 min-w-[7rem]"
              loading={folderBusy}
              icon={<FolderTree className="w-3.5 h-3.5" />}
              onClick={() => handleQueueFolder(true)}
              disabled={!folderPath.trim()}
            >
              하위 일괄
            </ActionButton>
          </div>
          <p className="text-sm text-muted-foreground">
            찾아보기: Ctrl+클릭으로 여러 폴더 선택 · 스테이징 후 「수집 시작」
          </p>
        </GlassCard>

        <GlassCard className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              Grok 스토리
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={grokEnabled}
              onClick={() => handleGrokToggle(!grokEnabled)}
              className={cn(
                "relative w-10 h-5 rounded-full transition-colors",
                grokEnabled ? "bg-indigo-500" : "bg-white/10",
              )}
            >
              <span className={cn(
                "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform",
                grokEnabled ? "left-5" : "left-0.5",
              )} />
            </button>
          </div>
          <p className="text-sm text-muted-foreground">
            HarvestWorker와 동일 — coordinator inline Grok는 비활성, 후처리·캐시는 별도
          </p>
        </GlassCard>

        <GlassCard className="space-y-2">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            ♥ 좋아요만
          </h3>
          <div className="flex gap-2">
            <ActionButton
              variant="ghost"
              size="sm"
              className="flex-1"
              loading={favRunning}
              icon={<Heart className="w-3.5 h-3.5" />}
              onClick={() => handleFavorites("missing")}
              disabled={favRunning || state.running}
            >
              미수집
            </ActionButton>
            <ActionButton
              variant="ghost"
              size="sm"
              className="flex-1"
              loading={favRunning}
              icon={<Heart className="w-3.5 h-3.5" />}
              onClick={() => handleFavorites("all")}
              disabled={favRunning || state.running}
            >
              전체
            </ActionButton>
          </div>
        </GlassCard>
      </div>

      {/* ── 큐 + 로그 ── */}
      <div className="xl:col-span-2 space-y-4">

        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-base flex-wrap">
            <span className="text-muted-foreground">대기</span>
            <span className="text-white font-bold tabular-nums">{pendingCount}</span>
            {stagedCount > 0 && (
              <>
                <span className="text-muted-foreground">/ 스테이징</span>
                <span className="text-amber-400 font-bold tabular-nums">{stagedCount}</span>
              </>
            )}
            <span className="text-muted-foreground">/ 완료</span>
            <span className="text-emerald-400 font-bold tabular-nums">{doneCount}</span>
            {errorCount > 0 && (
              <>
                <span className="text-muted-foreground">/ 오류</span>
                <span className="text-rose-400 font-bold tabular-nums">{errorCount}</span>
              </>
            )}
          </div>

          <div className="flex items-center gap-2 ml-auto flex-wrap">
            {(doneCount > 0 || errorCount > 0) && (
              <ActionButton variant="ghost" size="sm" onClick={handleClearFinished} icon={<Trash2 className="w-3.5 h-3.5" />}>
                완료 제거
              </ActionButton>
            )}
            {!state.running && state.items.length > 0 && (
              <ActionButton variant="ghost" size="sm" onClick={handleClear} disabled={state.running}>
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
              disabled={state.running || !canStart}
            >
              {state.running ? "수집 중..." : stagedCount > 0 ? "스테이징 시작" : "수집 시작"}
            </ActionButton>
          </div>
        </div>

        {state.items.length === 0 ? (
          <GlassCard variant="subtle" className="flex items-center justify-center h-48 text-muted-foreground text-base">
            큐가 비어 있습니다
          </GlassCard>
        ) : (
          <div className="space-y-2 max-h-[420px] overflow-y-auto no-scrollbar">
            {state.items.map(item => (
              <QueueRow
                key={item.id}
                item={item}
                onRemove={handleRemove}
                onCancel={handleCancel}
              />
            ))}
          </div>
        )}

        <GlassCard className="space-y-2">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            로그
          </h3>
          <LogPanel entries={logs} maxHeight="200px" />
        </GlassCard>
      </div>
    </div>
    </div>
  );
}

function QueueRow({
  item,
  onRemove,
  onCancel,
}: {
  item: HarvestItem;
  onRemove: (id: string) => void;
  onCancel: (id: string) => void;
}) {
  const isRunning = item.status === "running";
  const isDone = item.status === "done";
  const isError = item.status === "error";
  const isStaged = item.staged && item.status === "pending";

  return (
    <GlassCard
      noPadding
      className={cn(
        "px-4 py-3 flex items-center gap-3 transition-all duration-200",
        isRunning && "border-indigo-500/30 bg-indigo-500/5",
        isStaged && "border-amber-500/25 bg-amber-500/5",
        isDone && "border-emerald-500/20 opacity-70",
        isError && "border-rose-500/20 bg-rose-500/5",
      )}
    >
      <StatusIcon status={item.status} staged={isStaged} />

      <div className="w-32 shrink-0">
        <span className="font-mono text-base text-indigo-300 block truncate">{item.target}</span>
        {isStaged && (
          <span className="text-sm text-amber-400 font-semibold">큐 대기</span>
        )}
        {item.force_rebuild && (
          <span className="text-sm text-violet-400 flex items-center gap-0.5">
            <RotateCcw className="w-3 h-3" /> 재크롤
          </span>
        )}
      </div>

      <div className="flex-1 min-w-0">
        {isRunning ? (
          <div className="space-y-1">
            <p className="text-sm text-[#c8c8e0] truncate">{item.message || "처리 중..."}</p>
            <div className="h-1 rounded-full bg-white/[0.06] overflow-hidden">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all duration-500"
                style={{ width: `${item.progress}%` }}
              />
            </div>
          </div>
        ) : (
          <p className={cn(
            "text-sm truncate",
            isDone && "text-emerald-400",
            isError && "text-rose-400",
            isStaged && "text-amber-300",
            !isDone && !isError && !isStaged && "text-muted-foreground",
          )}>
            {queueItemMessage(item, isStaged)}
          </p>
        )}
      </div>

      {isRunning && (
        <>
          <span className="text-sm tabular-nums text-indigo-400 shrink-0">{item.progress}%</span>
          <button
            onClick={() => onCancel(item.id)}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-rose-400 hover:bg-rose-500/10 transition-colors shrink-0"
            title="취소"
          >
            <Ban className="w-3.5 h-3.5" />
          </button>
        </>
      )}

      {!isRunning && (
        <button
          onClick={() => onRemove(item.id)}
          className="w-6 h-6 rounded-lg flex items-center justify-center text-muted-foreground hover:text-white hover:bg-white/[0.06] transition-colors shrink-0"
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </GlassCard>
  );
}

function StatusIcon({ status, staged }: { status: HarvestItem["status"]; staged?: boolean }) {
  if (status === "running") return <Loader2 className="w-4 h-4 text-indigo-400 animate-spin shrink-0" />;
  if (status === "done") return <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />;
  if (status === "error") return <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />;
  if (staged) return <Clock className="w-4 h-4 text-amber-400 shrink-0" />;
  return <Clock className="w-4 h-4 text-muted-foreground shrink-0" />;
}

function statusLabel(status: HarvestItem["status"], staged?: boolean): string {
  if (staged) return "큐 대기";
  if (status === "pending") return "대기 중";
  if (status === "done") return "완료";
  if (status === "error") return "오류";
  return "";
}

/** 완료·오류 항목에 크롤 중간 메시지가 남지 않도록 표시 문구 정규화 */
function queueItemMessage(item: HarvestItem, staged?: boolean): string {
  const msg = (item.message || "").trim();
  const inProgress = /수집 중|번역 중|준비|매핑|저장 중|처리 중/i.test(msg);
  if (item.status === "done") {
    return msg && !inProgress ? msg : "완료";
  }
  if (item.status === "error") {
    return msg || "오류";
  }
  return msg || statusLabel(item.status, staged);
}
