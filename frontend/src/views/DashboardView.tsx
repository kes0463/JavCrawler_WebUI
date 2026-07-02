import { useState, useEffect, useRef, useCallback } from "react";
import { BookOpen, Tag, Clock } from "lucide-react";
import {
  fetchDashboardSummary,
  fetchPendingItems,
  fetchPreviewQueue,
  fetchSystemMetrics,
  type DashboardSummary,
  type PendingItem,
  type PreviewQueueStatus,
  type SystemMetrics,
} from "@/api/dashboard";
import { fetchQueue, createHarvestWS, type HarvestItem } from "@/api/harvest";
import { fetchApiStatus } from "@/api/client";
import { ArcGauge } from "@/components/dashboard/ArcGauge";
import { QuickActionGrid } from "@/components/dashboard/QuickActionGrid";
import { RingProgress } from "@/components/dashboard/RingProgress";
import { StatCard } from "@/components/dashboard/StatCard";
import { TaskQueueTable } from "@/components/dashboard/TaskQueueTable";
import { GlowCard } from "@/components/ui/GlowCard";
import { Skeleton } from "@/components/ui/Skeleton";

function formatNumber(n: number) {
  return n.toLocaleString("en-US");
}

function formatLoadError(reason: unknown): string {
  if (reason instanceof Error) return reason.message;
  return "API 연결 실패";
}

export default function DashboardView() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [system, setSystem] = useState<SystemMetrics | null>(null);
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [previewQueue, setPreviewQueue] = useState<PreviewQueueStatus | null>(null);
  const [harvestItems, setHarvestItems] = useState<HarvestItem[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setSummaryLoading(true);

    const results = await Promise.allSettled([
      fetchDashboardSummary(),
      fetchSystemMetrics(),
      fetchPendingItems(50),
      fetchPreviewQueue(40),
      fetchQueue(),
    ]);

    if (results[0].status === "fulfilled") {
      setSummary(results[0].value);
      setError(null);
    } else {
      setError(formatLoadError(results[0].reason));
    }

    if (results[1].status === "fulfilled") setSystem(results[1].value);
    if (results[2].status === "fulfilled") setPending(results[2].value);
    if (results[3].status === "fulfilled") setPreviewQueue(results[3].value);
    if (results[4].status === "fulfilled") setHarvestItems(results[4].value.items);

    setSummaryLoading(false);
  }, []);

  useEffect(() => {
    let cancelled = false;

    fetchApiStatus()
      .then(() => {
        if (!cancelled) void refresh();
      })
      .catch(e => {
        if (cancelled) return;
        setSummaryLoading(false);
        setError(formatLoadError(e));
      });

    let id: ReturnType<typeof setInterval> | undefined;
    let previewId: ReturnType<typeof setInterval> | undefined;

    const refreshPreview = () => {
      if (document.visibilityState !== "visible") return;
      fetchPreviewQueue(40)
        .then(setPreviewQueue)
        .catch(() => {});
    };

    const startPolling = () => {
      if (id !== undefined) return;
      id = setInterval(() => {
        if (document.visibilityState === "visible") void refresh();
      }, 12000);
      previewId = setInterval(refreshPreview, 4000);
    };
    const stopPolling = () => {
      if (id !== undefined) {
        clearInterval(id);
        id = undefined;
      }
      if (previewId !== undefined) {
        clearInterval(previewId);
        previewId = undefined;
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void refresh();
        refreshPreview();
        startPolling();
      } else {
        stopPolling();
      }
    };

    startPolling();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      stopPolling();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refresh]);

  useEffect(() => {
    const ws = createHarvestWS(event => {
      if (event.type === "state") {
        setHarvestItems(event.items);
      } else if (event.type === "queue_started" || event.type === "queue_finished") {
        fetchQueue().then(q => setHarvestItems(q.items));
        fetchPreviewQueue(40).then(setPreviewQueue);
      } else if (event.type === "item_started") {
        setHarvestItems(prev =>
          prev.map(i => (i.id === event.id ? { ...i, status: "running", progress: 0 } : i)),
        );
      } else if (event.type === "item_cancelled") {
        setHarvestItems(prev => prev.filter(i => i.id !== event.id));
      } else if (event.type === "progress") {
        setHarvestItems(prev =>
          prev.map(i =>
            i.id === event.id
              ? { ...i, progress: event.progress, message: event.message, status: "running" }
              : i,
          ),
        );
      } else if (event.type === "item_done") {
        setHarvestItems(prev =>
          prev.map(i => i.id === event.id ? {
            ...i,
            status: "done",
            progress: event.progress ?? 100,
            message: event.message || "완료",
          } : i),
        );
      } else if (event.type === "item_error") {
        setHarvestItems(prev =>
          prev.map(i =>
            i.id === event.id ? { ...i, status: "error", message: event.message } : i,
          ),
        );
      }
    });
    return () => ws.close();
  }, []);

  const lib = summary?.library;
  const metaRate = summary?.metadata_match_rate ?? 0;
  const pendingCount = summary?.pending_count ?? 0;

  return (
    <div className="w-full space-y-5 animate-fade-in">
      {error && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-lg text-amber-200">
          {error} — <code className="text-amber-100/90">start_web.bat</code>을 닫았다가 다시 실행해 webapi(포트 8765)를 재시작하세요.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full items-stretch">
        {summaryLoading && !summary ? (
          [0, 1].map(i => (
            <GlowCard key={i}>
              <Skeleton className="h-24 w-full" />
            </GlowCard>
          ))
        ) : (
          <>
            <StatCard
              label="Total Library Items"
              value={lib ? `${formatNumber(lib.total)} files` : "—"}
              delta={lib ? `${lib.with_folder} linked` : undefined}
              icon={BookOpen}
              accent="blue"
            />
            <StatCard
              label="Metadata Match Rate"
              value=""
              icon={Tag}
              accent="green"
            >
              <RingProgress
                value={metaRate}
                label="Matched"
                detail={
                  lib
                    ? `${formatNumber(lib.with_metadata)} / ${formatNumber(lib.total)}`
                    : undefined
                }
              />
            </StatCard>
            <StatCard
              label="Pending Analysis"
              value={`${formatNumber(pendingCount)} items`}
              icon={Clock}
              accent="orange"
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 w-full items-stretch">
        <GlowCard accent="blue" className="lg:col-span-8 min-h-[240px] !p-6">
          <p className="text-lg font-semibold text-slate-300 mb-5">CPU &amp; GPU Usage</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 py-2">
            <ArcGauge
              label="CPU"
              sublabel={system?.cpu_model}
              value={system?.cpu_percent ?? 0}
              accent="blue"
            />
            <ArcGauge
              label="GPU"
              sublabel={system?.gpu_name}
              value={system?.gpu_usage_percent ?? 0}
              accent="orange"
            />
          </div>
          {system && (
            <p className="text-base text-slate-400 text-center mt-3">
              RAM {system.mem_used_gb} / {system.mem_total_gb} GB ({system.mem_percent}%)
            </p>
          )}
        </GlowCard>
        <div className="lg:col-span-4 min-h-[240px]">
          <QuickActionGrid />
        </div>
      </div>

      <TaskQueueTable
        harvestItems={harvestItems}
        pendingItems={pending}
        previewQueue={previewQueue}
        className="w-full"
        onQueueChange={refresh}
        onPreviewQueueUpdate={setPreviewQueue}
      />
    </div>
  );
}
