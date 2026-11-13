import { del, get } from "./client";

/** javstory/persona/persona_memory.py의 EnhancedPersonaMemory 노트 카테고리. */
export type PersonaChatMemoryCategory =
  | "preference"
  | "strong_reaction"
  | "negative_feedback"
  | "correction"
  | "style";

/** javstory/persona/recommendation_feedback.py가 붙이는 값 — 사용자가 직접 말한 게 아니라
 * 추천 후 실제 시청/평점을 보고 자동으로 기록됐다는 표시. */
export type PersonaChatMemoryNoteSource = "implicit_watch" | "post_rec_rating";

export interface PersonaChatMemoryNote {
  text: string;
  created_at?: string;
  triggers?: string[];
  product_codes?: string[];
  intensity?: number;
  source?: PersonaChatMemoryNoteSource;
  [key: string]: unknown;
}

/** 추천은 했지만 아직 시청/평점으로 반응이 확인되지 않은 품번. */
export interface PersonaChatPendingRecommendationOutcome {
  product_code: string;
  recommended_at: string;
}

export interface PersonaChatMemorySnapshot {
  turn_count: number;
  preference_notes: PersonaChatMemoryNote[];
  strong_reaction_notes: PersonaChatMemoryNote[];
  negative_feedback_notes: PersonaChatMemoryNote[];
  correction_notes: PersonaChatMemoryNote[];
  style_notes: PersonaChatMemoryNote[];
  recent_recommended_product_codes: string[];
  pending_recommendation_outcomes: PersonaChatPendingRecommendationOutcome[];
}

export const fetchPersonaChatMemory = (): Promise<PersonaChatMemorySnapshot> =>
  get("/api/persona-chat/memory");

export const removePersonaChatMemoryNote = (
  category: PersonaChatMemoryCategory,
  index: number,
): Promise<PersonaChatMemorySnapshot> =>
  del(`/api/persona-chat/memory/${category}/${index}`);
