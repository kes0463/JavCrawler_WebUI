import { useState } from "react";
import { Plus, Play, FileAudio } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { ActionButton } from "@/components/ui/ActionButton";
import { QueueAccordionCard } from "@/components/queue/QueueAccordionCard";
import { QueueItemRow, type QueueItem } from "@/components/queue/QueueItemRow";
import { LogPanel, type LogEntry } from "@/components/log/LogPanel";
import { PipelineStage, type Stage } from "@/components/library/PipelineStage";

const MOCK_STT_QUEUE: QueueItem[] = [
  { id: "1", label: "STARS-001.mp4", status: "running",  progress: 62, message: "음성 추출 중..." },
  { id: "2", label: "IPX-789.mkv",   status: "pending",  message: "대기 중" },
  { id: "3", label: "MIDE-456.mp4",  status: "done",     message: "Whisper 전사 완료" },
  { id: "4", label: "SSIS-234.avi",  status: "error",    message: "오디오 트랙 없음" },
];

const MOCK_SUB_QUEUE: QueueItem[] = [
  { id: "a", label: "STARS-001",     status: "running",  progress: 45, message: "번역 중 (KO→JA)..." },
  { id: "b", label: "MIDE-456",      status: "done",     message: "SRT 저장 완료" },
];

const PIPELINE_STAGES: Stage[] = [
  { id: "extract", label: "오디오 추출", status: "done" },
  { id: "stt",     label: "STT (Whisper)", status: "running" },
  { id: "trans",   label: "번역", status: "idle" },
  { id: "srt",     label: "SRT 저장", status: "idle" },
];

const MOCK_LOGS: LogEntry[] = [
  { id: 1, text: "Whisper 모델 로드: large-v3",          level: "info",    ts: "14:31:00" },
  { id: 2, text: "STARS-001.mp4 오디오 추출 완료",       level: "success", ts: "14:31:12" },
  { id: 3, text: "STARS-001 STT 진행: 62%",             level: "info",    ts: "14:32:45" },
  { id: 4, text: "MIDE-456 오디오 트랙 없음 — 건너뜀",  level: "error",   ts: "14:28:10" },
  { id: 5, text: "MIDE-456 SRT 저장: ./subs/MIDE-456.srt", level: "success", ts: "14:29:00" },
];

export default function ProcessingView() {
  const [input, setInput] = useState("");
  const [sttQueue, setSttQueue] = useState<QueueItem[]>(MOCK_STT_QUEUE);
  const [subQueue, setSubQueue] = useState<QueueItem[]>(MOCK_SUB_QUEUE);

  const runningCount = sttQueue.filter(i => i.status === "running").length
    + subQueue.filter(i => i.status === "running").length;

  return (
    <div className="space-y-5 animate-fade-in">

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">전사 · 자막</h1>
          <p className="text-base text-muted-foreground mt-0.5">STT 전사 및 자막 번역 파이프라인</p>
        </div>
        {runningCount > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/15 border border-indigo-500/25">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
            <span className="text-sm text-indigo-300">{runningCount}개 처리 중</span>
          </div>
        )}
      </div>

      <GlassCard className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          처리 파이프라인
        </h2>
        <PipelineStage stages={PIPELINE_STAGES} orientation="horizontal" />
      </GlassCard>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        <div className="space-y-4">
          <GlassCard className="space-y-3">
            <div className="flex items-center gap-2">
              <FileAudio className="w-5 h-5 text-muted-foreground" />
              <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
                파일 추가
              </h3>
            </div>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder={"파일 경로 또는 품번 입력\n\nD:\\media\\STARS-001.mp4\nIPX-789\n\nCtrl+Enter로 추가"}
              rows={7}
              className="w-full px-3 py-2.5 text-base rounded-xl resize-none bg-bg-base border border-white/[0.08] text-white placeholder:text-muted-foreground focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-all duration-150"
            />
            <div className="grid grid-cols-2 gap-2">
              <ActionButton variant="secondary" className="w-full">
                STT만
              </ActionButton>
              <ActionButton
                variant="primary"
                className="w-full"
                icon={<Plus className="w-4 h-4" />}
                disabled={!input.trim()}
              >
                추가
              </ActionButton>
            </div>
          </GlassCard>

          <GlassCard variant="subtle" className="text-base text-muted-foreground space-y-1.5">
            <p className="text-[#c8c8e0] font-medium">처리 순서</p>
            <ol className="space-y-1 list-decimal list-inside">
              <li>파일 경로 또는 품번 입력</li>
              <li>STT 전사 (Whisper large-v3)</li>
              <li>번역 (한국어 → 일본어)</li>
              <li>SRT 자막 파일 저장</li>
            </ol>
          </GlassCard>
        </div>

        <div className="lg:col-span-2 space-y-4">

          <QueueAccordionCard
            title="STT 전사 큐"
            icon="🎤"
            count={sttQueue.length}
            status={sttQueue.some(i => i.status === "running") ? "running" : "pending"}
            actions={
              <ActionButton
                variant="primary"
                size="sm"
                icon={<Play className="w-4 h-4" />}
              >
                시작
              </ActionButton>
            }
          >
            {sttQueue.length === 0
              ? <p className="text-base text-muted-foreground py-2">큐가 비어 있습니다</p>
              : sttQueue.map(item => (
                  <QueueItemRow
                    key={item.id}
                    item={item}
                    onRemove={id => setSttQueue(q => q.filter(i => i.id !== id))}
                  />
                ))}
          </QueueAccordionCard>

          <QueueAccordionCard
            title="자막 번역 큐"
            icon="🌐"
            count={subQueue.length}
            status={subQueue.some(i => i.status === "running") ? "running" : "inactive"}
          >
            {subQueue.length === 0
              ? <p className="text-base text-muted-foreground py-2">큐가 비어 있습니다</p>
              : subQueue.map(item => (
                  <QueueItemRow
                    key={item.id}
                    item={item}
                    onRemove={id => setSubQueue(q => q.filter(i => i.id !== id))}
                  />
                ))}
          </QueueAccordionCard>

          <GlassCard className="space-y-2">
            <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              처리 로그
            </h3>
            <LogPanel entries={MOCK_LOGS} maxHeight="180px" />
          </GlassCard>

        </div>
      </div>
    </div>
  );
}
