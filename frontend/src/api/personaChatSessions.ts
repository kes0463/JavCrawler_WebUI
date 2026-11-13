import { del, get, patch, post } from "./client";

export interface PersonaChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface PersonaChatSessionMessage {
  role: "user" | "assistant";
  content: string;
  reasoning?: string;
  ts?: string;
}

export interface PersonaChatSessionDetail extends PersonaChatSessionSummary {
  messages: PersonaChatSessionMessage[];
}

export const fetchPersonaChatSessions = (): Promise<{ sessions: PersonaChatSessionSummary[] }> =>
  get("/api/persona-chat/sessions");

export const createPersonaChatSession = (): Promise<PersonaChatSessionDetail> =>
  post("/api/persona-chat/sessions");

export const fetchPersonaChatSession = (id: string): Promise<PersonaChatSessionDetail> =>
  get(`/api/persona-chat/sessions/${encodeURIComponent(id)}`);

export const renamePersonaChatSession = (
  id: string,
  title: string,
): Promise<PersonaChatSessionSummary> =>
  patch(`/api/persona-chat/sessions/${encodeURIComponent(id)}`, { title });

export const deletePersonaChatSession = (id: string): Promise<{ deleted: boolean }> =>
  del(`/api/persona-chat/sessions/${encodeURIComponent(id)}`);

/** 저장된 메시지를 앞에서부터 keepCount개만 남기고 자른다 — 마지막 메시지 수정 후 재전송 전에 호출. */
export const truncatePersonaChatSession = (
  id: string,
  keepCount: number,
): Promise<PersonaChatSessionDetail> =>
  post(`/api/persona-chat/sessions/${encodeURIComponent(id)}/truncate`, { keep_count: keepCount });
