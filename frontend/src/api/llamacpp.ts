import { get, post } from "./client";

export type LlamaCppFeature = "insight" | "persona_chat";

export interface LlamaCppModelOption {
  id: string;
  label: string;
}

export interface LlamaCppModelsResponse {
  models: LlamaCppModelOption[];
  insight_active_preset_id: string;
  persona_chat_active_preset_id: string;
}

export type LlamaCppState = "stopped" | "spawning" | "ready" | "busy";

export interface LlamaCppStatus {
  state: LlamaCppState;
  active_preset_id: string | null;
  active_label: string | null;
  base_url: string;
  active_requests: number;
  persona_chat_managed: boolean;
}

export interface LlamaCppSelectResult {
  accepted: boolean;
  already_active: boolean;
}

export const fetchLlamaCppModels = (): Promise<LlamaCppModelsResponse> =>
  get("/api/llamacpp/models");

export const fetchLlamaCppStatus = (): Promise<LlamaCppStatus> =>
  get("/api/llamacpp/status");

export const selectLlamaCppModel = (
  feature: LlamaCppFeature,
  presetId: string,
): Promise<LlamaCppSelectResult> =>
  post("/api/llamacpp/select", { feature, preset_id: presetId });
