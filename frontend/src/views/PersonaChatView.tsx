import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy, Loader2, MessageSquarePlus, Send, Square, Trash2 } from "lucide-react";
import { fetchLlamaCppStatus, type LlamaCppState } from "@/api/llamacpp";
import { streamPersonaChat, type PersonaChatHistoryTurn, type PersonaChatUsage } from "@/api/personaChat";
import {
  createPersonaChatSession,
  deletePersonaChatSession,
  fetchPersonaChatSession,
  fetchPersonaChatSessions,
  type PersonaChatSessionSummary,
} from "@/api/personaChatSessions";
import { ModelPickerDropdown } from "@/components/llamacpp/ModelPickerDropdown";
import { GlassCard } from "@/components/ui/GlassCard";
import { LibraryDetailPanel } from "@/components/library/LibraryDetailPanel";
import { useLlamaCppModelPicker } from "@/hooks/useLlamaCppModelPicker";
import { usePlayer } from "@/contexts/PlayerContext";
import { useToast } from "@/contexts/ToastContext";
import { cn } from "@/lib/utils";

// javstory/persona/library_search.py의 _PRODUCT_CODE_RE와 동일한 취지(영문 접두 + 숫자).
const PRODUCT_CODE_RE = /(?<![A-Za-z0-9])([A-Za-z]{1,8})[-_\s]?(\d{2,7})(?![A-Za-z0-9])/g;

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

let _nextId = 0;

export default function PersonaChatView() {
  const { showToast } = useToast();
  const { openPlayer } = usePlayer();
  const [detailCode, setDetailCode] = useState<string | null>(null);
  const picker = useLlamaCppModelPicker("persona_chat");
  const [sessions, setSessions] = useState<PersonaChatSessionSummary[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [elapsedNowMs, setElapsedNowMs] = useState(0);
  const [serverState, setServerState] = useState<LlamaCppState | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sendStartedAtRef = useRef(0);

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

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const toggleThinking = useCallback((id: number) => {
    setMessages(prev =>
      prev.map(m => (m.id === id ? { ...m, thinkingOpen: !m.thinkingOpen } : m)),
    );
  }, []);

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

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let completed = false;
    try {
      for await (const event of streamPersonaChat(text, history, currentSessionId, undefined, ctrl.signal)) {
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
      if (completed) void refreshSessions();
    }
  }, [input, messages, streaming, currentSessionId, showToast, refreshSessions]);

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
        <ModelPickerDropdown picker={picker} />
      </div>

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
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto app-scroll p-2 space-y-1">
            {sessions.map(s => (
              <div
                key={s.id}
                onClick={() => void handleSelectSession(s.id)}
                className={cn(
                  "group flex items-center gap-1 rounded-xl px-2.5 py-2 cursor-pointer text-sm",
                  s.id === currentSessionId
                    ? "bg-accent/15 text-white border border-accent/25"
                    : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200 border border-transparent",
                  streaming && "pointer-events-none opacity-60",
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="truncate">{s.title}</div>
                  <div className="text-xs text-slate-500">{formatRelativeTime(s.updated_at)}</div>
                </div>
                <button
                  type="button"
                  onClick={e => void handleDeleteSession(s.id, e)}
                  title="대화 삭제"
                  className="shrink-0 opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-300 p-1"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
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
                  {(m.content || !hasReasoning) && (
                    <div
                      data-selectable-text
                      className={cn(
                        "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words",
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
                  )}
                  {(tokenInfo || m.stopped || (m.role === "assistant" && m.content && !isWaiting)) && (
                    <span className="inline-flex items-center gap-2 text-xs text-slate-500 mt-1 px-1">
                      {[tokenInfo, m.stopped ? "중지됨" : null].filter(Boolean).join(" · ")}
                      {m.role === "assistant" && m.content && !isWaiting && <CopyButton text={m.content} />}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          <div className="border-t border-white/[0.06] p-3 space-y-2">
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
