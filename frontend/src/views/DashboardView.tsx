import { useCallback, useEffect, useState } from "react";
import { BookOpen, Tag, Layers } from "lucide-react";
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

export default function DashboardView() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [system, setSystem] = useState<SystemMetrics | null>(null);
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [previewQueue, setPreviewQueue] = useState<PreviewQueueStatus | null>(null);
  const [harvestItems, setHarvestItems] = useState<HarvestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, sys, pend, preview, queue] = await Promise.all([
        fetchDashboardSummary(),
        fetchSystemMetrics(),
        fetchPendingItems(50),
        fetchPreviewQueue(40),
        fetchQueue(),
      ]);
      setSummary(s);
      setSystem(sys);
      setPending(pend);
      setPreviewQueue(preview);
      setHarvestItems(queue.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "API 연결 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    let id: ReturnType<typeof setInterval> | undefined;

    const startPolling = () => {
      if (id !== undefined) return;
      id = setInterval(() => {
        if (document.visibilityState === "visible") refresh();
      }, 12000);
    };
    const stopPolling = () => {
      if (id !== undefined) {
        clearInterval(id);
        id = undefined;
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        refresh();
        startPolling();
      } else {
        stopPolling();
      }
    };

    startPolling();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refresh]);

  useEffect(() => {
    const ws = createHarvestWS(event => {
      if (event.type === "state") {
        setHarvestItems(event.items);
      } else if (event.type === "queue_started") {
        fetchQueue().then(q => setHarvestItems(q.items));
      } else if (event.type === "queue_finished") {
        fetchQueue().then(q => setHarvestItems(q.items));
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

  if (loading && !summary) {
    return (
      <div className="w-full space-y-5 animate-fade-in">
        <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-4 w-full">
          {[0, 1, 2].map(i => (
            <GlowCard key={i}>
              <Skeleton className="h-24 w-full" />
            </GlowCard>
          ))}
        </div>
      </div>
    );
  }

  const lib = summary?.library;
  const metaRate = summary?.metadata_match_rate ?? 0;
  const mosaicCount = summary?.mosaic_queue_count ?? 0;

  return (
    <div className="w-full space-y-5 animate-fade-in">
      {error && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-lg text-amber-200">
          {error} — webapi가 실행 중인지 확인하세요 (port 8765)
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-4 w-full items-stretch">
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
          label="Mosaic Queue"
          value={`${mosaicCount} Items`}
          icon={Layers}
          accent="pink"
          sparkline={[4, 8, 6, 12, mosaicCount || 9, 7, mosaicCount || 11]}
        />
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
      />
    </div>
  );
}
