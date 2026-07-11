import { get, patch } from "./client";

export interface SttEngineOption {
  id: string;
  label: string;
  description: string;
  implemented: boolean;
}

export interface SttSettings {
  engine: string;
  whisper_model: string;
  faster_whisper_model: string;
  hf_whisper_model: string;
  vad_threshold: number;
  dialogue_only: boolean;
  engine_options: SttEngineOption[];
}

export type SttSettingsPatch = Partial<
  Pick<
    SttSettings,
    | "engine"
    | "whisper_model"
    | "faster_whisper_model"
    | "hf_whisper_model"
    | "vad_threshold"
    | "dialogue_only"
  >
>;

export const fetchSttSettings = (): Promise<SttSettings> =>
  get("/api/settings/stt");

export const patchSttSettings = (body: SttSettingsPatch): Promise<SttSettings> =>
  patch("/api/settings/stt", body);

export interface TranslationModelOption {
  id: string;
  label: string;
  gguf_env: string;
  gguf_path: string;
}

export interface TranslationProviderOption {
  id: string;
  label: string;
}

export interface OpenRouterProfileOption {
  id: string;
  label: string;
}

export interface LlamaCppSettings {
  bin: string;
  url: string;
  port: number;
  model: string;
  gguf_path: string;
  gguf_env: string;
  gguf_scan_dir: string;
  ctx: number;
  n_gpu_layers: number | null;
  cache_type_k: string;
  cache_type_v: string;
  threads: number | null;
  tensorcores: boolean;
  flash_attn: boolean;
  auto_start: boolean;
  fit_vram: boolean;
  command_preview: string;
}

export interface TranslationSettings {
  provider: string;
  openrouter_profile: string;
  llamacpp: LlamaCppSettings;
  provider_options: TranslationProviderOption[];
  model_options: TranslationModelOption[];
  openrouter_profile_options: OpenRouterProfileOption[];
}

export type TranslationSettingsPatch = Partial<{
  provider: string;
  openrouter_profile: string;
  llamacpp_bin: string;
  llamacpp_url: string;
  llamacpp_port: number;
  llamacpp_model: string;
  llamacpp_gguf_path: string;
  llamacpp_ctx: number;
  llamacpp_n_gpu_layers: number | null;
  llamacpp_cache_type_k: string;
  llamacpp_cache_type_v: string;
  llamacpp_threads: number | null;
  llamacpp_tensorcores: boolean;
  llamacpp_flash_attn: boolean;
  llamacpp_auto_start: boolean;
  llamacpp_fit_vram: boolean;
}>;

export const fetchTranslationSettings = (): Promise<TranslationSettings> =>
  get("/api/settings/translation");

export const patchTranslationSettings = (
  body: TranslationSettingsPatch,
): Promise<TranslationSettings> => patch("/api/settings/translation", body);

export interface TranslationPromptSettings {
  prompt_mode: string;
  prompt_variant: string;
  system_prompt_template: string;
  uses_custom_template: boolean;
  global_note: string;
  builtin_templates: Record<string, string>;
  prompt_mode_options: { id: string; label: string }[];
  prompt_variant_options: { id: string; label: string }[];
  user_message_format: string;
  placeholders: { note: string; slot: string };
}

export type TranslationPromptSettingsPatch = Partial<{
  prompt_mode: string;
  prompt_variant: string;
  system_prompt_template: string;
  global_note: string;
  reset_system_prompt: boolean;
}>;

export const fetchTranslationPromptSettings = (): Promise<TranslationPromptSettings> =>
  get("/api/settings/translation-prompt");

export const patchTranslationPromptSettings = (
  body: TranslationPromptSettingsPatch,
): Promise<TranslationPromptSettings> => patch("/api/settings/translation-prompt", body);

export interface EmbeddingsSettings {
  enabled: boolean;
  model: string;
  embedded_count: number;
  library_total: number;
  missing_count: number;
  pending_count?: number;
  backfill_running?: boolean;
  coverage_pct: number;
}

export type EmbeddingsSettingsPatch = Partial<{
  enabled: boolean;
  model: string;
}>;

export const fetchEmbeddingsSettings = (): Promise<EmbeddingsSettings> =>
  get("/api/settings/embeddings");

export const patchEmbeddingsSettings = (
  body: EmbeddingsSettingsPatch,
): Promise<EmbeddingsSettings> => patch("/api/settings/embeddings", body);
