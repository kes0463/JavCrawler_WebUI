import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { Play, FileAudio, FolderOpen, Ban, Trash2, Loader2, Upload, Save, StickyNote } from "lucide-react";
import {
  addProcessingFolder,
  addToProcessingQueue,
  cancelProcessingQueue,
  clearProcessingFinished,
  clearProcessingQueue,
  createProcessingWS,
  fetchProcessingQueue,
  removeProcessingItem,
  startProcessingQueue,
  toQueueRow,
  type LogEntry,
  type ProcessingKind,
  type ProcessingQueueResponse,
  type ProcessingWsEvent,
  type SentenceLineEntry,
} from "@/api/processing";
import { GlassCard } from "@/components/ui/GlassCard";
import { ActionButton } from "@/components/ui/ActionButton";
import { QueueAccordionCard } from "@/components/queue/QueueAccordionCard";
import { QueueItemRow } from "@/components/queue/QueueItemRow";
import { LogPanel } from "@/components/log/LogPanel";
import { SentenceStreamPanel } from "@/components/log/SentenceStreamPanel";
import { cn } from "@/lib/utils";
import { extractFolderPathsFromSnapshot, isElectron, snapshotDataTransfer } from "@/lib/folderPaths";
import { pickFoldersDialog } from "@/api/harvest";
import { fetchTranslationPromptSettings, patchTranslationPromptSettings } from "@/api/settings";
import { TextArea } from "@/components/ui/SettingsControls";
import { useToast } from "@/contexts/ToastContext";
import { useNavigation } from "@/contexts/NavigationContext";

let logSeq = 0;
let sentenceSeq = 0;

const EMPTY_STATE: ProcessingQueueResponse = {
  stt: { items: [], running: false },
  subtitle: { items: [], running: false },
};

function applyWsState(
  prev: ProcessingQueueResponse,
  event: Extract<ProcessingWsEvent, { type: "state" }>,
): ProcessingQueueResponse {
  return {
    ...prev,
    stt: event.stt,
    subtitle: event.subtitle,
  };
}

function patchItem(
  section: ProcessingQueueResponse["stt"],
  id: string,
  patch: Partial<ProcessingQueueResponse["stt"]["items"][number]>,
) {
  return {
    ...section,
    items: section.items.map(i => (i.id === id ? { ...i, ...patch } : i)),
  };
}

export default function ProcessingView() {
  const { showToast } = useToast();
  const { currentView } = useNavigation();
  const [state, setState] = useState<ProcessingQueueResponse>(EMPTY_STATE);
  const [addKind, setAddKind] = useState<ProcessingKind>("stt");
  const [adding, setAdding] = useState(false);
  const [startingKind, setStartingKind] = useState<ProcessingKind | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [sentenceLines, setSentenceLines] = useState<SentenceLineEntry[]>([]);
  const [activeSentenceItemId, setActiveSentenceItemId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [translationNote, setTranslationNote] = useState("");
  const [noteSaved, setNoteSaved] = useState("");
  const [noteLoading, setNoteLoading] = useState(true);
  const [noteSaving, setNoteSaving] = useState(false);
  const dragDepthRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  const pushLog = useCallback((level: LogEntry["level"], text: string, ts?: string) => {
    logSeq += 1;
    setLogs(prev => [
      ...prev,
      { id: String(logSeq), level, text, ts: ts ?? new Date().toLocaleTimeString() },
    ].slice(-200));
  }, []);

  const handleWsEvent = useCallback((event: ProcessingWsEvent) => {
    if (event.type === "state") {
      setState(prev => applyWsState(prev, event));
      return;
    }
    if (event.type === "log") {
      const level = (["info", "warn", "error", "debug", "success"].includes(event.level)
        ? event.level
        : "info") as LogEntry["level"];
      pushLog(level, event.text, event.ts);
      return;
    }
    if (event.type === "queue_started") {
      setState(prev => ({
        ...prev,
        [event.kind]: { ...prev[event.kind], running: true },
      }));
      return;
    }
    if (event.type === "queue_finished") {
      setState(prev => ({
        ...prev,
        [event.kind]: { ...prev[event.kind], running: false },
      }));
      fetchProcessingQueue().then(setState).catch(() => {});
      return;
    }
    if (event.type === "content_clear") {
      setSentenceLines([]);
      setActiveSentenceItemId(event.id);
      return;
    }
    if (event.type === "content_line") {
      sentenceSeq += 1;
      setSentenceLines(prev => [
        ...prev,
        {
          id: String(sentenceSeq),
          kind: event.kind,
          lang: event.lang,
          text: event.text,
          start: event.start,
          end: event.end,
          index: event.index,
          ts: event.ts,
        },
      ].slice(-800));
      setActiveSentenceItemId(event.id);
      return;
    }
    if (event.type === "item_started") {
      setState(prev => ({
        ...prev,
        [event.kind]: patchItem(prev[event.kind], event.id, {
          status: "running",
          progress: 0,
          message: "시작...",
        }),
      }));
      return;
    }
    if (event.type === "progress") {
      setState(prev => ({
        ...prev,
        [event.kind]: patchItem(prev[event.kind], event.id, {
          progress: event.progress,
          message: event.message,
        }),
      }));
      return;
    }
    if (event.type === "item_done") {
      setState(prev => ({
        ...prev,
        [event.kind]: patchItem(prev[event.kind], event.id, {
          status: "done",
          progress: event.progress ?? 100,
          message: event.message ?? "완료",
        }),
      }));
      return;
    }
    if (event.type === "item_error") {
      setState(prev => ({
        ...prev,
        [event.kind]: patchItem(prev[event.kind], event.id, {
          status: "error",
          message: event.message,
        }),
      }));
      pushLog("error", event.message);
      return;
    }
    if (event.type === "item_cancelled") {
      setState(prev => ({
        ...prev,
        [event.kind]: patchItem(prev[event.kind], event.id, {
          status: "pending",
          progress: 0,
          message: "대기 중...",
        }),
      }));
    }
  }, [pushLog]);

  useEffect(() => {
    if (currentView !== "processing") return;
    fetchProcessingQueue().then(setState).catch(e => {
      showToast(e instanceof Error ? e.message : "큐를 불러오지 못했습니다", "error");
    });

    const ws = createProcessingWS(handleWsEvent);
    wsRef.current = ws;
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [currentView, handleWsEvent, showToast]);

  useEffect(() => {
    if (currentView !== "processing") return;
    let cancelled = false;
    setNoteLoading(true);
    fetchTranslationPromptSettings()
      .then(snap => {
        if (cancelled) return;
        setTranslationNote(snap.global_note);
        setNoteSaved(snap.global_note);
      })
      .catch(e => {
        if (!cancelled) {
          showToast(e instanceof Error ? e.message : "번역 노트 불러오기 실패", "error");
        }
      })
      .finally(() => {
        if (!cancelled) setNoteLoading(false);
      });
    return () => { cancelled = true; };
  }, [currentView, showToast]);

  const noteDirty = translationNote !== noteSaved;

  const handleSaveTranslationNote = async () => {
    setNoteSaving(true);
    try {
      const snap = await patchTranslationPromptSettings({ global_note: translationNote });
      setTranslationNote(snap.global_note);
      setNoteSaved(snap.global_note);
      showToast("번역 노트 저장됨", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "번역 노트 저장 실패", "error");
    } finally {
      setNoteSaving(false);
    }
  };

  const handleAddPaths = async (kind: ProcessingKind, paths: string[]) => {
    if (!paths.length) return;
    setAdding(true);
    try {
      const snap = await addToProcessingQueue(kind, paths);
      setState(snap);
      const planned = snap.planned ?? paths.length;
      showToast(`${planned}건 ${kind === "stt" ? "STT" : "번역"} 큐에 추가`, "success");
      if (snap.warnings?.length) {
        showToast(snap.warnings[0], "warn");
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "추가 실패", "error");
    } finally {
      setAdding(false);
    }
  };

  const handleAddFolders = async (kind: ProcessingKind, folders: string[]) => {
    if (!folders.length) return;
    setAdding(true);
    try {
      let lastSnap = state;
      for (const folder of folders) {
        lastSnap = await addProcessingFolder(kind, folder);
      }
      setState(lastSnap);
      showToast(`폴더 ${folders.length}개 → ${kind === "stt" ? "STT" : "번역"} 큐`, "success");
      if (lastSnap.warnings?.length) {
        showToast(lastSnap.warnings[0], "warn");
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "폴더 추가 실패", "error");
    } finally {
      setAdding(false);
    }
  };

  const handlePickFolder = async (kind: ProcessingKind) => {
    const paths = await pickFoldersDialog();
    if (!paths.length) return;
    await handleAddFolders(kind, paths);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    dragDepthRef.current = 0;
    setDragging(false);

    const videoPaths: string[] = [];
    for (const file of Array.from(e.dataTransfer.files)) {
      const f = file as File & { path?: string };
      let p = f.path?.trim();
      if (!p && typeof window !== "undefined") {
        p = window.javstory?.getPathForFile?.(file)?.trim() || "";
      }
      if (p && /\.(mp4|mkv|avi|wmv|mov|m4v|ts|webm|flv|mpg|mpeg)$/i.test(p)) {
        videoPaths.push(p);
      }
    }
    if (videoPaths.length) {
      void handleAddPaths(addKind, videoPaths);
      return;
    }

    const folders = extractFolderPathsFromSnapshot(snapshotDataTransfer(e.dataTransfer));
    if (folders.length) {
      void handleAddFolders(addKind, folders);
    }
  };

  const handleStart = async (kind: ProcessingKind) => {
    setStartingKind(kind);
    try {
      const res = await startProcessingQueue(kind);
      showToast(`${kind === "stt" ? "STT" : "번역"} 큐 시작 (${res.queued}건)`, "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "시작 실패", "error");
    } finally {
      setStartingKind(null);
    }
  };

  const handleCancel = async (kind: ProcessingKind) => {
    try {
      await cancelProcessingQueue(kind);
      showToast(`${kind === "stt" ? "STT" : "번역"} 큐 중지 요청`, "info");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "중지 실패", "error");
    }
  };

  const handleRemove = async (kind: ProcessingKind, id: string) => {
    try {
      await removeProcessingItem(kind, id);
      setState(prev => ({
        ...prev,
        [kind]: {
          ...prev[kind],
          items: prev[kind].items.filter(i => i.id !== id),
        },
      }));
    } catch (e) {
      showToast(e instanceof Error ? e.message : "삭제 실패", "error");
    }
  };

  const handleClearFinished = async (kind: ProcessingKind) => {
    try {
      const res = await clearProcessingFinished(kind);
      const snap = await fetchProcessingQueue();
      setState(snap);
      showToast(`완료 항목 ${res.removed}건 삭제`, "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "삭제 실패", "error");
    }
  };

  const handleClearAll = async (kind: ProcessingKind) => {
    const label = kind === "stt" ? "STT" : "번역";
    const n = state[kind].items.length;
    if (!n) {
      showToast(`${label} 큐가 이미 비어 있습니다`, "info");
      return;
    }
    try {
      const res = await clearProcessingQueue(kind);
      const snap = await fetchProcessingQueue();
      setState(snap);
      showToast(`${label} 큐 ${res.removed}건 전체 삭제`, "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "전체 삭제 실패", "error");
    }
  };

  const runningCount =
    state.stt.items.filter(i => i.status === "running").length
    + state.subtitle.items.filter(i => i.status === "running").length;

  const sttRows = state.stt.items.map(toQueueRow);
  const subRows = state.subtitle.items.map(toQueueRow);

  return (
    <div
      className="space-y-5 animate-fade-in"
      onDragEnter={e => {
        e.preventDefault();
        dragDepthRef.current += 1;
        setDragging(true);
      }}
      onDragLeave={e => {
        e.preventDefault();
        dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
        if (dragDepthRef.current === 0) setDragging(false);
      }}
      onDragOver={e => e.preventDefault()}
      onDrop={handleDrop}
    >
      {dragging && (
        <div className="fixed inset-0 z-[100] bg-indigo-500/10 border-2 border-dashed border-indigo-400/50 pointer-events-none flex items-center justify-center">
          <p className="text-indigo-200 text-lg font-medium">폴더 또는 영상 파일을 여기로 놓으세요</p>
        </div>
      )}

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">전사 · 자막</h1>
          <p className="text-base text-muted-foreground mt-0.5">STT 전사(stable-ts) 및 JA→KO 자막 번역</p>
        </div>
        {runningCount > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/15 border border-indigo-500/25">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
            <span className="text-sm text-indigo-300">{runningCount}개 처리 중</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="space-y-4">
          <GlassCard className="space-y-3">
            <div className="flex items-center gap-2">
              <FileAudio className="w-5 h-5 text-muted-foreground" />
              <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
                파일 추가
              </h3>
            </div>
            <div className="flex gap-2">
              {(["stt", "subtitle"] as const).map(k => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setAddKind(k)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    addKind === k
                      ? "border-indigo-500/40 bg-indigo-500/15 text-indigo-200"
                      : "border-white/10 text-muted-foreground hover:bg-white/[0.04]"
                  }`}
                >
                  {k === "stt" ? "STT" : "번역"}
                </button>
              ))}
            </div>
            <div
              className={cn(
                "rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors",
                dragging
                  ? "border-accent/50 bg-accent/10"
                  : "border-white/[0.10] bg-bg-base/50",
              )}
            >
              <Upload className={cn(
                "w-8 h-8 mx-auto mb-2",
                dragging ? "text-accent-light" : "text-muted-foreground",
              )} />
              <p className="text-sm text-[#d0d0e8]">폴더 또는 영상 파일 드래그&드롭</p>
              <p className="text-xs text-muted-foreground mt-1">폴더는 직하위 영상만 추가됩니다</p>
            </div>
            <ActionButton
              variant="primary"
              className="w-full"
              icon={adding ? <Loader2 className="w-4 h-4 animate-spin" /> : <FolderOpen className="w-4 h-4" />}
              disabled={adding}
              onClick={() => void handlePickFolder(addKind)}
            >
              폴더 선택
            </ActionButton>
          </GlassCard>

          <GlassCard variant="subtle" className="text-base text-muted-foreground space-y-1.5">
            <p className="text-[#c8c8e0] font-medium">처리 순서</p>
            <ol className="space-y-1 list-decimal list-inside">
              <li>폴더 선택 또는 드래그&드롭으로 추가</li>
              <li>STT 전사 (stable-ts / Whisper large-v2)</li>
              <li>KO 번역 (LLM)</li>
              <li>`.ja.srt` / `.ko.srt` 저장</li>
            </ol>
            {!isElectron() && (
              <p className="text-sm pt-1">폴더 선택 버튼은 Electron 앱에서 사용할 수 있습니다. 브라우저에서는 드래그&드롭을 이용하세요.</p>
            )}
          </GlassCard>
        </div>

        <div className="lg:col-span-2 space-y-4">
          <QueueAccordionCard
            title="STT 전사 큐"
            icon="🎤"
            count={sttRows.length}
            status={state.stt.running ? "running" : sttRows.some(i => i.status === "pending") ? "pending" : "inactive"}
            actions={
              <div className="flex items-center gap-2">
                {state.stt.running ? (
                  <ActionButton
                    variant="secondary"
                    size="sm"
                    icon={<Ban className="w-4 h-4" />}
                    onClick={() => void handleCancel("stt")}
                  >
                    중지
                  </ActionButton>
                ) : (
                  <ActionButton
                    variant="primary"
                    size="sm"
                    icon={startingKind === "stt" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    disabled={!sttRows.some(i => i.status === "pending") || startingKind !== null}
                    onClick={() => void handleStart("stt")}
                  >
                    시작
                  </ActionButton>
                )}
                <ActionButton
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 className="w-4 h-4" />}
                  onClick={() => void handleClearFinished("stt")}
                >
                  완료 삭제
                </ActionButton>
                <ActionButton
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 className="w-4 h-4" />}
                  disabled={sttRows.length === 0}
                  onClick={() => void handleClearAll("stt")}
                >
                  전체 삭제
                </ActionButton>
              </div>
            }
          >
            {sttRows.length === 0
              ? <p className="text-base text-muted-foreground py-2">큐가 비어 있습니다</p>
              : sttRows.map(item => (
                  <QueueItemRow
                    key={item.id}
                    item={item}
                    onRemove={id => void handleRemove("stt", id)}
                  />
                ))}
          </QueueAccordionCard>

          <QueueAccordionCard
            title="자막 번역 큐"
            icon="🌐"
            count={subRows.length}
            status={state.subtitle.running ? "running" : subRows.some(i => i.status === "pending") ? "pending" : "inactive"}
            actions={
              <div className="flex items-center gap-2">
                {state.subtitle.running ? (
                  <ActionButton
                    variant="secondary"
                    size="sm"
                    icon={<Ban className="w-4 h-4" />}
                    onClick={() => void handleCancel("subtitle")}
                  >
                    중지
                  </ActionButton>
                ) : (
                  <ActionButton
                    variant="primary"
                    size="sm"
                    icon={startingKind === "subtitle" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    disabled={!subRows.some(i => i.status === "pending") || startingKind !== null}
                    onClick={() => void handleStart("subtitle")}
                  >
                    시작
                  </ActionButton>
                )}
                <ActionButton
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 className="w-4 h-4" />}
                  onClick={() => void handleClearFinished("subtitle")}
                >
                  완료 삭제
                </ActionButton>
                <ActionButton
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 className="w-4 h-4" />}
                  disabled={subRows.length === 0}
                  onClick={() => void handleClearAll("subtitle")}
                >
                  전체 삭제
                </ActionButton>
              </div>
            }
          >
            {subRows.length === 0
              ? <p className="text-base text-muted-foreground py-2">큐가 비어 있습니다</p>
              : subRows.map(item => (
                  <QueueItemRow
                    key={item.id}
                    item={item}
                    onRemove={id => void handleRemove("subtitle", id)}
                  />
                ))}
          </QueueAccordionCard>

          <GlassCard className="space-y-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="flex items-start gap-2 min-w-0">
                <StickyNote className="w-5 h-5 text-muted-foreground shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
                    번역 노트
                  </h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    시스템 프롬프트 <code className="text-violet-300/90">{"{{note}}"}</code>에
                    삽입됩니다. 추가 지시·용어집을 작성한 뒤 저장하세요.
                    (배우·작품 노트가 있으면 함께 합쳐집니다)
                  </p>
                </div>
              </div>
              <ActionButton
                variant={noteDirty ? "primary" : "ghost"}
                size="sm"
                loading={noteSaving}
                disabled={noteLoading || (!noteDirty && !noteSaving)}
                icon={<Save className="w-3.5 h-3.5" />}
                onClick={() => void handleSaveTranslationNote()}
              >
                {noteDirty ? "저장" : "저장됨"}
              </ActionButton>
            </div>
            {noteLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground py-6 justify-center">
                <Loader2 className="w-4 h-4 animate-spin" />
                불러오는 중…
              </div>
            ) : (
              <TextArea
                value={translationNote}
                onChange={setTranslationNote}
                rows={6}
                placeholder={"독백은 반말로 번역.\n古明地こいし=코메이지 코이시"}
                className="text-sm"
              />
            )}
          </GlassCard>

          <GlassCard className="space-y-2">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
                전사 · 번역 문장
              </h3>
              {activeSentenceItemId && sentenceLines.length > 0 && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {sentenceLines.length}줄
                </span>
              )}
            </div>
            <SentenceStreamPanel entries={sentenceLines} maxHeight="300px" />
          </GlassCard>

          <GlassCard className="space-y-2">
            <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              처리 로그
            </h3>
            <LogPanel entries={logs} maxHeight="220px" />
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
