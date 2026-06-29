import { useState } from "react";
import { Upload, Play, FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/components/ui/GlassCard";
import { ActionButton } from "@/components/ui/ActionButton";
import { QueueAccordionCard } from "@/components/queue/QueueAccordionCard";
import { QueueItemRow, type QueueItem } from "@/components/queue/QueueItemRow";
import { LogPanel, type LogEntry } from "@/components/log/LogPanel";
import { ProgressIndicator } from "@/components/ui/ProgressIndicator";

const MOCK_QUEUE: QueueItem[] = [
  { id: "1", label: "STARS-001.mp4", status: "running",  progress: 38, message: "프레임 분석 중..." },
  { id: "2", label: "IPX-789.mkv",   status: "running",  progress: 91, message: "모자이크 마스크 적용..." },
  { id: "3", label: "MIDE-456.mp4",  status: "pending",  message: "대기 중" },
  { id: "4", label: "SSIS-234.avi",  status: "pending",  message: "대기 중" },
  { id: "5", label: "MIFD-111.mp4",  status: "done",     message: "출력 저장 완료" },
];

const MOCK_LOGS: LogEntry[] = [
  { id: 1, text: "모자이크 제거 모델 로드: IOPaint v1.4",      level: "info",    ts: "14:30:00" },
  { id: 2, text: "STARS-001.mp4 분석 시작 (1920x1080, 29.97fps)", level: "info", ts: "14:30:05" },
  { id: 3, text: "IPX-789.mkv 마스크 적용: 91% 완료",           level: "info",    ts: "14:31:20" },
  { id: 4, text: "MIFD-111.mp4 처리 완료 → output/MIFD-111_clean.mp4", level: "success", ts: "14:28:00" },
  { id: 5, text: "GPU VRAM 사용: 7.2GB / 12GB",               level: "debug",   ts: "14:31:22" },
];

export default function MosaicImportView() {
  const [queue, setQueue] = useState<QueueItem[]>(MOCK_QUEUE);
  const [dragging, setDragging] = useState(false);

  const runningCount = queue.filter(i => i.status === "running").length;
  const doneCount    = queue.filter(i => i.status === "done").length;
  const totalActive  = queue.length;

  return (
    <div className="space-y-5 animate-fade-in">

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">모자이크 제거</h1>
          <p className="text-base text-muted-foreground mt-0.5">AI 기반 모자이크 처리 파이프라인</p>
        </div>
        {runningCount > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-rose-500/15 border border-rose-500/25">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-pulse" />
            <span className="text-sm text-rose-300">{runningCount}개 처리 중</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "GPU VRAM",  value: "7.2 / 12 GB", pct: 60, variant: "accent" as const },
          { label: "처리 완료", value: `${doneCount} / ${totalActive}`, pct: totalActive > 0 ? (doneCount / totalActive) * 100 : 0, variant: "success" as const },
          { label: "진행 중",   value: `${runningCount}개`, pct: runningCount > 0 ? 100 : 0, variant: "warning" as const },
        ].map(({ label, value, pct, variant }) => (
          <GlassCard key={label} className="space-y-2">
            <div className="flex justify-between text-base">
              <span className="text-muted-foreground">{label}</span>
              <span className="text-[#c8c8e0] font-medium">{value}</span>
            </div>
            <ProgressIndicator value={pct} size="sm" variant={variant} />
          </GlassCard>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        <div className="space-y-4">
          <GlassCard
            noPadding
            className={cn(
              "border-dashed border-2 transition-all duration-200",
              dragging
                ? "border-accent/60 bg-accent/10"
                : "border-white/[0.10] hover:border-white/[0.20]",
            )}
            onDragEnter={() => setDragging(true)}
            onDragLeave={() => setDragging(false)}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); setDragging(false); }}
          >
            <div className="flex flex-col items-center justify-center py-10 gap-3 cursor-pointer">
              <div className={cn(
                "w-12 h-12 rounded-2xl border flex items-center justify-center transition-colors",
                dragging ? "border-accent/50 bg-accent/15" : "border-white/[0.10] bg-bg-surface",
              )}>
                <Upload className={cn("w-6 h-6 transition-colors", dragging ? "text-accent-light" : "text-muted-foreground")} />
              </div>
              <div className="text-center">
                <p className="text-base text-[#d0d0e8]">파일을 여기에 드롭</p>
                <p className="text-sm text-muted-foreground mt-0.5">MP4, MKV, AVI 지원</p>
              </div>
              <ActionButton variant="secondary" size="sm" icon={<FolderOpen className="w-4 h-4" />}>
                파일 선택
              </ActionButton>
            </div>
          </GlassCard>

          <GlassCard className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              처리 설정
            </h3>
            <div className="space-y-2.5">
              {[
                { label: "모델", value: "IOPaint v1.4" },
                { label: "품질", value: "High (720p)" },
                { label: "병렬 작업", value: "2" },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between text-base">
                  <span className="text-muted-foreground">{label}</span>
                  <span className="text-[#c8c8e0] font-medium">{value}</span>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>

        <div className="lg:col-span-2 space-y-4">

          <QueueAccordionCard
            title="모자이크 제거 큐"
            icon="🧩"
            count={queue.length}
            status="running"
            actions={
              <>
                <ActionButton variant="ghost" size="sm">전체 삭제</ActionButton>
                <ActionButton variant="primary" size="sm" icon={<Play className="w-4 h-4" />}>
                  시작
                </ActionButton>
              </>
            }
          >
            {queue.map(item => (
              <QueueItemRow
                key={item.id}
                item={item}
                onRemove={id => setQueue(q => q.filter(i => i.id !== id))}
                disabled={item.status === "running"}
              />
            ))}
          </QueueAccordionCard>

          <GlassCard className="space-y-2">
            <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              처리 로그
            </h3>
            <LogPanel entries={MOCK_LOGS} maxHeight="200px" />
          </GlassCard>

        </div>
      </div>
    </div>
  );
}
