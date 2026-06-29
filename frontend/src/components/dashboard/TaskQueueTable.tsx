import { cn } from "@/lib/utils";
import { GlowCard } from "@/components/ui/GlowCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { HarvestItem } from "@/api/harvest";
import type { PendingItem, PreviewQueueItem, PreviewQueueStatus } from "@/api/dashboard";

export interface TaskRow {
  id: string;
  name: string;
  kind: "harvest" | "preview" | "pending";
  status: "pending" | "running" | "done" | "error" | "active" | "analyzing";
  progress: number;
  eta: string;
  detail?: string;
  activity?: PreviewQueueItem["activity"];
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
    eta =
      item.activity === "stalled"
        ? "정체?"
        : item.elapsed_sec > 0
          ? `${Math.floor(item.elapsed_sec / 60)}분 경과`
          : "인코딩";
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
    detail: item.message || undefined,
    activity: item.activity,
  };
}

const KIND_LABEL: Record<TaskRow["kind"], string> = {
  harvest: "Harvest",
  preview: "Preview",
  pending: "Meta",
};

interface TaskQueueTableProps {
  harvestItems: HarvestItem[];
  pendingItems: PendingItem[];
  previewQueue: PreviewQueueStatus | null;
  className?: string;
}

export function TaskQueueTable({
  harvestItems,
  pendingItems,
  previewQueue,
  className,
}: TaskQueueTableProps) {
  const activeHarvest = harvestItems.filter(i => i.status === "running" || i.status === "pending");
  const previewRows = (previewQueue?.items ?? []).map(mapPreviewItem);

  const activePreview = previewRows.filter(
    r => r.status === "running" || r.status === "pending",
  );
  const recentPreviewDone = previewRows.filter(r => r.status === "done" || r.status === "error").slice(0, 5);

  const rows: TaskRow[] = [
    ...activePreview,
    ...activeHarvest.map(mapHarvestItem),
    ...recentPreviewDone,
    ...pendingItems
      .filter(p => !activeHarvest.some(h => (h.product_code || h.target) === p.product_code))
      .slice(0, 6)
      .map(mapPendingItem),
  ].slice(0, 16);

  const previewPending = previewQueue?.pending_count ?? 0;
  const previewRunning = previewQueue?.running_count ?? 0;
  const previewDone = previewQueue?.completed_total ?? 0;
  const previewState = previewQueue?.processing_state ?? "idle";
  const stateUi = PREVIEW_STATE_LABEL[previewState];
  const idleLabel = previewQueue
    ? formatIdleSec(previewQueue.seconds_since_activity)
    : "";

  return (
    <GlowCard accent="blue" className={cn("overflow-hidden !p-6", className)}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <h2 className="text-xl font-semibold text-white">Task Queue</h2>
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
          <span>{rows.length} 표시</span>
          {previewQueue && (
            <>
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold",
                  stateUi.className,
                )}
              >
                {stateUi.pulse && (
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                )}
                Preview {stateUi.label}
              </span>
              <span className="text-violet-300/90">
                실행 {previewRunning} / 대기 {previewPending.toLocaleString()} / 완료{" "}
                {previewDone.toLocaleString()}
              </span>
              <span className="text-slate-500">활동 {idleLabel}</span>
            </>
          )}
        </div>
      </div>
      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-left text-base">
          <thead>
            <tr className="text-slate-400 border-b border-white/[0.06] text-lg">
              <th className="pb-3 pl-1 font-semibold w-24">Type</th>
              <th className="pb-3 font-semibold">Task</th>
              <th className="pb-3 font-semibold">Status</th>
              <th className="pb-3 font-semibold min-w-[160px]">Progress</th>
              <th className="pb-3 pr-1 font-semibold text-right">ETA</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-10 text-center text-lg text-slate-500">
                  대기 중인 작업이 없습니다
                </td>
              </tr>
            ) : (
              rows.map(row => (
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
                      <div className="text-xs text-slate-500 font-sans mt-0.5 truncate max-w-[280px]">
                        {row.detail}
                      </div>
                    )}
                  </td>
                  <td className="py-3">
                    <div className="flex flex-col gap-1">
                      <StatusBadge
                        status={
                          row.status === "analyzing"
                            ? "pending"
                            : row.status === "active"
                              ? "running"
                              : row.status
                        }
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
                            row.kind === "preview" ? "bg-violet-500" : "bg-blue-500",
                          )}
                          style={{
                            width: `${row.progress}%`,
                            boxShadow:
                              row.kind === "preview"
                                ? "0 0 8px rgba(139,92,246,0.5)"
                                : "0 0 8px rgba(59,130,246,0.5)",
                          }}
                        />
                      </div>
                      <span className="text-base text-slate-400 w-10 tabular-nums">
                        {row.progress}%
                      </span>
                    </div>
                  </td>
                  <td className="py-3 pr-1 text-right text-base text-slate-400">{row.eta}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </GlowCard>
  );
}
