import { get, patch } from "./client";

export interface SttEngineOption {
  id: string;
  label: string;
  description: string;
  implemented: boolean;
}

export interface SttFwXxlOptions {
  language: string;
  vad_filter: boolean;
  vad_threshold: number;
  vad_min_speech_duration_ms: number;
  vad_max_speech_duration_s: number;
  condition_on_previous_text: boolean;
  no_speech_threshold: number;
  beam_size: number;
  best_of: number;
  temperature: number;
  temperature_increment_on_fallback: number;
  hallucination_silence_threshold: number;
  compute_type: string;
  batch_size: number;
  word_timestamps: boolean;
  repetition_penalty: number;
  log_prob_threshold: number;
  compression_ratio_threshold: number;
}

export interface FasterWhisperModelOption {
  id: string;
  label: string;
}

export interface SttSettings {
  engine: string;
  whisper_model: string;
  faster_whisper_model: string;
  hf_whisper_model: string;
  vad_threshold: number;
  dialogue_only: boolean;
  fw_xxl: SttFwXxlOptions;
  engine_options: SttEngineOption[];
  faster_whisper_model_options?: FasterWhisperModelOption[];
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
    | "fw_xxl"
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

export interface OmniRouteSettings {
  url: string;
  model: string;
}

export interface TranslationChunkOption {
  chunk_target_lines: number;
  chunk_overlap_lines: number;
  context_length: number | null;
}

export type TranslationChunkProvider =
  | "llamacpp"
  | "ollama"
  | "openrouter"
  | "omniroute"
  | "gemini";

export interface GeminiModelOption {
  id: string;
  label: string;
  rpm: number | null;
  tpm: number | null;
  rpd: number | null;
  is_pro: boolean;
}

export interface GeminiSettings {
  model: string;
  chain: string[];
  has_api_key: boolean;
  model_options: GeminiModelOption[];
}

export interface TranslationSettings {
  provider: string;
  openrouter_profile: string;
  llamacpp: LlamaCppSettings;
  omniroute: OmniRouteSettings;
  gemini: GeminiSettings;
  chunk_options: Record<TranslationChunkProvider, TranslationChunkOption>;
  provider_options: TranslationProviderOption[];
  model_options: TranslationModelOption[];
  openrouter_profile_options: OpenRouterProfileOption[];
}

export type TranslationSettingsPatch = Partial<{
  provider: string;
  openrouter_profile: string;
  omniroute_url: string;
  omniroute_model: string;
  gemini_chain: string[];
  gemini_chunk_target_lines: number;
  gemini_chunk_overlap_lines: number;
  llamacpp_chunk_target_lines: number;
  llamacpp_chunk_overlap_lines: number;
  ollama_chunk_target_lines: number;
  ollama_chunk_overlap_lines: number;
  ollama_context_length: number;
  openrouter_chunk_target_lines: number;
  openrouter_chunk_overlap_lines: number;
  omniroute_chunk_target_lines: number;
  omniroute_chunk_overlap_lines: number;
  omniroute_context_length: number;
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

export interface EmbeddingsGgufOption {
  id: string;
  label: string;
  gguf_path: string;
  gguf_env?: string;
}

export interface EmbeddingsSettings {
  enabled: boolean;
  backend: "llamacpp" | "ollama" | string;
  model: string;
  gguf_path?: string;
  gguf_scan_dir?: string;
  gguf_options?: EmbeddingsGgufOption[];
  embedded_count: number;
  library_total: number;
  missing_count: number;
  pending_count?: number;
  backfill_running?: boolean;
  coverage_pct: number;
  search_min_score?: number;
  search_relative_ratio?: number;
  search_max_gap?: number;
  batch_size?: number;
}

export type EmbeddingsSettingsPatch = Partial<{
  enabled: boolean;
  backend: string;
  model: string;
  gguf_path: string;
  search_min_score: number;
  search_relative_ratio: number;
  search_max_gap: number;
  batch_size: number;
}>;

export interface EmbeddingsGgufOptions {
  gguf_scan_dir?: string;
  gguf_options?: EmbeddingsGgufOption[];
}

export const fetchEmbeddingsSettings = (): Promise<EmbeddingsSettings> =>
  get("/api/settings/embeddings", 45_000);

export const fetchEmbeddingsGgufOptions = (): Promise<EmbeddingsGgufOptions> =>
  get("/api/settings/embeddings/gguf-options", 20_000);

export const patchEmbeddingsSettings = (
  body: EmbeddingsSettingsPatch,
): Promise<EmbeddingsSettings> => patch("/api/settings/embeddings", body);

export interface HarvestSettings {
  harvest_concurrency: number;
  embeddings_pause_during_harvest: boolean;
  harvest_llamacpp_slot_ctx: number | null;
  llamacpp_spawn_diagnostics: Record<string, unknown>;
  tuning_hints: string[];
}

export type HarvestSettingsPatch = Partial<{
  harvest_concurrency: number;
  embeddings_pause_during_harvest: boolean;
  harvest_llamacpp_slot_ctx: number | null;
}>;

export const fetchHarvestSettings = (): Promise<HarvestSettings> =>
  get("/api/settings/harvest");

export const patchHarvestSettings = (
  body: HarvestSettingsPatch,
): Promise<HarvestSettings> => patch("/api/settings/harvest", body);
