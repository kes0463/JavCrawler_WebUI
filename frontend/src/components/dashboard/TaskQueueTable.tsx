import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { GlowCard } from "@/components/ui/GlowCard";
import { StatusBadge, type StatusType } from "@/components/ui/StatusBadge";
import {
  clearEmbeddingFinished,
  clearPreviewFinished,
  fetchEmbeddingQueue,
  fetchPreviewQueue,
  formatPreviewSegmentProgress,
  pauseAllPreview,
  pausePreviewJob,
  removeEmbeddingJob,
  removePreviewJob,
  resumeAllPreview,
  resumePreviewJob,
  type EmbeddingQueueItem,
  type EmbeddingQueueStatus,
  type PendingItem,
  type PreviewQueueItem,
  type PreviewQueueStatus,
} from "@/api/dashboard";
import { cancelHarvestItem, clearFinished, removeFromQueue, type HarvestItem } from "@/api/harvest";

export interface TaskRow {
  id: string;
  name: string;
  kind: "harvest" | "preview" | "pending" | "embedding";
  status: "pending" | "running" | "done" | "error" | "active" | "analyzing" | "paused";
  progress: number;
  eta: string;
  detail?: string;
  activity?: PreviewQueueItem["activity"];
  previewJobId?: string;
  embeddingJobId?: string;
  harvestItemId?: string;
  rawPreviewStatus?: string;
}

function mapHarvestItem(item: HarvestItem): TaskRow {
  const staged = item.staged && item.status === "pending";
  return {
    id: item.id,
    name: item.product_code || item.target,
    kind: "harvest",
    status: staged ? "pending" : item.status,
    progress: item.progress,
    eta: item.status === "running" ? "진행 중" : staged ? "스테이징" : item.status === "pending" ? "대기" : "—",
    detail: item.message || undefined,
    harvestItemId: item.id,
  };
}

function mapPendingItem(item: PendingItem, idx: number): TaskRow {
  return {
    id: `pending-${item.product_code}-${idx}`,
    name: item.product_code,
    kind: "pending",
    status: "pending",
    progress: 0,
    eta: "대기",
  };
}

function formatIdleSec(sec: number): string {
  if (sec < 60) return `${sec}초 전`;
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m}분 전`;
  return `${Math.floor(m / 60)}시간 ${m % 60}분 전`;
}

const PREVIEW_STATE_LABEL: Record<
  PreviewQueueStatus["processing_state"],
  { label: string; className: string; pulse?: boolean }
> = {
  active: { label: "인코딩 진행 중", className: "bg-emerald-500/20 text-emerald-300", pulse: true },
  idle: { label: "대기 없음", className: "bg-slate-500/20 text-slate-400" },
  backlogged: {
    label: "큐 정체 (실행 0)",
    className: "bg-amber-500/20 text-amber-300",
  },
  stalled: { label: "작업 응답 없음", className: "bg-red-500/20 text-red-300" },
};

function mapPreviewItem(item: PreviewQueueItem): TaskRow {
  const segmentLabel = formatPreviewSegmentProgress(item);
  const status =
    item.status === "paused"
      ? "paused"
      : item.status === "queued"
        ? "pending"
        : item.status === "running"
          ? "running"
          : item.status === "done"
            ? "done"
            : item.status === "error"
              ? "error"
              : "pending";
  let eta = "—";
  if (status === "paused") eta = "일시정지";
  else if (status === "running") {
    if (segmentLabel) {
      eta = segmentLabel;
    } else if (item.message?.includes("구간")) {
      eta = item.message;
    } else {
      eta =
        item.activity === "stalled"
          ? "정체?"
          : item.elapsed_sec > 0
            ? `${Math.floor(item.elapsed_sec / 60)}분 경과`
            : "인코딩";
    }
  } else if (status === "pending") eta = "대기";
  else if (status === "done") eta = "완료";
  else if (status === "error") eta = "실패";

  return {
    id: `preview-${item.id}`,
    name: item.product_code,
    kind: "preview",
    status,
    progress: item.progress,
    eta,
    detail: segmentLabel
      ?? (status === "running" && item.message ? item.message : undefined),
    activity: item.activity,
    previewJobId: item.id,
    rawPreviewStatus: item.status,
  };
}

function mapEmbeddingItem(item: EmbeddingQueueItem): TaskRow {
  const status =
    item.status === "queued"
      ? "pending"
      : item.status === "running"
        ? "running"
        : item.status === "done"
          ? "done"
          : item.status === "error"
            ? "error"
            : "pending";
  let eta = "—";
  if (status === "running") {
    eta = item.elapsed_sec > 0
      ? `${Math.floor(item.elapsed_sec / 60)}분 경과`
      : "생성 중";
  } else if (status === "pending") eta = "대기";
  else if (status === "done") eta = "완료";
  else if (status === "error") eta = "실패";

  return {
    id: `embedding-${item.id}`,
    name: item.product_code,
    kind: "embedding",
    status,
    progress: item.progress,
    eta,
    detail: item.message || item.model || undefined,
    embeddingJobId: item.id,
  };
}

const KIND_LABEL: Record<TaskRow["kind"], string> = {
  harvest: "Harvest",
  preview: "Preview",
  pending: "Meta",
  embedding: "Embedding",
};

function rowStatusBadge(row: TaskRow, rowPaused: boolean): StatusType {
  if (rowPaused || row.status === "paused") return "warning";
  if (row.status === "analyzing") return "pending";
  if (row.status === "active") return "running";
  if (row.status === "done" || row.status === "error" || row.status === "running" || row.status === "pending") {
    return row.status;
  }
  return "pending";
}

function formatActionError(e: unknown): string {
  const msg = e instanceof Error ? e.message : "작업 실패";
  if (msg.includes("Not Found")) {
    return "일시정지 API를 찾을 수 없습니다. start_web.bat으로 webapi를 재시작해 주세요.";
  }
  return msg;
}

interface TaskQueueTableProps {
  harvestItems: HarvestItem[];
  pendingItems: PendingItem[];
  previewQueue: PreviewQueueStatus | null;
  embeddingQueue?: EmbeddingQueueStatus | null;
  className?: string;
  onQueueChange?: () => void;
  onPreviewQueueUpdate?: (queue: PreviewQueueStatus) => void;
  onEmbeddingQueueUpdate?: (queue: EmbeddingQueueStatus) => void;
}

export function TaskQueueTable({
  harvestItems,
  pendingItems,
  previewQueue,
  embeddingQueue = null,
  className,
  onQueueChange,
  onPreviewQueueUpdate,
  onEmbeddingQueueUpdate,
}: TaskQueueTableProps) {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [userPaused, setUserPaused] = useState(false);
  const [rowPausedIds, setRowPausedIds] = useState<Set<string>>(() => new Set());
  const busyRef = useRef(false);

  useEffect(() => {
    setUserPaused(previewQueue?.user_paused ?? false);
    const paused = new Set<string>();
    for (const item of previewQueue?.items ?? []) {
      if (item.status === "paused") paused.add(item.id);
    }
    setRowPausedIds(paused);
  }, [previewQueue]);

  const syncPreviewQueue = useCallback(async () => {
    const preview = await fetchPreviewQueue(40);
    onPreviewQueueUpdate?.(preview);
    return preview;
  }, [onPreviewQueueUpdate]);

  const syncEmbeddingQueue = useCallback(async () => {
    const emb = await fetchEmbeddingQueue(40);
    onEmbeddingQueueUpdate?.(emb);
    return emb;
  }, [onEmbeddingQueueUpdate]);

  const runAction = useCallback(
    async (fn: () => Promise<unknown>) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      setActionError(null);
      try {
        await fn();
        await Promise.all([syncPreviewQueue(), syncEmbeddingQueue()]);
        onQueueChange?.();
      } catch (e) {
        setActionError(formatActionError(e));
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [onQueueChange, syncEmbeddingQueue, syncPreviewQueue],
  );

  const activeHarvest = harvestItems.filter(i => i.status === "running" || i.status === "pending");
  const previewRows = (previewQueue?.items ?? []).map(mapPreviewItem);
  const embeddingRows = (embeddingQueue?.items ?? []).map(mapEmbeddingItem);

  const activePreview = previewRows.filter(
    r => r.status === "running" || r.status === "pending" || r.status === "paused",
  );
  const recentPreviewDone = previewRows.filter(r => r.status === "done" || r.status === "error").slice(0, 5);
  const activeEmbedding = embeddingRows.filter(
    r => r.status === "running" || r.status === "pending",
  );
  const recentEmbeddingDone = embeddingRows
    .filter(r => r.status === "done" || r.status === "error")
    .slice(0, 5);

  const rows: TaskRow[] = [
    ...activeEmbedding,
    ...activePreview,
    ...activeHarvest.map(mapHarvestItem),
    ...recentEmbeddingDone,
    ...recentPreviewDone,
    ...pendingItems
      .filter(p => !activeHarvest.some(h => (h.product_code || h.target) === p.product_code))
      .slice(0, 6)
      .map(mapPendingItem),
  ].slice(0, 20);

  const previewPending = previewQueue?.pending_count ?? 0;
  const previewRunning = previewQueue?.running_count ?? 0;
  const previewDone = previewQueue?.completed_total ?? 0;
  const previewState = previewQueue?.processing_state ?? "idle";
  const stateUi = PREVIEW_STATE_LABEL[previewState];
  const idleLabel = previewQueue
    ? formatIdleSec(previewQueue.seconds_since_activity)
    : "";
  const harvestPaused = previewQueue?.harvest_paused ?? false;
  const embPending = embeddingQueue?.pending_count ?? 0;
  const embRunning = embeddingQueue?.running_count ?? 0;
  const embDone = embeddingQueue?.completed_total ?? 0;

  const handleClearFinished = () =>
    runAction(async () => {
      await Promise.all([clearPreviewFinished(), clearEmbeddingFinished(), clearFinished()]);
    });

  const handleTogglePauseAll = async () => {
    if (busyRef.current || harvestPaused) return;
    const nextPaused = !userPaused;
    setUserPaused(nextPaused);
    setActionError(null);
    busyRef.current = true;
    setBusy(true);
    try {
      if (nextPaused) {
        await pauseAllPreview();
      } else {
        await resumeAllPreview();
      }
      const preview = await syncPreviewQueue();
      setUserPaused(preview.user_paused ?? nextPaused);
      onQueueChange?.();
    } catch (e) {
      setUserPaused(!nextPaused);
      setActionError(formatActionError(e));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const isRowPaused = (row: TaskRow) =>
    row.status === "paused"
    || row.rawPreviewStatus === "paused"
    || (row.previewJobId ? rowPausedIds.has(row.previewJobId) : false);

  const toggleRowPause = async (row: TaskRow) => {
    if (!row.previewJobId || busyRef.current || harvestPaused) return;
    const jobId = row.previewJobId;
    const wasPaused = isRowPaused(row);
    const prevIds = rowPausedIds;
    const nextIds = new Set(rowPausedIds);
    if (wasPaused) nextIds.delete(jobId);
    else nextIds.add(jobId);
    setRowPausedIds(nextIds);
    setActionError(null);
    busyRef.current = true;
    setBusy(true);
    try {
      if (wasPaused) await resumePreviewJob(jobId);
      else await pausePreviewJob(jobId);
      await syncPreviewQueue();
      onQueueChange?.();
    } catch (e) {
      setRowPausedIds(prevIds);
      setActionError(formatActionError(e));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  return (
    <GlowCard accent="blue" className={cn("overflow-hidden !p-6", className)}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <h2 className="text-xl font-semibold text-white">Task Queue</h2>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={handleClearFinished}
            className="px-3 py-1.5 text-xs font-medium rounded-md bg-white/[0.06] text-slate-300 hover:bg-white/[0.1] disabled:opacity-50"
          >
            완료 목록 삭제
          </button>
          <button
            type="button"
            disabled={busy || harvestPaused}
            title={harvestPaused ? "크롤링 중에는 프리뷰가 자동 일시정지됩니다" : undefined}
            onClick={handleTogglePauseAll}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-violet-500/20 text-violet-200 hover:bg-violet-500/30 disabled:opacity-50"
          >
            {userPaused && !harvestPaused ? (
              <>
                <Play className="w-3.5 h-3.5" />
                모두 재개
              </>
            ) : (
              <>
                <Pause className="w-3.5 h-3.5" />
                모두 일시정지
              </>
            )}
          </button>
        </div>
      </div>
      {actionError && (
        <p className="mb-3 text-sm text-rose-400">{actionError}</p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400 mb-4">
        <span>{rows.length} 표시</span>
        {previewQueue && (
          <>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold",
                harvestPaused
                  ? "bg-amber-500/20 text-amber-300"
                  : userPaused
                    ? "bg-violet-500/20 text-violet-300"
                    : stateUi.className,
              )}
            >
              {harvestPaused ? (
                "크롤링 중 — Preview 일시정지"
              ) : userPaused ? (
                "Preview 일시정지"
              ) : (
                <>
                  {stateUi.pulse && (
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  )}
                  Preview {stateUi.label}
                </>
              )}
            </span>
            <span className="text-violet-300/90">
              실행 {previewRunning} / 대기 {previewPending.toLocaleString()} / 완료{" "}
              {previewDone.toLocaleString()}
            </span>
            <span className="text-slate-500">활동 {idleLabel}</span>
          </>
        )}
        {embeddingQueue && (
          <span className="text-emerald-300/90">
            Embedding 실행 {embRunning} / 대기 {embPending.toLocaleString()} / 완료{" "}
            {embDone.toLocaleString()}
          </span>
        )}
      </div>
      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-left text-base">
          <thead>
            <tr className="text-slate-400 border-b border-white/[0.06] text-lg">
              <th className="pb-3 pl-1 font-semibold w-24">Type</th>
              <th className="pb-3 font-semibold">Task</th>
              <th className="pb-3 font-semibold">Status</th>
              <th className="pb-3 font-semibold min-w-[160px]">Progress</th>
              <th className="pb-3 font-semibold text-right">ETA</th>
              <th className="pb-3 pr-1 font-semibold text-right w-24">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-10 text-center text-lg text-slate-500">
                  대기 중인 작업이 없습니다
                </td>
              </tr>
            ) : (
              rows.map(row => {
                const rowPaused = row.kind === "preview" && isRowPaused(row);
                return (
                <tr
                  key={row.id}
                  className="border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02]"
                >
                  <td className="py-3 pl-1">
                    <span
                      className={cn(
                        "text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded",
                        row.kind === "preview"
                          ? "bg-violet-500/20 text-violet-300"
                          : row.kind === "embedding"
                            ? "bg-emerald-500/20 text-emerald-300"
                            : row.kind === "harvest"
                              ? "bg-blue-500/20 text-blue-300"
                              : "bg-slate-500/20 text-slate-400",
                      )}
                    >
                      {KIND_LABEL[row.kind]}
                    </span>
                  </td>
                  <td className="py-3 font-mono text-lg text-indigo-300">
                    <div>{row.name}</div>
                    {row.detail && (
                      <div
                        className={cn(
                          "text-xs font-sans mt-0.5 truncate max-w-[360px]",
                          row.detail.includes("구간")
                            ? "text-violet-300/90 font-medium"
                            : "text-slate-500",
                        )}
                        title={row.detail}
                      >
                        {row.detail}
                      </div>
                    )}
                  </td>
                  <td className="py-3">
                    <div className="flex flex-col gap-1">
                      <StatusBadge
                        status={rowStatusBadge(row, rowPaused)}
                        label={rowPaused ? "일시정지" : undefined}
                        showDot
                        className="text-base px-2.5 py-1 w-fit"
                      />
                      {row.kind === "preview" && row.activity === "stalled" && (
                        <span className="text-xs text-amber-400">응답 없음</span>
                      )}
                      {row.kind === "preview" && row.activity === "active" && row.status === "running" && (
                        <span className="text-xs text-emerald-400/90">동작 중</span>
                      )}
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <div className="flex items-center gap-3">
                      <div className="flex-1 h-2 rounded-full bg-white/[0.06] overflow-hidden">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-300",
                            row.kind === "preview"
                              ? "bg-violet-500"
                              : row.kind === "embedding"
                                ? "bg-emerald-500"
                                : "bg-blue-500",
                          )}
                          style={{
                            width: `${row.progress}%`,
                            boxShadow:
                              row.kind === "preview"
                                ? "0 0 8px rgba(139,92,246,0.5)"
                                : row.kind === "embedding"
                                  ? "0 0 8px rgba(16,185,129,0.5)"
                                  : "0 0 8px rgba(59,130,246,0.5)",
                          }}
                        />
                      </div>
                      <span className="text-base text-slate-400 w-10 tabular-nums">
                        {row.progress}%
                      </span>
                    </div>
                  </td>
                  <td className="py-3 text-right text-base text-slate-400 max-w-[220px]">
                    <span className="block truncate" title={row.eta}>
                      {rowPaused ? "일시정지" : row.eta}
                    </span>
                  </td>
                  <td className="py-3 pr-1 text-right">
                    <div className="inline-flex items-center gap-1">
                      {row.kind === "preview" && row.previewJobId && (
                        <>
                          {(row.status === "pending" ||
                            row.status === "running" ||
                            row.status === "paused") && (
                            <button
                              type="button"
                              disabled={busy || harvestPaused}
                              title={isRowPaused(row) ? "재개" : "일시정지"}
                              onClick={() => toggleRowPause(row)}
                              className="p-1.5 rounded-md text-slate-400 hover:text-violet-300 hover:bg-white/[0.06] disabled:opacity-40"
                            >
                              {isRowPaused(row) ? (
                                <Play className="w-4 h-4" />
                              ) : (
                                <Pause className="w-4 h-4" />
                              )}
                            </button>
                          )}
                          <button
                            type="button"
                            disabled={busy}
                            title="삭제"
                            onClick={() =>
                              runAction(() => removePreviewJob(row.previewJobId!))
                            }
                            className="p-1.5 rounded-md text-slate-400 hover:text-rose-400 hover:bg-white/[0.06] disabled:opacity-40"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                      {row.kind === "embedding" && row.embeddingJobId && (
                        <button
                          type="button"
                          disabled={busy || row.status === "running"}
                          title="삭제"
                          onClick={() =>
                            runAction(() => removeEmbeddingJob(row.embeddingJobId!))
                          }
                          className="p-1.5 rounded-md text-slate-400 hover:text-rose-400 hover:bg-white/[0.06] disabled:opacity-40"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                      {row.kind === "harvest" && row.harvestItemId && (
                        <>
                          {row.status === "running" && (
                            <button
                              type="button"
                              disabled={busy}
                              title="취소"
                              onClick={() =>
                                runAction(() => cancelHarvestItem(row.harvestItemId!))
                              }
                              className="p-1.5 rounded-md text-slate-400 hover:text-amber-300 hover:bg-white/[0.06] disabled:opacity-40"
                            >
                              <Pause className="w-4 h-4" />
                            </button>
                          )}
                          {row.status !== "running" && (
                            <button
                              type="button"
                              disabled={busy}
                              title="삭제"
                              onClick={() =>
                                runAction(() => removeFromQueue(row.harvestItemId!))
                              }
                              className="p-1.5 rounded-md text-slate-400 hover:text-rose-400 hover:bg-white/[0.06] disabled:opacity-40"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
              })
            )}
          </tbody>
        </table>
      </div>
    </GlowCard>
  );
}
