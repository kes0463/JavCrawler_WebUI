import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  Eye,
  Loader2,
  MessageSquarePlus,
  Pencil,
  RefreshCw,
  Search,
  Send,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { fetchLlamaCppStatus, type LlamaCppState } from "@/api/llamacpp";
import {
  streamPersonaChat,
  type PersonaChatHistoryTurn,
  type PersonaChatRecommendationItem,
  type PersonaChatUsage,
} from "@/api/personaChat";
import { coverUrl } from "@/api/library";
import {
  createPersonaChatSession,
  deletePersonaChatSession,
  fetchPersonaChatSession,
  fetchPersonaChatSessions,
  renamePersonaChatSession,
  truncatePersonaChatSession,
  type PersonaChatSessionSummary,
} from "@/api/personaChatSessions";
import {
  fetchPersonaChatMemory,
  removePersonaChatMemoryNote,
  type PersonaChatMemoryCategory,
  type PersonaChatMemorySnapshot,
} from "@/api/personaChatMemory";
import { ModelPickerDropdown } from "@/components/llamacpp/ModelPickerDropdown";
import { GlassCard } from "@/components/ui/GlassCard";
import { LibraryDetailPanel } from "@/components/library/LibraryDetailPanel";
import { useLlamaCppModelPicker } from "@/hooks/useLlamaCppModelPicker";
import { useNavigation } from "@/contexts/NavigationContext";
import { usePlayer } from "@/contexts/PlayerContext";
import { useToast } from "@/contexts/ToastContext";
import { cn } from "@/lib/utils";

// javstory/persona/library_search.py의 _PRODUCT_CODE_RE와 동일한 취지(영문 접두 + 숫자).
const PRODUCT_CODE_RE = /(?<![A-Za-z0-9])([A-Za-z]{1,8})[-_\s]?(\d{2,7})(?![A-Za-z0-9])/g;

/** 메시지 안에 직접 언급된 첫 품번 — 있으면 백엔드 product_code 컨텍스트로 우선 전달한다. */
function firstProductCode(text: string): string | undefined {
  const match = text.matchAll(PRODUCT_CODE_RE).next().value as RegExpMatchArray | undefined;
  return match ? `${match[1].toUpperCase()}-${match[2]}` : undefined;
}

function renderMessageContent(text: string, onCodeClick: (code: string) => void) {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  for (const match of text.matchAll(PRODUCT_CODE_RE)) {
    const idx = match.index ?? 0;
    if (idx > lastIndex) nodes.push(<Fragment key={key++}>{text.slice(lastIndex, idx)}</Fragment>);
    const raw = match[0];
    const code = `${match[1].toUpperCase()}-${match[2]}`;
    nodes.push(
      <button
        key={key++}
        type="button"
        onClick={() => onCodeClick(code)}
        className="text-accent-light underline underline-offset-2 decoration-accent-light/40 hover:decoration-accent-light"
      >
        {raw}
      </button>,
    );
    lastIndex = idx + raw.length;
  }
  if (lastIndex < text.length) nodes.push(<Fragment key={key++}>{text.slice(lastIndex)}</Fragment>);
  return nodes;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 클립보드 접근 실패 시 조용히 무시 */
    }
  }, [text]);
  return (
    <button
      type="button"
      onClick={() => void handleCopy()}
      title="답변 복사"
      className="inline-flex items-center gap-1 text-slate-500 hover:text-slate-300"
    >
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  reasoning?: string;
  thinkingOpen?: boolean;
  error?: boolean;
  stopped?: boolean;
  usage?: PersonaChatUsage | null;
  elapsedSec?: number | null;
  tokensPerSec?: number | null;
  recommendations?: PersonaChatRecommendationItem[];
  /** 서버 세션 파일에 실제로 저장됐는지 — edit&resend가 truncate할 개수를 셀 때 씀. */
  persisted?: boolean;
}

/** 추천 답변에 실제로 언급된 후보의 랭킹 근거를 짧은 배지로 — 원인 배지는 최대 3개로 압축. */
function recommendationBadges(item: PersonaChatRecommendationItem): string[] {
  const badges = [...item.matched_genre_terms, ...item.matched_query_terms, ...item.matched_persona_terms];
  return Array.from(new Set(badges)).slice(0, 3);
}

function RecommendationCard({
  item,
  onOpen,
}: {
  item: PersonaChatRecommendationItem;
  onOpen: (code: string) => void;
}) {
  const badges = recommendationBadges(item);
  return (
    <button
      type="button"
      onClick={() => onOpen(item.product_code)}
      className="group flex-shrink-0 w-40 text-left rounded-xl border border-white/[0.08] bg-black/20 overflow-hidden hover:border-accent/40 transition-colors"
    >
      <div className="relative aspect-[3/2] bg-black/40">
        <img
          src={coverUrl(item.product_code)}
          alt={item.product_code}
          className="absolute inset-0 w-full h-full object-cover"
          loading="lazy"
          onError={e => {
            (e.target as HTMLImageElement).style.display = "none";
          }}
        />
        {item.persona_match_score > 0 && (
          <span className="absolute top-1.5 right-1.5 text-[10px] px-1.5 py-0.5 rounded-md bg-black/70 text-amber-300 tabular-nums">
            {Math.round(item.persona_match_score)}점
          </span>
        )}
      </div>
      <div className="p-2 space-y-1">
        <p className="text-xs font-semibold text-white truncate">{item.product_code}</p>
        <p className="text-xs text-slate-300 line-clamp-2 leading-snug min-h-[2.2em]">{item.title || "—"}</p>
        {item.matched_seed_title && (
          <p className="text-[10px] text-accent-light/80 line-clamp-1">
            «{item.matched_seed_title}»과 비슷해서
          </p>
        )}
        {badges.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {badges.map(badge => (
              <span
                key={badge}
                className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-400 border border-white/[0.06]"
              >
                {badge}
              </span>
            ))}
          </div>
        )}
      </div>
    </button>
  );
}

function isAbortError(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

function formatTokenInfo(m: Pick<ChatMessage, "usage" | "tokensPerSec" | "elapsedSec">): string | null {
  const parts: string[] = [];
  const completion = m.usage?.completion_tokens;
  if (typeof completion === "number") parts.push(`${completion.toLocaleString()} tokens`);
  if (typeof m.tokensPerSec === "number") parts.push(`${m.tokensPerSec.toFixed(1)} tok/s`);
  if (typeof m.elapsedSec === "number") parts.push(`${m.elapsedSec.toFixed(1)}s`);
  return parts.length ? parts.join(" · ") : null;
}

function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMin = Math.round((Date.now() - then) / 60000);
  if (diffMin < 1) return "방금";
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;
  const diffDay = Math.round(diffHour / 24);
  return `${diffDay}일 전`;
}

// gui/qml/components/PersonaChatWidget.qml의 memoryPanel과 동일한 카테고리/라벨.
const MEMORY_NOTE_GROUPS: {
  key: keyof Pick<
    PersonaChatMemorySnapshot,
    "preference_notes" | "strong_reaction_notes" | "negative_feedback_notes" | "correction_notes" | "style_notes"
  >;
  category: PersonaChatMemoryCategory;
  label: string;
}[] = [
  { key: "preference_notes", category: "preference", label: "취향" },
  { key: "strong_reaction_notes", category: "strong_reaction", label: "강한 반응" },
  { key: "negative_feedback_notes", category: "negative_feedback", label: "비선호" },
  { key: "correction_notes", category: "correction", label: "교정" },
  { key: "style_notes", category: "style", label: "말투" },
];

let _nextId = 0;

export default function PersonaChatView() {
  const { showToast } = useToast();
  const { openPlayer } = usePlayer();
  const { personaChatEntry, clearPersonaChatEntry } = useNavigation();
  const [detailCode, setDetailCode] = useState<string | null>(null);
  // detailCode와 별개 — 상세 패널을 띄우지 않고 다음 메시지에만 조용히 붙는 작품 컨텍스트.
  // (딥링크로 "물어보기"를 눌렀을 때 상세 패널이 채팅 화면을 덮지 않게 하기 위함)
  const [focusProductCode, setFocusProductCode] = useState<string | null>(null);
  const picker = useLlamaCppModelPicker("persona_chat");
  const [sessions, setSessions] = useState<PersonaChatSessionSummary[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [renamingSessionId, setRenamingSessionId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const [sessionSearch, setSessionSearch] = useState("");
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [elapsedNowMs, setElapsedNowMs] = useState(0);
  const [serverState, setServerState] = useState<LlamaCppState | null>(null);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [memory, setMemory] = useState<PersonaChatMemorySnapshot | null>(null);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const sendStartedAtRef = useRef(0);

  // 라이브러리/배우 상세 등에서 딥링크로 들어온 경우 — 작품 컨텍스트를 붙이고/입력창을
  // 채운 뒤 한 번만 소비한다(이 탭은 PERSIST_VIEWS라 언마운트 없이 계속 떠 있으므로
  // 마운트 시점이 아니라 값이 바뀔 때마다 반응해야 한다).
  useEffect(() => {
    if (!personaChatEntry) return;
    if (personaChatEntry.productCode) setFocusProductCode(personaChatEntry.productCode);
    if (personaChatEntry.prefillMessage) setInput(personaChatEntry.prefillMessage);
    clearPersonaChatEntry();
  }, [personaChatEntry, clearPersonaChatEntry]);

  // 최초 진입 시: 대화 목록을 불러와 가장 최근 대화로 들어가고, 대화가 하나도 없으면 새로 만든다.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { sessions: list } = await fetchPersonaChatSessions();
        if (cancelled) return;
        setSessions(list);
        if (list.length > 0) {
          const detail = await fetchPersonaChatSession(list[0].id);
          if (cancelled) return;
          setCurrentSessionId(detail.id);
          setMessages(
            detail.messages.map(m => ({
              id: ++_nextId,
              role: m.role,
              content: m.content,
              reasoning: m.reasoning || undefined,
              persisted: true,
            })),
          );
        } else {
          const created = await createPersonaChatSession();
          if (cancelled) return;
          setSessions([created]);
          setCurrentSessionId(created.id);
          setMessages([]);
        }
      } catch (e) {
        showToast(e instanceof Error ? e.message : "대화 목록을 불러오지 못했습니다", "error");
      } finally {
        if (!cancelled) setLoadingSession(false);
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!streaming) return;
    sendStartedAtRef.current = Date.now();
    setElapsedNowMs(0);
    const timer = window.setInterval(() => {
      setElapsedNowMs(Date.now() - sendStartedAtRef.current);
    }, 250);
    return () => window.clearInterval(timer);
  }, [streaming]);

  // 채팅 전송이 (모델 미선택 상태에서도) llama-server를 암묵적으로 기동시킬 수 있어,
  // "생각 중"과 "VRAM에 모델 로딩 중"을 구분해서 보여주기 위해 스트리밍 중엔 서버
  // 상태를 함께 폴링한다 — 그렇지 않으면 로딩 중에도 그냥 "생각 중"으로만 보여서
  // 실제로는 GPU에 모델을 올리는 중인데 멈춘 것처럼 보인다.
  useEffect(() => {
    if (!streaming) {
      setServerState(null);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const st = await fetchLlamaCppStatus();
        if (!cancelled) setServerState(st.state);
      } catch {
        /* 폴링 실패는 무시 — 상태 표시만 못 할 뿐 스트리밍 자체엔 영향 없음 */
      }
    };
    void poll();
    const timer = window.setInterval(poll, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [streaming]);

  const lastTokenInfo = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "assistant") return formatTokenInfo(m);
    }
    return null;
  }, [messages]);

  // 딥링크로 조용히 붙은 컨텍스트(focusProductCode)를 우선하고, 없으면 채팅 안에서
  // 직접 연 상세 패널(detailCode)을 이어 쓴다 — 패널을 닫으면(둘 다 같은 곳에서
  // setDetailCode(null)) 자연히 컨텍스트도 같이 풀린다.
  const activeFocusCode = focusProductCode ?? detailCode;

  // 지금 붙어 있는 작품 컨텍스트가 다음 전송에 붙는지 보여주는 칩 —
  // 입력창에 이미 품번을 직접 썼다면 그게 우선이라 칩은 숨긴다.
  const pendingFocusCode = useMemo(
    () => (activeFocusCode && !firstProductCode(input) ? activeFocusCode : null),
    [activeFocusCode, input],
  );

  const filteredSessions = useMemo(() => {
    const q = sessionSearch.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter(s => s.title.toLowerCase().includes(q));
  }, [sessions, sessionSearch]);

  // "마지막 사용자 메시지 수정" 대상 — 목록에서 가장 최근 사용자 메시지 하나만 허용한다.
  const lastUserMessageId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") return messages[i].id;
    }
    return null;
  }, [messages]);

  const refreshSessions = useCallback(async () => {
    try {
      const { sessions: list } = await fetchPersonaChatSessions();
      setSessions(list);
    } catch {
      /* 목록 갱신 실패는 조용히 무시 — 대화 자체는 이미 진행된 상태 */
    }
  }, []);

  const handleNewConversation = useCallback(async () => {
    if (streaming) return;
    try {
      const created = await createPersonaChatSession();
      setSessions(prev => [created, ...prev]);
      setCurrentSessionId(created.id);
      setMessages([]);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "새 대화 시작 실패", "error");
    }
  }, [streaming, showToast]);

  const handleSelectSession = useCallback(
    async (id: string) => {
      if (streaming || id === currentSessionId) return;
      setLoadingSession(true);
      try {
        const detail = await fetchPersonaChatSession(id);
        setCurrentSessionId(detail.id);
        setMessages(
          detail.messages.map(m => ({
            id: ++_nextId,
            role: m.role,
            content: m.content,
            reasoning: m.reasoning || undefined,
          })),
        );
      } catch (e) {
        showToast(e instanceof Error ? e.message : "대화를 불러오지 못했습니다", "error");
      } finally {
        setLoadingSession(false);
      }
    },
    [streaming, currentSessionId, showToast],
  );

  const handleDeleteSession = useCallback(
    async (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      if (streaming) return;
      if (!confirm("이 대화를 삭제할까요?")) return;
      try {
        await deletePersonaChatSession(id);
        const remaining = sessions.filter(s => s.id !== id);
        setSessions(remaining);
        if (id === currentSessionId) {
          if (remaining.length > 0) {
            void handleSelectSession(remaining[0].id);
          } else {
            const created = await createPersonaChatSession();
            setSessions([created]);
            setCurrentSessionId(created.id);
            setMessages([]);
          }
        }
      } catch (e2) {
        showToast(e2 instanceof Error ? e2.message : "대화 삭제 실패", "error");
      }
    },
    [streaming, sessions, currentSessionId, handleSelectSession, showToast],
  );

  const handleStartRename = useCallback((session: PersonaChatSessionSummary, e: React.MouseEvent) => {
    e.stopPropagation();
    setRenamingSessionId(session.id);
    setRenameDraft(session.title);
  }, []);

  const handleCancelRename = useCallback((e?: React.MouseEvent) => {
    e?.stopPropagation();
    setRenamingSessionId(null);
    setRenameDraft("");
  }, []);

  const handleSaveRename = useCallback(
    async (id: string) => {
      const title = renameDraft.trim();
      setRenamingSessionId(null);
      if (!title) return;
      const previous = sessions.find(s => s.id === id)?.title;
      if (title === previous) return;
      setRenameSaving(true);
      try {
        const updated = await renamePersonaChatSession(id, title);
        setSessions(prev => prev.map(s => (s.id === id ? { ...s, title: updated.title } : s)));
      } catch (e) {
        showToast(e instanceof Error ? e.message : "대화 이름 변경 실패", "error");
      } finally {
        setRenameSaving(false);
      }
    },
    [renameDraft, sessions, showToast],
  );

  const loadMemory = useCallback(async () => {
    setMemoryLoading(true);
    try {
      const snapshot = await fetchPersonaChatMemory();
      setMemory(snapshot);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "기억을 불러오지 못했습니다", "error");
    } finally {
      setMemoryLoading(false);
    }
  }, [showToast]);

  const handleToggleMemory = useCallback(() => {
    setMemoryOpen(prev => {
      const next = !prev;
      if (next) void loadMemory();
      return next;
    });
  }, [loadMemory]);

  const handleRemoveMemoryNote = useCallback(
    async (category: PersonaChatMemoryCategory, index: number) => {
      try {
        const snapshot = await removePersonaChatMemoryNote(category, index);
        setMemory(snapshot);
      } catch (e) {
        showToast(e instanceof Error ? e.message : "기억 삭제 실패", "error");
      }
    },
    [showToast],
  );

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const toggleThinking = useCallback((id: number) => {
    setMessages(prev =>
      prev.map(m => (m.id === id ? { ...m, thinkingOpen: !m.thinkingOpen } : m)),
    );
  }, []);

  // handleSend/handleRetry/handleResendEditedMessage가 공유하는 실제 스트리밍 실행부 —
  // assistantId 자리의 메시지 하나에 토큰/추론/추천/완료를 채워 넣는다.
  const runTurn = useCallback(
    async (text: string, history: PersonaChatHistoryTurn[], assistantId: number) => {
      // 메시지에 품번이 직접 언급됐으면 그걸, 아니면 지금 붙어 있는 작품 컨텍스트를
      // "이어서 묻는" 대상으로 백엔드에 넘긴다(둘 다 없으면 컨텍스트 없이 일반 대화).
      const contextProductCode = firstProductCode(text) ?? activeFocusCode ?? undefined;

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      let completed = false;
      try {
        for await (const event of streamPersonaChat(text, history, currentSessionId, contextProductCode, ctrl.signal)) {
          if (event.type === "token") {
            setMessages(prev =>
              prev.map(m => (m.id === assistantId ? { ...m, content: m.content + event.text } : m)),
            );
          } else if (event.type === "reasoning") {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, reasoning: (m.reasoning ?? "") + event.text } : m,
              ),
            );
          } else if (event.type === "recommendations") {
            setMessages(prev =>
              prev.map(m => (m.id === assistantId ? { ...m, recommendations: event.items } : m)),
            );
          } else if (event.type === "done") {
            completed = true;
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: event.text,
                      usage: event.usage ?? null,
                      elapsedSec: event.elapsed_sec ?? null,
                      tokensPerSec: event.tokens_per_sec ?? null,
                      persisted: true,
                    }
                  : m,
              ),
            );
          } else if (event.type === "error") {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, content: event.message, error: true } : m,
              ),
            );
            showToast(event.message, "error");
          }
        }
      } catch (e) {
        if (isAbortError(e)) {
          setMessages(prev =>
            prev.map(m => (m.id === assistantId ? { ...m, stopped: true } : m)),
          );
        } else {
          const msg = e instanceof Error ? e.message : "응답 스트리밍 실패";
          setMessages(prev =>
            prev.map(m => (m.id === assistantId ? { ...m, content: msg, error: true } : m)),
          );
          showToast(msg, "error");
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
        // 첫 메시지였다면 서버가 자동으로 지은 제목/순서를 목록에 반영.
        if (completed) {
          void refreshSessions();
          // 서버는 매 턴마다 메모리를 갱신하므로, 패널이 열려 있으면 최신 상태로 맞춘다.
          if (memoryOpen) void loadMemory();
        }
      }
    },
    [currentSessionId, activeFocusCode, showToast, refreshSessions, memoryOpen, loadMemory],
  );

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming || !currentSessionId) return;
    setInput("");

    const history: PersonaChatHistoryTurn[] = messages
      .filter(m => !m.error)
      .map(m => ({ role: m.role, content: m.content }));

    const userMsg: ChatMessage = { id: ++_nextId, role: "user", content: text };
    const assistantId = ++_nextId;
    setMessages(prev => [...prev, userMsg, { id: assistantId, role: "assistant", content: "" }]);
    setStreaming(true);
    await runTurn(text, history, assistantId);
  }, [input, messages, streaming, currentSessionId, runTurn]);

  // 실패한 응답에 "다시 시도" — 같은 사용자 메시지·이전 히스토리로 같은 자리에 다시 스트리밍한다.
  // 실패한 턴은 애초에 서버 세션 파일에 저장되지 않으므로(webapi/routes/persona_chat.py의
  // _sse_gen은 full_text가 있을 때만 append_turn) truncate가 필요 없다.
  const handleRetry = useCallback(
    async (assistantId: number) => {
      if (streaming || !currentSessionId) return;
      const idx = messages.findIndex(m => m.id === assistantId);
      if (idx < 0) return;
      let userIdx = idx - 1;
      while (userIdx >= 0 && messages[userIdx].role !== "user") userIdx--;
      if (userIdx < 0) return;
      const text = messages[userIdx].content;
      const history: PersonaChatHistoryTurn[] = messages
        .slice(0, userIdx)
        .filter(m => !m.error)
        .map(m => ({ role: m.role, content: m.content }));

      setMessages(prev =>
        prev.map(m => (m.id === assistantId ? { id: assistantId, role: "assistant", content: "" } : m)),
      );
      setStreaming(true);
      await runTurn(text, history, assistantId);
    },
    [messages, streaming, currentSessionId, runTurn],
  );

  const handleStartEditMessage = useCallback(
    (m: ChatMessage) => {
      if (streaming) return;
      setEditingMessageId(m.id);
      setEditDraft(m.content);
    },
    [streaming],
  );

  const handleCancelEditMessage = useCallback(() => {
    setEditingMessageId(null);
    setEditDraft("");
  }, []);

  // 마지막 사용자 메시지를 고쳐서 재전송 — 그 메시지와 그 뒤(원래 답변 포함)를 지우고
  // 새 턴을 이어 붙인다. 서버 세션 파일도 같은 지점까지 잘라서(truncate) 재전송 후
  // 다른 대화로 갔다 돌아와도 옛 턴이 다시 나타나지 않게 한다.
  const handleResendEditedMessage = useCallback(
    async (id: number) => {
      const text = editDraft.trim();
      setEditingMessageId(null);
      if (!text || !currentSessionId || streaming) return;
      const idx = messages.findIndex(m => m.id === id);
      if (idx < 0) return;

      const before = messages.slice(0, idx);
      const history: PersonaChatHistoryTurn[] = before
        .filter(m => !m.error)
        .map(m => ({ role: m.role, content: m.content }));
      // 서버에는 성공적으로 끝난(=persisted) 턴만 (user, assistant) 쌍으로 저장돼 있으므로,
      // 그 쌍의 개수만큼만 남기고 잘라야 실패/중지된 시도로 개수가 어긋나지 않는다.
      const persistedPairsBefore = before.filter(m => m.role === "assistant" && m.persisted).length;

      const editedUserMsg: ChatMessage = { id, role: "user", content: text, persisted: false };
      const assistantId = ++_nextId;
      setMessages(prev => [...before, editedUserMsg, { id: assistantId, role: "assistant", content: "" }]);
      setStreaming(true);
      try {
        await truncatePersonaChatSession(currentSessionId, persistedPairsBefore * 2);
      } catch (e) {
        showToast(e instanceof Error ? e.message : "이전 답변 정리 실패 — 계속 진행합니다", "error");
      }
      await runTurn(text, history, assistantId);
    },
    [editDraft, messages, currentSessionId, streaming, runTurn, showToast],
  );

  const handleExportMarkdown = useCallback(() => {
    const title = sessions.find(s => s.id === currentSessionId)?.title || "페르소나챗 대화";
    const lines: string[] = [`# ${title}`, ""];
    for (const m of messages) {
      if (m.error || !m.content) continue;
      lines.push(m.role === "user" ? "**나**" : "**페르소나챗**", "", m.content, "");
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/[\\/:*?"<>|]/g, "_").slice(0, 60)}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [sessions, currentSessionId, messages]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend],
  );

  return (
    <div className="flex flex-col h-[calc(100vh-220px)] min-h-[560px] space-y-4 animate-fade-in">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Persona Chat</h1>
          <p className="text-base text-muted-foreground mt-0.5">
            취향 기반 대화형 추천 큐레이터
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleToggleMemory}
            className={cn(
              "inline-flex items-center gap-1.5 h-9 px-3 rounded-xl border text-sm",
              memoryOpen
                ? "bg-accent/15 text-accent-light border-accent/30"
                : "text-slate-300 border-white/10 hover:bg-white/[0.04]",
            )}
          >
            <Brain className="w-4 h-4" />
            {memoryOpen ? "기억 닫기" : "기억 보기"}
          </button>
          <button
            type="button"
            onClick={handleExportMarkdown}
            disabled={messages.length === 0}
            title="이 대화를 마크다운으로 내보내기"
            className="inline-flex items-center justify-center w-9 h-9 rounded-xl border border-white/10 text-slate-300 hover:bg-white/[0.04] disabled:opacity-40 disabled:pointer-events-none"
          >
            <Download className="w-4 h-4" />
          </button>
          <ModelPickerDropdown picker={picker} />
        </div>
      </div>

      {memoryOpen && (
        <GlassCard className="space-y-2.5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">지금 기억하는 내 취향</h3>
            {memoryLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400" />}
          </div>
          {memory && memory.recent_recommended_product_codes.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {memory.recent_recommended_product_codes.map(code => (
                <button
                  key={code}
                  type="button"
                  onClick={() => setDetailCode(code)}
                  title="상세 보기"
                  className="text-xs px-2 py-0.5 rounded-md bg-white/[0.05] text-slate-300 border border-white/10 hover:border-accent/40 hover:text-accent-light"
                >
                  {code}
                </button>
              ))}
            </div>
          )}
          {memory && memory.pending_recommendation_outcomes.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-slate-500">
                추천 후 반응 확인 중 ({memory.pending_recommendation_outcomes.length}개) — 실제로 보시면 자동으로 취향에 반영돼요
              </p>
              <div className="flex flex-wrap gap-1.5">
                {memory.pending_recommendation_outcomes.map(outcome => (
                  <button
                    key={outcome.product_code}
                    type="button"
                    onClick={() => setDetailCode(outcome.product_code)}
                    title={`추천 시점: ${formatRelativeTime(outcome.recommended_at)}`}
                    className="text-xs px-2 py-0.5 rounded-md bg-white/[0.03] text-slate-500 border border-dashed border-white/10 hover:border-accent/40 hover:text-accent-light"
                  >
                    {outcome.product_code}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="space-y-1.5 max-h-56 overflow-y-auto app-scroll pr-1">
            {memory &&
              MEMORY_NOTE_GROUPS.flatMap(group =>
                memory[group.key].map((note, index) => {
                  const isImplicit = note.source === "implicit_watch" || note.source === "post_rec_rating";
                  return (
                    <div
                      key={`${group.category}-${index}`}
                      className="flex items-start gap-2 text-sm text-[#d0d0e8] bg-white/[0.03] border border-white/[0.06] rounded-lg px-2.5 py-1.5"
                    >
                      <span className="shrink-0 text-xs px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-400">
                        {group.label}
                      </span>
                      <span className="flex-1 leading-relaxed">
                        {note.text}
                        {isImplicit && (
                          <span
                            title="채팅에서 추천한 작품의 실제 시청/평점을 보고 자동으로 기록됨"
                            className="inline-flex items-center gap-0.5 ml-1.5 text-[10px] text-accent-light/80 align-middle"
                          >
                            <Eye className="w-3 h-3" />
                            자동 감지
                          </span>
                        )}
                      </span>
                      <button
                        type="button"
                        onClick={() => void handleRemoveMemoryNote(group.category, index)}
                        title="이 기억 삭제"
                        className="shrink-0 text-slate-500 hover:text-rose-300 p-0.5"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                }),
              )}
            {memory && MEMORY_NOTE_GROUPS.every(group => memory[group.key].length === 0) && (
              <p className="text-sm text-muted-foreground">아직 저장된 대화 기억이 없습니다.</p>
            )}
          </div>
        </GlassCard>
      )}

      <div className="flex-1 min-h-0 flex gap-4">
        <GlassCard className="w-60 shrink-0 flex flex-col" noPadding>
          <div className="p-3 border-b border-white/[0.06]">
            <button
              type="button"
              onClick={() => void handleNewConversation()}
              disabled={streaming}
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-xl border border-white/10 text-sm text-slate-300 hover:bg-white/[0.04] disabled:opacity-40"
            >
              <MessageSquarePlus className="w-4 h-4" />
              새 대화 시작
            </button>
            {sessions.length > 4 && (
              <div className="relative mt-2">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
                <input
                  value={sessionSearch}
                  onChange={e => setSessionSearch(e.target.value)}
                  placeholder="대화 검색"
                  className="w-full rounded-lg bg-bg-surface border border-white/[0.08] pl-8 pr-2.5 py-1.5 text-sm text-[#e2e2f0] placeholder:text-slate-500 focus:outline-none focus:border-accent/50"
                />
              </div>
            )}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto app-scroll p-2 space-y-1">
            {sessionSearch.trim() && filteredSessions.length === 0 && (
              <p className="text-xs text-slate-500 text-center py-3">검색 결과가 없습니다</p>
            )}
            {filteredSessions.map(s => {
              const isRenaming = renamingSessionId === s.id;
              return (
                <div
                  key={s.id}
                  onClick={() => !isRenaming && void handleSelectSession(s.id)}
                  className={cn(
                    "group flex items-center gap-1 rounded-xl px-2.5 py-2 text-sm",
                    isRenaming ? "cursor-default" : "cursor-pointer",
                    s.id === currentSessionId
                      ? "bg-accent/15 text-white border border-accent/25"
                      : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200 border border-transparent",
                    streaming && !isRenaming && "pointer-events-none opacity-60",
                  )}
                >
                  <div className="flex-1 min-w-0">
                    {isRenaming ? (
                      <input
                        autoFocus
                        value={renameDraft}
                        onChange={e => setRenameDraft(e.target.value)}
                        onClick={e => e.stopPropagation()}
                        onKeyDown={e => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void handleSaveRename(s.id);
                          } else if (e.key === "Escape") {
                            e.preventDefault();
                            handleCancelRename();
                          }
                        }}
                        onBlur={() => void handleSaveRename(s.id)}
                        disabled={renameSaving}
                        className="w-full rounded-lg bg-bg-surface border border-accent/40 px-1.5 py-0.5 text-sm text-white focus:outline-none disabled:opacity-50"
                      />
                    ) : (
                      <div className="truncate">{s.title}</div>
                    )}
                    <div className="text-xs text-slate-500">{formatRelativeTime(s.updated_at)}</div>
                  </div>
                  {isRenaming ? (
                    <button
                      type="button"
                      onClick={e => handleCancelRename(e)}
                      title="이름 변경 취소"
                      className="shrink-0 text-slate-500 hover:text-slate-300 p-1"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={e => handleStartRename(s, e)}
                        title="대화 이름 변경"
                        className="shrink-0 opacity-0 group-hover:opacity-100 text-slate-500 hover:text-slate-200 p-1"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={e => void handleDeleteSession(s.id, e)}
                        title="대화 삭제"
                        className="shrink-0 opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-300 p-1"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </GlassCard>

        <GlassCard className="flex-1 min-h-0 flex flex-col" noPadding>
          <div className="flex-1 min-h-0 overflow-y-auto app-scroll px-5 py-4 space-y-3">
            {!loadingSession && messages.length === 0 && (
              <p className="text-sm text-muted-foreground">
                취향이나 최근 본 작품을 말씀해 주시면 맞춰서 추천해 드릴게요.
              </p>
            )}
            {messages.map(m => {
              const tokenInfo = m.role === "assistant" ? formatTokenInfo(m) : null;
              const isWaiting = streaming && m.role === "assistant" && !m.content && !m.reasoning;
              const hasReasoning = m.role === "assistant" && !!m.reasoning;
              const isEditingThis = editingMessageId === m.id;
              const isEditableLastUserMessage = m.role === "user" && m.id === lastUserMessageId;
              return (
                <div
                  key={m.id}
                  className={cn("flex flex-col", m.role === "user" ? "items-end" : "items-start")}
                >
                  {hasReasoning && (
                    <div className="max-w-[80%] mb-1">
                      <button
                        type="button"
                        onClick={() => toggleThinking(m.id)}
                        className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 px-1 py-0.5"
                      >
                        {m.thinkingOpen ? (
                          <ChevronDown className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5" />
                        )}
                        Thinking
                        {streaming && !m.content && (
                          <Loader2 className="w-3 h-3 animate-spin ml-0.5" />
                        )}
                      </button>
                      {m.thinkingOpen && (
                        <div
                          data-selectable-text
                          className="mt-1 rounded-xl px-3 py-2 text-xs text-slate-400 italic whitespace-pre-wrap break-words bg-white/[0.03] border border-white/[0.06]"
                        >
                          {m.reasoning}
                        </div>
                      )}
                    </div>
                  )}
                  {isEditingThis ? (
                    <div className="max-w-[80%] w-full space-y-1.5">
                      <textarea
                        autoFocus
                        value={editDraft}
                        onChange={e => setEditDraft(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            void handleResendEditedMessage(m.id);
                          } else if (e.key === "Escape") {
                            e.preventDefault();
                            handleCancelEditMessage();
                          }
                        }}
                        rows={2}
                        className="w-full resize-none rounded-xl bg-indigo-500/10 border border-indigo-400/40 px-4 py-2.5 text-sm text-indigo-100 whitespace-pre-wrap focus:outline-none focus:ring-1 focus:ring-accent/40"
                      />
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={handleCancelEditMessage}
                          className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1"
                        >
                          취소
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleResendEditedMessage(m.id)}
                          disabled={!editDraft.trim()}
                          className="text-xs text-accent-light hover:text-white px-2 py-1 disabled:opacity-40"
                        >
                          수정 후 재전송
                        </button>
                      </div>
                    </div>
                  ) : (
                    (m.content || !hasReasoning) && (
                      <div className="group/bubble relative max-w-[80%]">
                        <div
                          data-selectable-text
                          className={cn(
                            "rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words",
                            m.role === "user"
                              ? "bg-indigo-500/20 text-indigo-100 border border-indigo-400/20"
                              : m.error
                                ? "bg-rose-500/10 text-rose-300 border border-rose-500/30"
                                : "bg-white/[0.05] text-[#e2e2f0] border border-white/[0.06]",
                          )}
                        >
                          {isWaiting ? (
                            serverState === "spawning" ? (
                              <span className="inline-flex items-center gap-2 text-amber-300/90">
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                모델을 VRAM에 불러오는 중… {(elapsedNowMs / 1000).toFixed(0)}s
                                <span className="text-slate-500">(처음 로딩은 오래 걸릴 수 있어요)</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-2 text-slate-400">
                                <span className="flex gap-1">
                                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]" />
                                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]" />
                                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" />
                                </span>
                                생각 중… {(elapsedNowMs / 1000).toFixed(0)}s
                              </span>
                            )
                          ) : (
                            renderMessageContent(m.content, setDetailCode)
                          )}
                        </div>
                        {isEditableLastUserMessage && !streaming && (
                          <button
                            type="button"
                            onClick={() => handleStartEditMessage(m)}
                            title="이 메시지 수정 후 재전송"
                            className="absolute -left-7 top-1/2 -translate-y-1/2 opacity-0 group-hover/bubble:opacity-100 text-slate-500 hover:text-slate-200 p-1"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    )
                  )}
                  {!!m.recommendations?.length && (
                    <div className="max-w-[80%] w-full flex gap-2 overflow-x-auto app-scroll pb-1 pt-1">
                      {m.recommendations.map(item => (
                        <RecommendationCard key={item.product_code} item={item} onOpen={setDetailCode} />
                      ))}
                    </div>
                  )}
                  {(tokenInfo || m.stopped || (m.role === "assistant" && m.content && !isWaiting)) && (
                    <span className="inline-flex items-center gap-2 text-xs text-slate-500 mt-1 px-1">
                      {[tokenInfo, m.stopped ? "중지됨" : null].filter(Boolean).join(" · ")}
                      {m.role === "assistant" && m.content && !isWaiting && !m.error && (
                        <CopyButton text={m.content} />
                      )}
                      {m.role === "assistant" && m.error && (
                        <button
                          type="button"
                          onClick={() => void handleRetry(m.id)}
                          disabled={streaming}
                          className="inline-flex items-center gap-1 text-slate-400 hover:text-accent-light disabled:opacity-40"
                        >
                          <RefreshCw className="w-3.5 h-3.5" />
                          다시 시도
                        </button>
                      )}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          <div className="border-t border-white/[0.06] p-3 space-y-2">
            {pendingFocusCode && (
              <div className="flex items-center gap-1.5 px-1">
                <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-md bg-accent/10 text-accent-light border border-accent/20">
                  {pendingFocusCode} 기준으로 답변
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setFocusProductCode(null);
                    setDetailCode(null);
                  }}
                  title="이 작품 컨텍스트 해제"
                  className="text-slate-500 hover:text-slate-300"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={streaming || loadingSession}
                rows={2}
                placeholder="메시지를 입력하세요 (Enter로 전송, Shift+Enter로 줄바꿈)"
                className="flex-1 resize-none rounded-xl bg-bg-surface border border-white/[0.08] px-3 py-2 text-sm text-[#e2e2f0] placeholder:text-slate-500 focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 disabled:opacity-50"
              />
              {streaming ? (
                <button
                  type="button"
                  onClick={handleStop}
                  title="생성 중지"
                  className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-rose-500/20 border border-rose-400/30 text-rose-300 hover:bg-rose-500/30"
                >
                  <Square className="w-4 h-4" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void handleSend()}
                  disabled={!input.trim() || loadingSession}
                  className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-accent/20 border border-accent/30 text-accent-light hover:bg-accent/30 disabled:opacity-40 disabled:pointer-events-none"
                >
                  <Send className="w-4 h-4" />
                </button>
              )}
            </div>
            <div className="flex items-center justify-between px-1 text-xs text-slate-500 min-h-[1rem]">
              <span>
                {streaming && (
                  <span className="inline-flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {serverState === "spawning"
                      ? `모델 로딩 중… ${(elapsedNowMs / 1000).toFixed(1)}s`
                      : `생성 중… ${(elapsedNowMs / 1000).toFixed(1)}s`}
                  </span>
                )}
              </span>
              {!streaming && lastTokenInfo && <span>마지막 응답: {lastTokenInfo}</span>}
            </div>
          </div>
        </GlassCard>
      </div>
      {detailCode && (
        <LibraryDetailPanel
          code={detailCode}
          onClose={() => setDetailCode(null)}
          onPlay={() => openPlayer(detailCode)}
        />
      )}
    </div>
  );
}
