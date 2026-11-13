import { postStream } from "./client";

export interface PersonaChatHistoryTurn {
  role: "user" | "assistant";
  content: string;
}

export interface PersonaChatUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

/** javstory/persona/persona_chat.py의 _structured_recommendation_items()와 동일한 형태. */
export interface PersonaChatRecommendationItem {
  product_code: string;
  title: string;
  actors: string[];
  genres: string[];
  persona_match_score: number;
  ranking_reasons: string[];
  matched_persona_terms: string[];
  matched_genre_terms: string[];
  matched_query_terms: string[];
  matched_seed_title: string;
}

export type PersonaChatStreamEvent =
  | { type: "token"; text: string }
  | { type: "reasoning"; text: string }
  | { type: "recommendations"; items: PersonaChatRecommendationItem[] }
  | {
      type: "done";
      text: string;
      usage?: PersonaChatUsage | null;
      elapsed_sec?: number | null;
      tokens_per_sec?: number | null;
    }
  | { type: "error"; message: string };

export async function* streamPersonaChat(
  message: string,
  history: PersonaChatHistoryTurn[],
  sessionId: string | null,
  productCode?: string,
  signal?: AbortSignal,
): AsyncGenerator<PersonaChatStreamEvent> {
  for await (const raw of postStream(
    "/api/persona-chat/message",
    { message, history, product_code: productCode ?? null, session_id: sessionId },
    signal,
  )) {
    if (raw === "[DONE]") return;
    try {
      yield JSON.parse(raw) as PersonaChatStreamEvent;
    } catch {
      // 파싱 실패 프레임은 무시
    }
  }
}
