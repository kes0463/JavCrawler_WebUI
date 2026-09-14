import { useCallback, useEffect, useState } from "react";
import { Save, RotateCcw, HardDrive, Cpu, Globe, Shield, Mic2, Loader2, Languages, FileText, Sparkles, Film, Trash2, Wheat, Plus, ChevronUp, ChevronDown } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { ActionButton } from "@/components/ui/ActionButton";
import {
  SettingsSection, SettingsRow,
  TextInput, SecretInput, SelectInput, Toggle, TextArea,
} from "@/components/ui/SettingsControls";
import {
  fetchSttSettings,
  patchSttSettings,
  fetchTranslationSettings,
  patchTranslationSettings,
  fetchTranslationPromptSettings,
  patchTranslationPromptSettings,
  fetchEmbeddingsSettings,
  fetchEmbeddingsGgufOptions,
  patchEmbeddingsSettings,
  fetchHarvestSettings,
  patchHarvestSettings,
  type SttFwXxlOptions,
  type SttSettings,
  type TranslationSettings,
  type TranslationPromptSettings,
  type EmbeddingsSettings,
  type EmbeddingsGgufOption,
  type HarvestSettings,
} from "@/api/settings";
import { warmupLibraryEmbeddings, backfillLibraryEmbeddings } from "@/api/library";
import {
  fetchProxyCacheStats,
  clearProxyCache,
  type ProxyCacheStats,
} from "@/api/playback";
import { useToast } from "@/contexts/ToastContext";

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

const WHISPER_MODEL_OPTIONS = [
  { label: "large-v2 (기본)", value: "large-v2" },
  { label: "large-v3", value: "large-v3" },
  { label: "medium", value: "medium" },
  { label: "small", value: "small" },
  { label: "turbo", value: "turbo" },
];

const FASTER_WHISPER_MODEL_OPTIONS = [
  { label: "kotoba-v2.0-faster (기본)", value: "kotoba-tech/kotoba-whisper-v2.0-faster" },
  { label: "Medium", value: "medium" },
  { label: "large-v2", value: "large-v2" },
  { label: "large-v3", value: "large-v3" },
  { label: "large-v3-turbo", value: "large-v3-turbo" },
];

const DEFAULT_FW_XXL: SttFwXxlOptions = {
  language: "ja",
  vad_filter: true,
  vad_threshold: 0.6,
  vad_min_speech_duration_ms: 400,
  vad_max_speech_duration_s: 18,
  condition_on_previous_text: false,
  no_speech_threshold: 0.6,
  beam_size: 7,
  best_of: 5,
  temperature: 0,
  temperature_increment_on_fallback: 0.2,
  hallucination_silence_threshold: 1.5,
  compute_type: "float16",
  batch_size: 8,
  word_timestamps: false,
  repetition_penalty: 1.2,
  log_prob_threshold: -1.0,
  compression_ratio_threshold: 2.4,
};

type FwXxlDraft = {
  language: string;
  vad_filter: boolean;
  vad_threshold: string;
  vad_min_speech_duration_ms: string;
  vad_max_speech_duration_s: string;
  condition_on_previous_text: boolean;
  no_speech_threshold: string;
  beam_size: string;
  best_of: string;
  temperature: string;
  temperature_increment_on_fallback: string;
  hallucination_silence_threshold: string;
  compute_type: string;
  batch_size: string;
  word_timestamps: boolean;
  repetition_penalty: string;
  log_prob_threshold: string;
  compression_ratio_threshold: string;
};

function fwXxlToDraft(o: SttFwXxlOptions): FwXxlDraft {
  const m = { ...DEFAULT_FW_XXL, ...o };
  return {
    language: m.language,
    vad_filter: m.vad_filter,
    vad_threshold: String(m.vad_threshold),
    vad_min_speech_duration_ms: String(m.vad_min_speech_duration_ms),
    vad_max_speech_duration_s: String(m.vad_max_speech_duration_s),
    condition_on_previous_text: m.condition_on_previous_text,
    no_speech_threshold: String(m.no_speech_threshold),
    beam_size: String(m.beam_size),
    best_of: String(m.best_of),
    temperature: String(m.temperature),
    temperature_increment_on_fallback: String(m.temperature_increment_on_fallback),
    hallucination_silence_threshold: String(m.hallucination_silence_threshold),
    compute_type: m.compute_type,
    batch_size: String(m.batch_size),
    word_timestamps: m.word_timestamps,
    repetition_penalty: String(m.repetition_penalty),
    log_prob_threshold: String(m.log_prob_threshold),
    compression_ratio_threshold: String(m.compression_ratio_threshold),
  };
}

function parseFwXxlDraft(d: FwXxlDraft): SttFwXxlOptions | null {
  const num = (s: string) => parseFloat(s);
  const int = (s: string) => parseInt(s, 10);
  const vad = num(d.vad_threshold);
  const noSpeech = num(d.no_speech_threshold);
  const beam = int(d.beam_size);
  const bestOf = int(d.best_of);
  const temp = num(d.temperature);
  const tempInc = num(d.temperature_increment_on_fallback);
  const hallu = num(d.hallucination_silence_threshold);
  const batch = int(d.batch_size);
  const minSpeech = int(d.vad_min_speech_duration_ms);
  const maxSpeech = int(d.vad_max_speech_duration_s);
  const rep = num(d.repetition_penalty);
  const logProb = num(d.log_prob_threshold);
  const compRatio = num(d.compression_ratio_threshold);
  if ([vad, noSpeech, temp, tempInc, hallu, rep, logProb, compRatio].some(Number.isNaN)) return null;
  if ([beam, bestOf, batch, minSpeech, maxSpeech].some(Number.isNaN)) return null;
  if (vad < 0.05 || vad > 0.95) return null;
  return {
    language: (d.language || "ja").trim() || "ja",
    vad_filter: d.vad_filter,
    vad_threshold: vad,
    vad_min_speech_duration_ms: minSpeech,
    vad_max_speech_duration_s: maxSpeech,
    condition_on_previous_text: d.condition_on_previous_text,
    no_speech_threshold: noSpeech,
    beam_size: beam,
    best_of: bestOf,
    temperature: temp,
    temperature_increment_on_fallback: tempInc,
    hallucination_silence_threshold: hallu,
    compute_type: (d.compute_type || "float16").trim() || "float16",
    batch_size: batch,
    word_timestamps: d.word_timestamps,
    repetition_penalty: rep,
    log_prob_threshold: logProb,
    compression_ratio_threshold: compRatio,
  };
}

export default function SettingsView() {
  const { showToast } = useToast();
  const [apiKey, setApiKey] = useState("");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [outputDir, setOutputDir] = useState("D:\\JAVSTORY\\output");
  const [cacheDir, setCacheDir] = useState("D:\\JAVSTORY\\cache");
  const [concurrentTasks, setConcurrentTasks] = useState("2");
  const [autoScrape, setAutoScrape] = useState(true);
  const [darkMode, setDarkMode] = useState(true);

  const [sttLoading, setSttLoading] = useState(true);
  const [sttSaving, setSttSaving] = useState(false);
  const [stt, setStt] = useState<SttSettings | null>(null);
  const [sttDraft, setSttDraft] = useState({
    engine: "stable_ts",
    whisper_model: "large-v2",
    faster_whisper_model: "kotoba-tech/kotoba-whisper-v2.0-faster",
    hf_whisper_model: "litagin/anime-whisper",
    vad_threshold: "0.35",
    dialogue_only: true,
    fw_xxl: fwXxlToDraft(DEFAULT_FW_XXL),
  });

  const loadStt = useCallback(async () => {
    setSttLoading(true);
    try {
      const snap = await fetchSttSettings();
      setStt(snap);
      setSttDraft({
        engine: snap.engine,
        whisper_model: snap.whisper_model,
        faster_whisper_model: snap.faster_whisper_model,
        hf_whisper_model: snap.hf_whisper_model,
        vad_threshold: String(snap.vad_threshold),
        dialogue_only: snap.dialogue_only,
        fw_xxl: fwXxlToDraft(snap.fw_xxl ?? DEFAULT_FW_XXL),
      });
    } catch (e) {
      showToast(e instanceof Error ? e.message : "STT 설정 불러오기 실패", "error");
    } finally {
      setSttLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadStt();
  }, [loadStt]);

  const handleSaveStt = async () => {
    setSttSaving(true);
    try {
      const vad = parseFloat(sttDraft.vad_threshold);
      if (Number.isNaN(vad) || vad < 0.05 || vad > 0.95) {
        showToast("VAD 임계값은 0.05~0.95 사이여야 합니다", "error");
        return;
      }
      const patch: Parameters<typeof patchSttSettings>[0] = {
        engine: sttDraft.engine,
        whisper_model: sttDraft.whisper_model,
        faster_whisper_model: sttDraft.faster_whisper_model,
        hf_whisper_model: sttDraft.hf_whisper_model,
        vad_threshold: vad,
        dialogue_only: sttDraft.dialogue_only,
      };
      if (sttDraft.engine === "stable_ts_fw") {
        const fw = parseFwXxlDraft(sttDraft.fw_xxl);
        if (!fw) {
          showToast("Faster-Whisper-XXL 옵션 값이 올바르지 않습니다", "error");
          return;
        }
        patch.fw_xxl = fw;
        patch.vad_threshold = fw.vad_threshold;
      }
      const snap = await patchSttSettings(patch);
      setStt(snap);
      setSttDraft({
        engine: snap.engine,
        whisper_model: snap.whisper_model,
        faster_whisper_model: snap.faster_whisper_model,
        hf_whisper_model: snap.hf_whisper_model,
        vad_threshold: String(snap.vad_threshold),
        dialogue_only: snap.dialogue_only,
        fw_xxl: fwXxlToDraft(snap.fw_xxl ?? DEFAULT_FW_XXL),
      });
      showToast("자막 전사 설정 저장됨", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "STT 설정 저장 실패", "error");
    } finally {
      setSttSaving(false);
    }
  };

  const handleResetStt = () => {
    if (!stt) return;
    setSttDraft({
      engine: stt.engine,
      whisper_model: stt.whisper_model,
      faster_whisper_model: stt.faster_whisper_model,
      hf_whisper_model: stt.hf_whisper_model,
      vad_threshold: String(stt.vad_threshold),
      dialogue_only: stt.dialogue_only,
      fw_xxl: fwXxlToDraft(stt.fw_xxl ?? DEFAULT_FW_XXL),
    });
  };

  const setFwXxl = <K extends keyof FwXxlDraft>(key: K, value: FwXxlDraft[K]) => {
    setSttDraft(d => ({ ...d, fw_xxl: { ...d.fw_xxl, [key]: value } }));
  };

  const handleResetFwXxlDefaults = () => {
    setSttDraft(d => ({
      ...d,
      fw_xxl: fwXxlToDraft(DEFAULT_FW_XXL),
      vad_threshold: String(DEFAULT_FW_XXL.vad_threshold),
    }));
    showToast("Faster-Whisper-XXL 옵션을 기본값으로 초기화했습니다 (저장 필요)", "info");
  };

  const engineOptions = (stt?.engine_options ?? [])
    .filter(o => o.implemented)
    .map(o => ({ label: o.label, value: o.id }));

  const selectedEngineHint = stt?.engine_options.find(o => o.id === sttDraft.engine)?.description;

  const [embLoading, setEmbLoading] = useState(true);
  const [embSaving, setEmbSaving] = useState(false);
  const [embWarming, setEmbWarming] = useState(false);
  const [emb, setEmb] = useState<EmbeddingsSettings | null>(null);
  const [ggufOptions, setGgufOptions] = useState<EmbeddingsGgufOption[]>([]);
  const [ggufScanDir, setGgufScanDir] = useState("");
  const [ggufOptionsLoading, setGgufOptionsLoading] = useState(true);
  const [embDraft, setEmbDraft] = useState({
    enabled: false,
    backend: "llamacpp",
    model: "nomic-embed-text",
    gguf_path: "",
    search_min_score: "0.36",
    search_relative_ratio: "0.84",
    search_max_gap: "0.10",
    batch_size: "10",
  });

  const loadGgufOptions = useCallback(async () => {
    setGgufOptionsLoading(true);
    try {
      const snap = await fetchEmbeddingsGgufOptions();
      setGgufOptions(snap.gguf_options ?? []);
      setGgufScanDir(snap.gguf_scan_dir ?? "");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "GGUF 목록 불러오기 실패", "error");
    } finally {
      setGgufOptionsLoading(false);
    }
  }, [showToast]);

  const loadEmb = useCallback(async () => {
    setEmbLoading(true);
    void loadGgufOptions();
    try {
      const snap = await fetchEmbeddingsSettings();
      setEmb(snap);
      if (snap.gguf_options?.length) {
        setGgufOptions(snap.gguf_options);
      }
      if (snap.gguf_scan_dir) {
        setGgufScanDir(snap.gguf_scan_dir);
      }
      let ggufPath = snap.gguf_path || "";
      if (!ggufPath && snap.model) {
        const modelKey = snap.model.trim().toLowerCase();
        const match = (snap.gguf_options ?? []).find(o => {
          const stem = o.label.replace(/\s*\(현재\)\s*$/, "").replace(/\.gguf$/i, "").toLowerCase();
          return stem === modelKey || stem.includes(modelKey) || modelKey.includes(stem);
        });
        if (match?.gguf_path) {
          ggufPath = match.gguf_path;
        }
      }
      setEmbDraft({
        enabled: snap.enabled,
        backend: snap.backend || "llamacpp",
        model: snap.model,
        gguf_path: ggufPath,
        search_min_score: String(snap.search_min_score ?? 0.36),
        search_relative_ratio: String(snap.search_relative_ratio ?? 0.84),
        search_max_gap: String(snap.search_max_gap ?? 0.1),
        batch_size: String(snap.batch_size ?? 10),
      });
    } catch (e) {
      showToast(e instanceof Error ? e.message : "임베딩 설정 불러오기 실패", "error");
    } finally {
      setEmbLoading(false);
    }
  }, [showToast, loadGgufOptions]);

  useEffect(() => {
    void loadEmb();
  }, [loadEmb]);

  const [harvestLoading, setHarvestLoading] = useState(true);
  const [harvestSaving, setHarvestSaving] = useState(false);
  const [harvest, setHarvest] = useState<HarvestSettings | null>(null);
  const [harvestDraft, setHarvestDraft] = useState({
    harvest_concurrency: "2",
    embeddings_pause_during_harvest: true,
    harvest_llamacpp_slot_ctx: "4096",
  });

  const loadHarvest = useCallback(async () => {
    setHarvestLoading(true);
    try {
      const snap = await fetchHarvestSettings();
      setHarvest(snap);
      setHarvestDraft({
        harvest_concurrency: String(snap.harvest_concurrency),
        embeddings_pause_during_harvest: snap.embeddings_pause_during_harvest,
        harvest_llamacpp_slot_ctx:
          snap.harvest_llamacpp_slot_ctx != null
            ? String(snap.harvest_llamacpp_slot_ctx)
            : "4096",
      });
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Harvest 설정 불러오기 실패", "error");
    } finally {
      setHarvestLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadHarvest();
  }, [loadHarvest]);

  const handleSaveHarvest = async () => {
    setHarvestSaving(true);
    try {
      const conc = parseInt(harvestDraft.harvest_concurrency, 10);
      if (!Number.isFinite(conc) || conc < 1 || conc > 5) {
        showToast("Harvest 동시 실행 수는 1~5 사이여야 합니다", "error");
        return;
      }
      const slotRaw = harvestDraft.harvest_llamacpp_slot_ctx.trim();
      const slotCtx = slotRaw ? parseInt(slotRaw, 10) : null;
      if (slotRaw && (!Number.isFinite(slotCtx!) || slotCtx! < 512)) {
        showToast("슬롯 ctx는 512 이상이어야 합니다", "error");
        return;
      }
      const snap = await patchHarvestSettings({
        harvest_concurrency: conc,
        embeddings_pause_during_harvest: harvestDraft.embeddings_pause_during_harvest,
        harvest_llamacpp_slot_ctx: slotCtx,
      });
      setHarvest(snap);
      setHarvestDraft({
        harvest_concurrency: String(snap.harvest_concurrency),
        embeddings_pause_during_harvest: snap.embeddings_pause_during_harvest,
        harvest_llamacpp_slot_ctx:
          snap.harvest_llamacpp_slot_ctx != null
            ? String(snap.harvest_llamacpp_slot_ctx)
            : "",
      });
      showToast("Harvest 성능 설정 저장됨 (llama-server 재시작 필요)", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Harvest 설정 저장 실패", "error");
    } finally {
      setHarvestSaving(false);
    }
  };

  const handleSaveEmb = async () => {
    setEmbSaving(true);
    try {
      const model = embDraft.model.trim();
      if (!model) {
        showToast("임베딩 모델 이름을 입력하세요", "error");
        return;
      }
      const minScore = Number(embDraft.search_min_score);
      const relRatio = Number(embDraft.search_relative_ratio);
      const maxGap = Number(embDraft.search_max_gap);
      if (!Number.isFinite(minScore) || minScore < 0.05 || minScore > 0.95) {
        showToast("최소 유사도는 0.05~0.95 사이여야 합니다", "error");
        return;
      }
      if (!Number.isFinite(relRatio) || relRatio < 0.05 || relRatio > 0.99) {
        showToast("상대 비율은 0.05~0.99 사이여야 합니다", "error");
        return;
      }
      if (!Number.isFinite(maxGap) || maxGap < 0.01 || maxGap > 0.5) {
        showToast("최대 격차는 0.01~0.5 사이여야 합니다", "error");
        return;
      }
      const batchSize = Number(embDraft.batch_size);
      if (!Number.isInteger(batchSize) || batchSize < 1 || batchSize > 64) {
        showToast("병렬 처리 개수는 1~64 사이 정수여야 합니다", "error");
        return;
      }
      const snap = await patchEmbeddingsSettings({
        enabled: embDraft.enabled,
        backend: embDraft.backend,
        model,
        gguf_path: embDraft.gguf_path.trim(),
        search_min_score: minScore,
        search_relative_ratio: relRatio,
        search_max_gap: maxGap,
        batch_size: batchSize,
      });
      setEmb(snap);
      setEmbDraft({
        enabled: snap.enabled,
        backend: snap.backend || "llamacpp",
        model: snap.model,
        gguf_path: snap.gguf_path || "",
        search_min_score: String(snap.search_min_score ?? 0.36),
        search_relative_ratio: String(snap.search_relative_ratio ?? 0.84),
        search_max_gap: String(snap.search_max_gap ?? 0.1),
        batch_size: String(snap.batch_size ?? 10),
      });
      showToast("임베딩 설정 저장됨", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "임베딩 설정 저장 실패", "error");
    } finally {
      setEmbSaving(false);
    }
  };

  const handleResetEmb = () => {
    if (!emb) return;
    setEmbDraft({
      enabled: emb.enabled,
      backend: emb.backend || "llamacpp",
      model: emb.model,
      gguf_path: emb.gguf_path || "",
      search_min_score: String(emb.search_min_score ?? 0.36),
      search_relative_ratio: String(emb.search_relative_ratio ?? 0.84),
      search_max_gap: String(emb.search_max_gap ?? 0.1),
      batch_size: String(emb.batch_size ?? 10),
    });
  };

  const handleWarmupEmbeddings = async () => {
    setEmbWarming(true);
    try {
      const res = await warmupLibraryEmbeddings(12);
      showToast(res.message, res.ok ? "success" : "warn");
      await loadEmb();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "임베딩 워밍업 실패", "error");
    } finally {
      setEmbWarming(false);
    }
  };

  const handleBackfillEmbeddings = async () => {
    setEmbWarming(true);
    try {
      const res = await backfillLibraryEmbeddings(4);
      showToast(res.message, res.ok ? "success" : "warn");
      await loadEmb();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "임베딩 백필 실패", "error");
    } finally {
      setEmbWarming(false);
    }
  };

  const [trLoading, setTrLoading] = useState(true);
  const [trSaving, setTrSaving] = useState(false);
  const [tr, setTr] = useState<TranslationSettings | null>(null);
  const [geminiApiKeyDraft, setGeminiApiKeyDraft] = useState("");
  const [trDraft, setTrDraft] = useState({
    provider: "llamacpp",
    openrouter_profile: "default",
    omniroute_url: "http://localhost:20128/v1",
    omniroute_model: "",
    omniroute_chunk_target_lines: "12",
    omniroute_chunk_overlap_lines: "3",
    omniroute_context_length: "32768",
    llamacpp_bin: "",
    llamacpp_url: "http://127.0.0.1:8080",
    llamacpp_port: "8080",
    llamacpp_model: "qwen2.5-14b",
    llamacpp_gguf_path: "",
    llamacpp_ctx: "16384",
    llamacpp_n_gpu_layers: "99",
    llamacpp_cache_type_k: "q8_0",
    llamacpp_cache_type_v: "q8_0",
    llamacpp_threads: "12",
    llamacpp_tensorcores: true,
    llamacpp_flash_attn: true,
    llamacpp_auto_start: true,
    llamacpp_fit_vram: false,
    llamacpp_chunk_target_lines: "12",
    llamacpp_chunk_overlap_lines: "3",
    ollama_chunk_target_lines: "12",
    ollama_chunk_overlap_lines: "3",
    ollama_context_length: "2048",
    openrouter_chunk_target_lines: "16",
    openrouter_chunk_overlap_lines: "4",
    gemini_chain: [
      "gemini-3.5-flash",
      "gemini-2.0-flash",
      "gemini-3.1-flash-lite",
      "gemini-2.5-flash-lite",
    ] as string[],
    gemini_chunk_target_lines: "16",
    gemini_chunk_overlap_lines: "4",
  });

  const applyTrSnap = useCallback((snap: TranslationSettings) => {
    const lc = snap.llamacpp;
    const co = snap.chunk_options;
    setTrDraft({
      provider: snap.provider,
      openrouter_profile: snap.openrouter_profile,
      omniroute_url: snap.omniroute.url,
      omniroute_model: snap.omniroute.model,
      omniroute_chunk_target_lines: String(co.omniroute.chunk_target_lines),
      omniroute_chunk_overlap_lines: String(co.omniroute.chunk_overlap_lines),
      omniroute_context_length: String(co.omniroute.context_length ?? 32768),
      llamacpp_bin: lc.bin === "llama-server.exe" ? "" : lc.bin,
      llamacpp_url: lc.url,
      llamacpp_port: String(lc.port),
      llamacpp_model: lc.model,
      llamacpp_gguf_path: lc.gguf_path,
      llamacpp_ctx: String(lc.ctx),
      llamacpp_n_gpu_layers: lc.n_gpu_layers != null ? String(lc.n_gpu_layers) : "",
      llamacpp_cache_type_k: lc.cache_type_k,
      llamacpp_cache_type_v: lc.cache_type_v,
      llamacpp_threads: lc.threads != null ? String(lc.threads) : "",
      llamacpp_tensorcores: lc.tensorcores,
      llamacpp_flash_attn: lc.flash_attn,
      llamacpp_auto_start: lc.auto_start,
      llamacpp_fit_vram: lc.fit_vram,
      llamacpp_chunk_target_lines: String(co.llamacpp.chunk_target_lines),
      llamacpp_chunk_overlap_lines: String(co.llamacpp.chunk_overlap_lines),
      ollama_chunk_target_lines: String(co.ollama.chunk_target_lines),
      ollama_chunk_overlap_lines: String(co.ollama.chunk_overlap_lines),
      ollama_context_length: String(co.ollama.context_length ?? 2048),
      openrouter_chunk_target_lines: String(co.openrouter.chunk_target_lines),
      openrouter_chunk_overlap_lines: String(co.openrouter.chunk_overlap_lines),
      gemini_chain: snap.gemini.chain.length ? snap.gemini.chain : [snap.gemini.model],
      gemini_chunk_target_lines: String(co.gemini.chunk_target_lines),
      gemini_chunk_overlap_lines: String(co.gemini.chunk_overlap_lines),
    });
  }, []);

  const loadTranslation = useCallback(async () => {
    setTrLoading(true);
    try {
      const snap = await fetchTranslationSettings();
      setTr(snap);
      applyTrSnap(snap);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "번역 설정 불러오기 실패", "error");
    } finally {
      setTrLoading(false);
    }
  }, [applyTrSnap, showToast]);

  useEffect(() => {
    void loadTranslation();
  }, [loadTranslation]);

  const handleSaveTranslation = async () => {
    setTrSaving(true);
    try {
      if (trDraft.provider === "omniroute" && !trDraft.omniroute_model.trim()) {
        showToast("OmniRoute 모델(콤보) 이름을 입력해주세요", "error");
        return;
      }
      const ctx = parseInt(trDraft.llamacpp_ctx, 10);
      const port = parseInt(trDraft.llamacpp_port, 10);
      if (Number.isNaN(ctx) || ctx < 512) {
        showToast("컨텍스트 크기는 512 이상이어야 합니다", "error");
        return;
      }
      if (Number.isNaN(port) || port < 1 || port > 65535) {
        showToast("포트는 1~65535 사이여야 합니다", "error");
        return;
      }
      const nglRaw = trDraft.llamacpp_n_gpu_layers.trim();
      const ngl = nglRaw ? parseInt(nglRaw, 10) : null;
      if (nglRaw && (Number.isNaN(ngl!) || ngl! < 0)) {
        showToast("GPU 레이어(-ngl)는 0 이상이어야 합니다", "error");
        return;
      }
      const thRaw = trDraft.llamacpp_threads.trim();
      const threads = thRaw ? parseInt(thRaw, 10) : null;
      if (thRaw && (Number.isNaN(threads!) || threads! < 1)) {
        showToast("스레드 수는 1 이상이어야 합니다", "error");
        return;
      }

      const parseChunkLines = (raw: string, label: string): number | null => {
        const n = parseInt(raw, 10);
        if (Number.isNaN(n) || n < 1 || n > 200) {
          showToast(`${label} 청크 길이는 1~200줄 사이여야 합니다`, "error");
          return null;
        }
        return n;
      };
      const parseOverlapLines = (raw: string, label: string): number | null => {
        const n = parseInt(raw, 10);
        if (Number.isNaN(n) || n < 0 || n > 50) {
          showToast(`${label} 겹침(오버랩)은 0~50줄 사이여야 합니다`, "error");
          return null;
        }
        return n;
      };
      const parseContextLen = (raw: string, label: string): number | null => {
        const n = parseInt(raw, 10);
        if (Number.isNaN(n) || n < 512) {
          showToast(`${label} 컨텍스트 길이는 512 이상이어야 합니다`, "error");
          return null;
        }
        return n;
      };

      const llamacppChunkTarget = parseChunkLines(trDraft.llamacpp_chunk_target_lines, "llama.cpp");
      const llamacppChunkOverlap = parseOverlapLines(trDraft.llamacpp_chunk_overlap_lines, "llama.cpp");
      const ollamaChunkTarget = parseChunkLines(trDraft.ollama_chunk_target_lines, "Ollama");
      const ollamaChunkOverlap = parseOverlapLines(trDraft.ollama_chunk_overlap_lines, "Ollama");
      const ollamaContextLen = parseContextLen(trDraft.ollama_context_length, "Ollama");
      const openrouterChunkTarget = parseChunkLines(trDraft.openrouter_chunk_target_lines, "OpenRouter");
      const openrouterChunkOverlap = parseOverlapLines(trDraft.openrouter_chunk_overlap_lines, "OpenRouter");
      const omnirouteChunkTarget = parseChunkLines(trDraft.omniroute_chunk_target_lines, "OmniRoute");
      const omnirouteChunkOverlap = parseOverlapLines(trDraft.omniroute_chunk_overlap_lines, "OmniRoute");
      const omnirouteContextLen = parseContextLen(trDraft.omniroute_context_length, "OmniRoute");
      const geminiChunkTarget = parseChunkLines(trDraft.gemini_chunk_target_lines, "Gemini");
      const geminiChunkOverlap = parseOverlapLines(trDraft.gemini_chunk_overlap_lines, "Gemini");
      if (
        llamacppChunkTarget === null ||
        llamacppChunkOverlap === null ||
        ollamaChunkTarget === null ||
        ollamaChunkOverlap === null ||
        ollamaContextLen === null ||
        openrouterChunkTarget === null ||
        openrouterChunkOverlap === null ||
        omnirouteChunkTarget === null ||
        omnirouteChunkOverlap === null ||
        omnirouteContextLen === null ||
        geminiChunkTarget === null ||
        geminiChunkOverlap === null
      ) {
        return;
      }

      const geminiChain = trDraft.gemini_chain.filter(Boolean);
      if (trDraft.provider === "gemini" && geminiChain.length === 0) {
        showToast("Gemini 폴백 체인에 모델을 1개 이상 추가해주세요", "error");
        return;
      }

      const snap = await patchTranslationSettings({
        provider: trDraft.provider,
        openrouter_profile: trDraft.openrouter_profile,
        omniroute_url: trDraft.omniroute_url,
        omniroute_model: trDraft.omniroute_model,
        omniroute_chunk_target_lines: omnirouteChunkTarget,
        omniroute_chunk_overlap_lines: omnirouteChunkOverlap,
        omniroute_context_length: omnirouteContextLen,
        llamacpp_bin: trDraft.llamacpp_bin,
        llamacpp_url: trDraft.llamacpp_url,
        llamacpp_port: port,
        llamacpp_model: trDraft.llamacpp_model,
        llamacpp_gguf_path: trDraft.llamacpp_gguf_path,
        llamacpp_ctx: ctx,
        llamacpp_n_gpu_layers: ngl,
        llamacpp_cache_type_k: trDraft.llamacpp_cache_type_k,
        llamacpp_cache_type_v: trDraft.llamacpp_cache_type_v,
        llamacpp_threads: threads,
        llamacpp_tensorcores: trDraft.llamacpp_tensorcores,
        llamacpp_flash_attn: trDraft.llamacpp_flash_attn,
        llamacpp_auto_start: trDraft.llamacpp_auto_start,
        llamacpp_fit_vram: trDraft.llamacpp_fit_vram,
        llamacpp_chunk_target_lines: llamacppChunkTarget,
        llamacpp_chunk_overlap_lines: llamacppChunkOverlap,
        ollama_chunk_target_lines: ollamaChunkTarget,
        ollama_chunk_overlap_lines: ollamaChunkOverlap,
        ollama_context_length: ollamaContextLen,
        openrouter_chunk_target_lines: openrouterChunkTarget,
        openrouter_chunk_overlap_lines: openrouterChunkOverlap,
        gemini_chain: geminiChain,
        gemini_chunk_target_lines: geminiChunkTarget,
        gemini_chunk_overlap_lines: geminiChunkOverlap,
        ...(geminiApiKeyDraft.trim() ? { gemini_api_key: geminiApiKeyDraft.trim() } : {}),
      });
      setTr(snap);
      applyTrSnap(snap);
      setGeminiApiKeyDraft("");
      showToast("번역 엔진 설정 저장됨", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "번역 설정 저장 실패", "error");
    } finally {
      setTrSaving(false);
    }
  };

  const handleResetTranslation = () => {
    if (!tr) return;
    applyTrSnap(tr);
    setGeminiApiKeyDraft("");
  };

  const providerOptions = (tr?.provider_options ?? []).map(o => ({ label: o.label, value: o.id }));
  const modelOptions = (tr?.model_options ?? []).map(o => ({ label: o.label, value: o.id }));
  const orProfileOptions = (tr?.openrouter_profile_options ?? []).map(o => ({ label: o.label, value: o.id }));
  const commandPreview = tr?.llamacpp.command_preview ?? "";
  const geminiModelOptions = (tr?.gemini.model_options ?? []).map(o => ({
    label: `${o.label} (${o.rpm ?? "?"} RPM · ${o.tpm ? `${(o.tpm / 1_000_000).toFixed(0)}M` : "?"} TPM · ${o.rpd ?? "무제한"} RPD)`,
    value: o.id,
  }));

  const [prLoading, setPrLoading] = useState(true);
  const [prSaving, setPrSaving] = useState(false);
  const [pr, setPr] = useState<TranslationPromptSettings | null>(null);
  const [prDraft, setPrDraft] = useState({
    prompt_mode: "html",
    prompt_variant: "general",
    system_prompt_template: "",
    global_note: "",
  });

  const applyPrSnap = useCallback((snap: TranslationPromptSettings) => {
    setPrDraft({
      prompt_mode: snap.prompt_mode,
      prompt_variant: snap.prompt_variant,
      system_prompt_template: snap.system_prompt_template,
      global_note: snap.global_note,
    });
  }, []);

  const loadPrompt = useCallback(async () => {
    setPrLoading(true);
    try {
      const snap = await fetchTranslationPromptSettings();
      setPr(snap);
      applyPrSnap(snap);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "프롬프트 설정 불러오기 실패", "error");
    } finally {
      setPrLoading(false);
    }
  }, [applyPrSnap, showToast]);

  useEffect(() => {
    void loadPrompt();
  }, [loadPrompt]);

  const handleSavePrompt = async () => {
    setPrSaving(true);
    try {
      const snap = await patchTranslationPromptSettings({
        prompt_mode: prDraft.prompt_mode,
        prompt_variant: prDraft.prompt_variant,
        system_prompt_template: prDraft.system_prompt_template,
        global_note: prDraft.global_note,
      });
      setPr(snap);
      applyPrSnap(snap);
      showToast("번역 프롬프트 저장됨", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "프롬프트 저장 실패", "error");
    } finally {
      setPrSaving(false);
    }
  };

  const handleResetPromptTemplate = () => {
    const variant = prDraft.prompt_variant as "general" | "jav";
    const builtin = pr?.builtin_templates[variant] ?? prDraft.system_prompt_template;
    setPrDraft(d => ({ ...d, system_prompt_template: builtin }));
  };

  const handleVariantChange = (variant: string) => {
    const builtin = pr?.builtin_templates[variant] ?? "";
    setPrDraft(d => ({
      ...d,
      prompt_variant: variant,
      system_prompt_template: pr?.uses_custom_template ? d.system_prompt_template : builtin,
    }));
  };

  const promptModeOptions = (pr?.prompt_mode_options ?? []).map(o => ({ label: o.label, value: o.id }));
  const promptVariantOptions = (pr?.prompt_variant_options ?? []).map(o => ({ label: o.label, value: o.id }));

  const [cacheStats, setCacheStats] = useState<ProxyCacheStats | null>(null);
  const [cacheLoading, setCacheLoading] = useState(true);
  const [cacheClearing, setCacheClearing] = useState(false);

  const loadCacheStats = useCallback(async () => {
    setCacheLoading(true);
    try {
      setCacheStats(await fetchProxyCacheStats());
    } catch (e) {
      showToast(e instanceof Error ? e.message : "재생 캐시 정보 불러오기 실패", "error");
    } finally {
      setCacheLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadCacheStats();
  }, [loadCacheStats]);

  const handleClearCache = async () => {
    setCacheClearing(true);
    try {
      const res = await clearProxyCache();
      showToast(
        `재생 캐시 정리 완료 · ${res.removed}개 삭제 (${formatBytes(res.freed_bytes)} 확보)`,
        "success",
      );
      await loadCacheStats();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "재생 캐시 정리 실패", "error");
    } finally {
      setCacheClearing(false);
    }
  };

  const cacheUsagePct =
    cacheStats && cacheStats.max_bytes > 0
      ? Math.min(100, (cacheStats.total_bytes / cacheStats.max_bytes) * 100)
      : 0;

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl">

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">설정</h1>
          <p className="text-base text-muted-foreground mt-0.5">JAVSTORY Pro 환경 설정</p>
        </div>
      </div>

      {/* ── 자막 전사 ── */}
      <SettingsSection icon={Mic2} title="자막 전사">
        {sttLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground py-4">
            <Loader2 className="w-4 h-4 animate-spin" />
            설정 불러오는 중…
          </div>
        ) : (
          <>
            <SettingsRow
              label="STT 프리셋"
              hint={selectedEngineHint ?? "모델 + GPU 백엔드 + stable-ts 후처리를 한 번에 선택"}
            >
              <SelectInput
                value={sttDraft.engine}
                onChange={v => setSttDraft(d => ({ ...d, engine: v }))}
                options={engineOptions.length ? engineOptions : [
                  { label: "Stable TS (PyTorch)", value: "stable_ts" },
                  { label: "Faster-Whisper-XXL", value: "stable_ts_fw" },
                  { label: "Anime-Whisper + Stable TS", value: "anime_whisper" },
                ]}
              />
            </SettingsRow>

            {sttDraft.engine === "stable_ts" && (
              <SettingsRow label="Whisper 모델" hint="PyTorch stable-ts 백엔드">
                <SelectInput
                  value={sttDraft.whisper_model}
                  onChange={v => setSttDraft(d => ({ ...d, whisper_model: v }))}
                  options={WHISPER_MODEL_OPTIONS}
                />
              </SettingsRow>
            )}

            {sttDraft.engine === "stable_ts_fw" && (
              <>
                <SettingsRow
                  label="Faster-Whisper 모델"
                  hint="CTranslate2 가중치 — kotoba는 일본어 특화"
                >
                  <SelectInput
                    value={sttDraft.faster_whisper_model}
                    onChange={v => setSttDraft(d => ({ ...d, faster_whisper_model: v }))}
                    options={(() => {
                      const fromApi = (stt?.faster_whisper_model_options ?? []).map(o => ({
                        label: o.label,
                        value: o.id,
                      }));
                      const base = fromApi.length ? fromApi : FASTER_WHISPER_MODEL_OPTIONS;
                      const cur = sttDraft.faster_whisper_model;
                      if (cur && !base.some(o => o.value === cur)) {
                        return [{ label: cur, value: cur }, ...base];
                      }
                      return base;
                    })()}
                  />
                </SettingsRow>

                <div className="pt-2 pb-1 border-t border-white/5 flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-white/90">Faster-Whisper-XXL 세부 옵션</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      language=ja · VAD·beam·temperature 등 XXL CLI 대응 값
                    </p>
                  </div>
                  <ActionButton
                    variant="ghost"
                    size="sm"
                    icon={<RotateCcw className="w-3.5 h-3.5" />}
                    onClick={handleResetFwXxlDefaults}
                  >
                    기본값으로 초기화
                  </ActionButton>
                </div>

                <SettingsRow label="Language" hint="--language">
                  <TextInput
                    value={sttDraft.fw_xxl.language}
                    onChange={v => setFwXxl("language", v)}
                  />
                </SettingsRow>
                <SettingsRow label="VAD 필터" hint="--vad_filter" control="switch">
                  <Toggle
                    checked={sttDraft.fw_xxl.vad_filter}
                    onChange={v => setFwXxl("vad_filter", v)}
                    disabled={sttSaving}
                  />
                </SettingsRow>
                <SettingsRow label="VAD 임계값" hint="--vad_threshold (높을수록 배경음 억제)">
                  <TextInput
                    value={sttDraft.fw_xxl.vad_threshold}
                    onChange={v => setFwXxl("vad_threshold", v)}
                  />
                </SettingsRow>
                <SettingsRow label="최소 발화(ms)" hint="--vad_min_speech_duration_ms">
                  <TextInput
                    value={sttDraft.fw_xxl.vad_min_speech_duration_ms}
                    onChange={v => setFwXxl("vad_min_speech_duration_ms", v)}
                  />
                </SettingsRow>
                <SettingsRow label="최대 발화(s)" hint="--vad_max_speech_duration_s">
                  <TextInput
                    value={sttDraft.fw_xxl.vad_max_speech_duration_s}
                    onChange={v => setFwXxl("vad_max_speech_duration_s", v)}
                  />
                </SettingsRow>
                <SettingsRow
                  label="이전 텍스트 조건"
                  hint="--condition_on_previous_text"
                  control="switch"
                >
                  <Toggle
                    checked={sttDraft.fw_xxl.condition_on_previous_text}
                    onChange={v => setFwXxl("condition_on_previous_text", v)}
                    disabled={sttSaving}
                  />
                </SettingsRow>
                <SettingsRow label="무음 임계값" hint="--no_speech_threshold">
                  <TextInput
                    value={sttDraft.fw_xxl.no_speech_threshold}
                    onChange={v => setFwXxl("no_speech_threshold", v)}
                  />
                </SettingsRow>
                <SettingsRow label="로그확률 임계값" hint="--log_prob_threshold (낮을수록 fallback 완화)">
                  <TextInput
                    value={sttDraft.fw_xxl.log_prob_threshold}
                    onChange={v => setFwXxl("log_prob_threshold", v)}
                  />
                </SettingsRow>
                <SettingsRow label="압축률 임계값" hint="--compression_ratio_threshold (높을수록 fallback 완화)">
                  <TextInput
                    value={sttDraft.fw_xxl.compression_ratio_threshold}
                    onChange={v => setFwXxl("compression_ratio_threshold", v)}
                  />
                </SettingsRow>
                <SettingsRow label="Beam size" hint="--beam_size">
                  <TextInput
                    value={sttDraft.fw_xxl.beam_size}
                    onChange={v => setFwXxl("beam_size", v)}
                  />
                </SettingsRow>
                <SettingsRow label="Best of" hint="--best_of">
                  <TextInput
                    value={sttDraft.fw_xxl.best_of}
                    onChange={v => setFwXxl("best_of", v)}
                  />
                </SettingsRow>
                <SettingsRow label="Temperature" hint="--temperature">
                  <TextInput
                    value={sttDraft.fw_xxl.temperature}
                    onChange={v => setFwXxl("temperature", v)}
                  />
                </SettingsRow>
                <SettingsRow label="Temp 증가(fallback)" hint="--temperature_increment_on_fallback">
                  <TextInput
                    value={sttDraft.fw_xxl.temperature_increment_on_fallback}
                    onChange={v => setFwXxl("temperature_increment_on_fallback", v)}
                  />
                </SettingsRow>
                <SettingsRow label="환각 침묵 임계(s)" hint="--hallucination_silence_threshold">
                  <TextInput
                    value={sttDraft.fw_xxl.hallucination_silence_threshold}
                    onChange={v => setFwXxl("hallucination_silence_threshold", v)}
                  />
                </SettingsRow>
                <SettingsRow label="Compute type" hint="--compute_type (CUDA float16)">
                  <SelectInput
                    value={sttDraft.fw_xxl.compute_type}
                    onChange={v => setFwXxl("compute_type", v)}
                    options={[
                      { label: "float16", value: "float16" },
                      { label: "int8_float16", value: "int8_float16" },
                      { label: "int8", value: "int8" },
                      { label: "float32", value: "float32" },
                    ]}
                  />
                </SettingsRow>
                <SettingsRow label="Batch size" hint="--batch_size">
                  <TextInput
                    value={sttDraft.fw_xxl.batch_size}
                    onChange={v => setFwXxl("batch_size", v)}
                  />
                </SettingsRow>
                <SettingsRow label="단어 타임스탬프" hint="--word_timestamps" control="switch">
                  <Toggle
                    checked={sttDraft.fw_xxl.word_timestamps}
                    onChange={v => setFwXxl("word_timestamps", v)}
                    disabled={sttSaving}
                  />
                </SettingsRow>
                <SettingsRow label="반복 페널티" hint="--repetition_penalty">
                  <TextInput
                    value={sttDraft.fw_xxl.repetition_penalty}
                    onChange={v => setFwXxl("repetition_penalty", v)}
                  />
                </SettingsRow>
              </>
            )}

            {sttDraft.engine === "anime_whisper" && (
              <SettingsRow label="HF 모델 ID" hint="litagin/anime-whisper 권장">
                <TextInput
                  value={sttDraft.hf_whisper_model}
                  onChange={v => setSttDraft(d => ({ ...d, hf_whisper_model: v }))}
                />
              </SettingsRow>
            )}

            {sttDraft.engine !== "stable_ts_fw" && (
              <SettingsRow
                label="VAD 임계값"
                hint="높을수록 헛소리·배경음 자막 억제 (대사만 모드 시 최소 0.45)"
              >
                <TextInput
                  value={sttDraft.vad_threshold}
                  onChange={v => setSttDraft(d => ({ ...d, vad_threshold: v }))}
                />
              </SettingsRow>
            )}

            <SettingsRow
              label="대사만 모드"
              hint="신음·효과음·헛자막 세그먼트 제거 (Anime-Whisper 사용 시 권장)"
              control="switch"
            >
              <Toggle
                checked={sttDraft.dialogue_only}
                onChange={v => setSttDraft(d => ({ ...d, dialogue_only: v }))}
                disabled={sttSaving}
              />
            </SettingsRow>

            <div className="flex gap-2 pt-1">
              <ActionButton
                variant="ghost"
                size="sm"
                icon={<RotateCcw className="w-3.5 h-3.5" />}
                onClick={handleResetStt}
                disabled={sttSaving}
              >
                되돌리기
              </ActionButton>
              <ActionButton
                variant="primary"
                size="sm"
                loading={sttSaving}
                icon={<Save className="w-3.5 h-3.5" />}
                onClick={() => void handleSaveStt()}
              >
                전사 설정 저장
              </ActionButton>
            </div>
          </>
        )}
      </SettingsSection>

      {/* ── 번역 엔진 ── */}
      <SettingsSection icon={Languages} title="번역 (JA→KO)">
        {trLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground py-4">
            <Loader2 className="w-4 h-4 animate-spin" />
            설정 불러오는 중…
          </div>
        ) : (
          <>
            <SettingsRow label="번역 백엔드" hint="자막 JA→KO 번역에 사용할 LLM">
              <SelectInput
                value={trDraft.provider}
                onChange={v => setTrDraft(d => ({ ...d, provider: v }))}
                options={providerOptions.length ? providerOptions : [
                  { label: "llama.cpp (로컬 llama-server)", value: "llamacpp" },
                  { label: "OpenRouter (클라우드 API)", value: "openrouter" },
                  { label: "Ollama (로컬)", value: "ollama" },
                  { label: "OmniRoute (로컬 라우터)", value: "omniroute" },
                  { label: "Gemini (Google API 직접 호출)", value: "gemini" },
                ]}
              />
            </SettingsRow>

            {trDraft.provider === "gemini" && (
              <>
                <SettingsRow
                  label="API 키"
                  hint={
                    tr?.gemini.has_api_key
                      ? "이미 설정되어 있습니다 — 바꾸려면 새 키를 입력 후 저장"
                      : "AI Studio에서 발급한 키를 입력하세요 (JAVSTORY_GEMINI_API_KEY로 저장)"
                  }
                >
                  <SecretInput
                    value={geminiApiKeyDraft}
                    onChange={setGeminiApiKeyDraft}
                    placeholder={tr?.gemini.has_api_key ? "설정됨 · 변경 시에만 입력" : "AIzaSy..."}
                  />
                </SettingsRow>

                <div className="space-y-2">
                  <div>
                    <p className="text-base text-[#c8c8e0]">폴백 체인</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      1순위가 기본 모델입니다. RPM/일일 쿼터 초과 시 자동으로 다음 모델로 전환됩니다.
                    </p>
                  </div>

                  <div className="space-y-2">
                    {trDraft.gemini_chain.map((modelId, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground w-4 shrink-0 text-right">
                          {idx + 1}
                        </span>
                        <div className="flex-1 min-w-0">
                          <SelectInput
                            value={modelId}
                            onChange={v =>
                              setTrDraft(d => {
                                const next = [...d.gemini_chain];
                                next[idx] = v;
                                return { ...d, gemini_chain: next };
                              })
                            }
                            options={
                              geminiModelOptions.length
                                ? geminiModelOptions
                                : [{ label: modelId, value: modelId }]
                            }
                          />
                        </div>
                        <ActionButton
                          variant="ghost"
                          size="icon"
                          disabled={idx === 0}
                          onClick={() =>
                            setTrDraft(d => {
                              const next = [...d.gemini_chain];
                              [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
                              return { ...d, gemini_chain: next };
                            })
                          }
                        >
                          <ChevronUp className="w-4 h-4" />
                        </ActionButton>
                        <ActionButton
                          variant="ghost"
                          size="icon"
                          disabled={idx === trDraft.gemini_chain.length - 1}
                          onClick={() =>
                            setTrDraft(d => {
                              const next = [...d.gemini_chain];
                              [next[idx + 1], next[idx]] = [next[idx], next[idx + 1]];
                              return { ...d, gemini_chain: next };
                            })
                          }
                        >
                          <ChevronDown className="w-4 h-4" />
                        </ActionButton>
                        <ActionButton
                          variant="ghost"
                          size="icon"
                          disabled={trDraft.gemini_chain.length <= 1}
                          onClick={() =>
                            setTrDraft(d => ({
                              ...d,
                              gemini_chain: d.gemini_chain.filter((_, i) => i !== idx),
                            }))
                          }
                        >
                          <Trash2 className="w-4 h-4" />
                        </ActionButton>
                      </div>
                    ))}
                  </div>

                  <ActionButton
                    variant="ghost"
                    size="sm"
                    icon={<Plus className="w-3.5 h-3.5" />}
                    onClick={() =>
                      setTrDraft(d => {
                        const catalog = tr?.gemini.model_options ?? [];
                        const unused = catalog.find(o => !d.gemini_chain.includes(o.id));
                        const nextModel = unused?.id ?? catalog[0]?.id ?? "gemini-2.0-flash";
                        return { ...d, gemini_chain: [...d.gemini_chain, nextModel] };
                      })
                    }
                  >
                    모델 추가
                  </ActionButton>
                </div>

                <SettingsRow label="청크 길이 (줄)" hint="권장 16줄">
                  <TextInput
                    value={trDraft.gemini_chunk_target_lines}
                    onChange={v => setTrDraft(d => ({ ...d, gemini_chunk_target_lines: v }))}
                    placeholder="16"
                  />
                </SettingsRow>

                <SettingsRow label="겹침 · 슬라이딩 윈도우 (줄)" hint="권장 4줄">
                  <TextInput
                    value={trDraft.gemini_chunk_overlap_lines}
                    onChange={v => setTrDraft(d => ({ ...d, gemini_chunk_overlap_lines: v }))}
                    placeholder="4"
                  />
                </SettingsRow>
              </>
            )}

            {trDraft.provider === "omniroute" && (
              <>
                <SettingsRow label="서버 URL" hint="사용자가 로컬에서 직접 띄운 OpenAI 호환 라우터 주소">
                  <TextInput
                    value={trDraft.omniroute_url}
                    onChange={v => setTrDraft(d => ({ ...d, omniroute_url: v }))}
                    placeholder="http://localhost:20128/v1"
                  />
                </SettingsRow>

                <SettingsRow label="모델(콤보)" hint="OmniRoute에 설정해 둔 콤보 이름을 그대로 입력">
                  <TextInput
                    value={trDraft.omniroute_model}
                    onChange={v => setTrDraft(d => ({ ...d, omniroute_model: v }))}
                    placeholder="예: combo"
                  />
                </SettingsRow>

                <SettingsRow label="청크 길이 (줄)" hint="한 번에 번역 요청할 자막 줄 수. 권장 12줄">
                  <TextInput
                    value={trDraft.omniroute_chunk_target_lines}
                    onChange={v => setTrDraft(d => ({ ...d, omniroute_chunk_target_lines: v }))}
                    placeholder="12"
                  />
                </SettingsRow>

                <SettingsRow label="겹침 · 슬라이딩 윈도우 (줄)" hint="이전 청크 마지막 N줄의 원문을 읽기 전용 문맥으로 함께 전달(재번역 대상 아님). 권장 3줄">
                  <TextInput
                    value={trDraft.omniroute_chunk_overlap_lines}
                    onChange={v => setTrDraft(d => ({ ...d, omniroute_chunk_overlap_lines: v }))}
                    placeholder="3"
                  />
                </SettingsRow>

                <SettingsRow label="컨텍스트 길이" hint="OmniRoute가 실제로 라우팅하는 모델의 컨텍스트 윈도우(토큰). 모르면 기본값 32768 유지">
                  <TextInput
                    value={trDraft.omniroute_context_length}
                    onChange={v => setTrDraft(d => ({ ...d, omniroute_context_length: v }))}
                    placeholder="32768"
                  />
                </SettingsRow>
              </>
            )}

            {trDraft.provider === "openrouter" && (
              <>
                <SettingsRow label="OpenRouter 프로필">
                  <SelectInput
                    value={trDraft.openrouter_profile}
                    onChange={v => setTrDraft(d => ({ ...d, openrouter_profile: v }))}
                    options={orProfileOptions.length ? orProfileOptions : [
                      { label: "DeepSeek V3.2 (기본)", value: "default" },
                    ]}
                  />
                </SettingsRow>

                <SettingsRow label="청크 길이 (줄)" hint="클라우드 모델이라 여유 있게 잡아도 됨. 권장 16줄">
                  <TextInput
                    value={trDraft.openrouter_chunk_target_lines}
                    onChange={v => setTrDraft(d => ({ ...d, openrouter_chunk_target_lines: v }))}
                    placeholder="16"
                  />
                </SettingsRow>

                <SettingsRow label="겹침 · 슬라이딩 윈도우 (줄)" hint="권장 4줄">
                  <TextInput
                    value={trDraft.openrouter_chunk_overlap_lines}
                    onChange={v => setTrDraft(d => ({ ...d, openrouter_chunk_overlap_lines: v }))}
                    placeholder="4"
                  />
                </SettingsRow>
              </>
            )}

            {trDraft.provider === "ollama" && (
              <>
                <SettingsRow label="청크 길이 (줄)" hint="선택한 모델 크기에 맞춘 권장값이 기본으로 채워집니다">
                  <TextInput
                    value={trDraft.ollama_chunk_target_lines}
                    onChange={v => setTrDraft(d => ({ ...d, ollama_chunk_target_lines: v }))}
                    placeholder="12"
                  />
                </SettingsRow>

                <SettingsRow label="겹침 · 슬라이딩 윈도우 (줄)">
                  <TextInput
                    value={trDraft.ollama_chunk_overlap_lines}
                    onChange={v => setTrDraft(d => ({ ...d, ollama_chunk_overlap_lines: v }))}
                    placeholder="3"
                  />
                </SettingsRow>

                <SettingsRow label="컨텍스트 길이 (num_ctx)" hint="Ollama 모델 컨텍스트 윈도우(토큰). 기본 2048 — 배경·번역 노트·힌트가 길어 잘리면 4096 이상으로 상향">
                  <TextInput
                    value={trDraft.ollama_context_length}
                    onChange={v => setTrDraft(d => ({ ...d, ollama_context_length: v }))}
                    placeholder="2048"
                  />
                </SettingsRow>
              </>
            )}

            {trDraft.provider === "llamacpp" && (
              <>
                <SettingsRow
                  label="GGUF 모델"
                  hint={
                    tr?.llamacpp.gguf_scan_dir
                      ? `${tr.llamacpp.gguf_scan_dir} 폴더의 .gguf 파일`
                      : "D:\\Models 폴더의 .gguf 파일"
                  }
                >
                  <SelectInput
                    value={trDraft.llamacpp_model}
                    onChange={v => {
                      const opt = tr?.model_options.find(o => o.id === v);
                      setTrDraft(d => ({
                        ...d,
                        llamacpp_model: v,
                        llamacpp_gguf_path: opt?.gguf_path ?? d.llamacpp_gguf_path,
                      }));
                    }}
                    options={modelOptions}
                  />
                </SettingsRow>

                <SettingsRow label="llama-server.exe 경로" hint="비우면 PATH의 llama-server.exe 사용">
                  <TextInput
                    value={trDraft.llamacpp_bin}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_bin: v }))}
                    placeholder="C:\\llama.cpp\\llama-server.exe"
                  />
                </SettingsRow>

                <SettingsRow
                  label="GGUF 경로"
                  hint="모델 선택 시 자동 입력. 직접 경로를 입력해도 됩니다."
                >
                  <TextInput
                    value={trDraft.llamacpp_gguf_path}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_gguf_path: v }))}
                  />
                </SettingsRow>

                <SettingsRow label="서버 URL">
                  <TextInput
                    value={trDraft.llamacpp_url}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_url: v }))}
                  />
                </SettingsRow>

                <SettingsRow label="포트" hint="기본 8080 (llama-server --port)">
                  <TextInput
                    value={trDraft.llamacpp_port}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_port: v }))}
                  />
                </SettingsRow>

                <SettingsRow label="컨텍스트 (-c)" hint="Qwen2.5 14B 권장: 16384">
                  <TextInput
                    value={trDraft.llamacpp_ctx}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_ctx: v }))}
                  />
                </SettingsRow>

                <SettingsRow label="청크 길이 (줄)" hint="선택한 모델(Qwen/Gemma 등)에 맞춘 권장값이 기본으로 채워집니다">
                  <TextInput
                    value={trDraft.llamacpp_chunk_target_lines}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_chunk_target_lines: v }))}
                  />
                </SettingsRow>

                <SettingsRow label="겹침 · 슬라이딩 윈도우 (줄)">
                  <TextInput
                    value={trDraft.llamacpp_chunk_overlap_lines}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_chunk_overlap_lines: v }))}
                  />
                </SettingsRow>

                <SettingsRow label="GPU 레이어 (-ngl)" hint="99 = 전체 GPU 오프로드. VRAM 부족 시 비우고 VRAM 자동 맞춤 사용">
                  <TextInput
                    value={trDraft.llamacpp_n_gpu_layers}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_n_gpu_layers: v }))}
                    placeholder="99"
                  />
                </SettingsRow>

                <SettingsRow label="KV 캐시 K (-ctk)" hint="TurboQuant: q8_0 권장">
                  <TextInput
                    value={trDraft.llamacpp_cache_type_k}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_cache_type_k: v }))}
                  />
                </SettingsRow>

                <SettingsRow label="KV 캐시 V (-ctv)">
                  <TextInput
                    value={trDraft.llamacpp_cache_type_v}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_cache_type_v: v }))}
                  />
                </SettingsRow>

                <SettingsRow label="CPU 스레드 (-t)" hint="Ryzen 7 5800X 등 8C/16T: 12 권장">
                  <TextInput
                    value={trDraft.llamacpp_threads}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_threads: v }))}
                    placeholder="12"
                  />
                </SettingsRow>

                <SettingsRow label="Tensor Cores" hint="NVIDIA GPU에서 --tensorcores on" control="switch">
                  <Toggle
                    checked={trDraft.llamacpp_tensorcores}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_tensorcores: v }))}
                    disabled={trSaving}
                  />
                </SettingsRow>

                <SettingsRow label="Flash Attention (-fa)" control="switch">
                  <Toggle
                    checked={trDraft.llamacpp_flash_attn}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_flash_attn: v }))}
                    disabled={trSaving}
                  />
                </SettingsRow>

                <SettingsRow label="VRAM 자동 맞춤 (-fit)" hint="-ngl 고정 시 끄는 것을 권장" control="switch">
                  <Toggle
                    checked={trDraft.llamacpp_fit_vram}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_fit_vram: v }))}
                    disabled={trSaving}
                  />
                </SettingsRow>

                <SettingsRow label="작업 시 자동 기동" hint="번역 시작 시 llama-server 자동 실행" control="switch">
                  <Toggle
                    checked={trDraft.llamacpp_auto_start}
                    onChange={v => setTrDraft(d => ({ ...d, llamacpp_auto_start: v }))}
                    disabled={trSaving}
                  />
                </SettingsRow>

                {commandPreview && (
                  <SettingsRow label="실행 명령 미리보기" hint="저장 후 자동 생성">
                    <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-all font-mono bg-bg-surface border border-white/[0.06] rounded-lg p-3 max-h-32 overflow-y-auto">
                      {commandPreview}
                    </pre>
                  </SettingsRow>
                )}
              </>
            )}

            <div className="flex gap-2 pt-1">
              <ActionButton
                variant="ghost"
                size="sm"
                icon={<RotateCcw className="w-3.5 h-3.5" />}
                onClick={handleResetTranslation}
                disabled={trSaving}
              >
                되돌리기
              </ActionButton>
              <ActionButton
                variant="primary"
                size="sm"
                loading={trSaving}
                icon={<Save className="w-3.5 h-3.5" />}
                onClick={() => void handleSaveTranslation()}
              >
                번역 설정 저장
              </ActionButton>
            </div>
          </>
        )}
      </SettingsSection>

      {/* ── 번역 프롬프트 ── */}
      <SettingsSection icon={FileText} title="번역 프롬프트">
        {prLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground py-4">
            <Loader2 className="w-4 h-4 animate-spin" />
            설정 불러오는 중…
          </div>
        ) : (
          <>
            <SettingsRow
              label="프롬프트 형식"
              hint="llama.cpp/Qwen 사용 시 HTML 필수. JSON은 레거시 경로"
            >
              <SelectInput
                value={prDraft.prompt_mode}
                onChange={v => setPrDraft(d => ({ ...d, prompt_mode: v }))}
                options={promptModeOptions.length ? promptModeOptions : [
                  { label: "HTML", value: "html" },
                  { label: "자동", value: "auto" },
                  { label: "JSON", value: "json" },
                ]}
              />
            </SettingsRow>

            <SettingsRow label="기본 템플릿" hint="일반=공리+지침, JAV=성인 콘텐츠 지침 추가">
              <SelectInput
                value={prDraft.prompt_variant}
                onChange={handleVariantChange}
                options={promptVariantOptions.length ? promptVariantOptions : [
                  { label: "일반", value: "general" },
                  { label: "JAV 자막", value: "jav" },
                ]}
              />
            </SettingsRow>

            <div className="space-y-2">
              <div>
                <p className="text-base text-[#c8c8e0]">시스템 프롬프트</p>
                <p className="text-sm text-muted-foreground mt-0.5">
                  {"{note}"} 또는 {"{{note}}"} — 전역 노트·작품 메타·스토리 힌트가 자동 주입됩니다.
                  ChatML 토큰(&lt;|im_start|&gt; 등)은 넣지 않아도 됩니다(API role로 분리).
                </p>
              </div>
              <TextArea
                value={prDraft.system_prompt_template}
                onChange={v => setPrDraft(d => ({ ...d, system_prompt_template: v }))}
                rows={14}
              />
            </div>

            <div className="space-y-2">
              <div>
                <p className="text-base text-[#c8c8e0]">전역 번역 노트</p>
                <p className="text-sm text-muted-foreground mt-0.5">
                  시스템 프롬프트 {"{note}"}에 합쳐집니다. 배우·작품 노트는 라이브러리 상세에서 편집.
                </p>
              </div>
              <TextArea
                value={prDraft.global_note}
                onChange={v => setPrDraft(d => ({ ...d, global_note: v }))}
                rows={5}
                placeholder="[전역 규칙]&#10;[용어/은어 매핑] …"
              />
            </div>

            {pr?.user_message_format && (
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">유저 메시지 형식 (자동 생성)</p>
                <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono bg-bg-surface border border-white/[0.06] rounded-lg p-3">
                  {pr.user_message_format}
                </pre>
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <ActionButton
                variant="ghost"
                size="sm"
                icon={<RotateCcw className="w-3.5 h-3.5" />}
                onClick={handleResetPromptTemplate}
                disabled={prSaving}
              >
                템플릿 기본값
              </ActionButton>
              <ActionButton
                variant="primary"
                size="sm"
                loading={prSaving}
                icon={<Save className="w-3.5 h-3.5" />}
                onClick={() => void handleSavePrompt()}
              >
                프롬프트 저장
              </ActionButton>
            </div>
          </>
        )}
      </SettingsSection>

      {/* ── API 설정 ── */}
      <SettingsSection icon={Shield} title="API 설정">
        <SettingsRow label="Fanza API Key" hint="메타데이터 수집에 사용">
          <SecretInput value={apiKey} onChange={setApiKey} placeholder="sk-..." />
        </SettingsRow>
        <SettingsRow label="Ollama 서버 URL" hint="로컬 LLM 번역 엔드포인트">
          <TextInput value={ollamaUrl} onChange={setOllamaUrl} />
        </SettingsRow>
      </SettingsSection>

      {/* ── Harvest 성능 ── */}
      <SettingsSection icon={Wheat} title="Harvest 성능">
        {harvestLoading && !harvest ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            불러오는 중…
          </div>
        ) : (
          <>
            <SettingsRow
              label="동시 실행 수"
              hint="1~5 · llama-server --parallel과 연동 (JAVSTORY_HARVEST_CONCURRENCY)"
            >
              <SelectInput
                value={harvestDraft.harvest_concurrency}
                onChange={v => setHarvestDraft(d => ({ ...d, harvest_concurrency: v }))}
                options={["1", "2", "3", "4", "5"].map(n => ({ label: n, value: n }))}
              />
            </SettingsRow>
            <SettingsRow
              label="Harvest 중 임베딩 일시정지"
              hint="번역 GPU/RAM 확보 · 완료 후 보류 SKU 일괄 임베딩"
              control="switch"
            >
              <Toggle
                checked={harvestDraft.embeddings_pause_during_harvest}
                onChange={v =>
                  setHarvestDraft(d => ({ ...d, embeddings_pause_during_harvest: v }))
                }
                disabled={harvestSaving}
              />
            </SettingsRow>
            <SettingsRow
              label="슬롯당 ctx"
              hint="JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX · total = slot × parallel (예: 4096×5=20480)"
            >
              <TextInput
                value={harvestDraft.harvest_llamacpp_slot_ctx}
                onChange={v =>
                  setHarvestDraft(d => ({ ...d, harvest_llamacpp_slot_ctx: v }))
                }
              />
            </SettingsRow>
            {harvest?.llamacpp_spawn_diagnostics?.command ? (
              <p className="text-xs text-muted-foreground px-1 break-all font-mono">
                llama-server: {String(harvest.llamacpp_spawn_diagnostics.command)}
              </p>
            ) : null}
            {(harvest?.tuning_hints ?? []).length > 0 ? (
              <ul className="text-xs text-muted-foreground px-1 space-y-1 list-disc list-inside">
                {harvest!.tuning_hints.map(h => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            ) : null}
            <div className="flex justify-end pt-2">
              <ActionButton
                variant="primary"
                size="sm"
                loading={harvestSaving}
                icon={<Save className="w-3.5 h-3.5" />}
                onClick={() => void handleSaveHarvest()}
              >
                Harvest 설정 저장
              </ActionButton>
            </div>
          </>
        )}
      </SettingsSection>

      {/* ── 시맨틱 검색 / 임베딩 ── */}
      <SettingsSection icon={Sparkles} title="시맨틱 검색 (임베딩)">
        {embLoading && !emb ? (
          <div className="flex flex-col gap-2 py-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              불러오는 중…
            </div>
            <p className="text-xs text-muted-foreground px-1">
              임베딩 커버리지 통계를 집계합니다. 라이브러리가 크면 수 초 걸릴 수 있습니다.
            </p>
          </div>
        ) : (
          <>
            <SettingsRow
              label="임베딩 사용"
              hint="llama-server로 작품 벡터를 만들어 자연어 검색·추천에 사용"
              control="switch"
            >
              <Toggle
                checked={embDraft.enabled}
                onChange={v => setEmbDraft(d => ({ ...d, enabled: v }))}
              />
            </SettingsRow>
            <SettingsRow label="백엔드" hint="기본: llama-server (채팅용과 별도 포트 8082)">
              <SelectInput
                value={embDraft.backend}
                onChange={v => setEmbDraft(d => ({ ...d, backend: v }))}
                options={[
                  { label: "llama-server", value: "llamacpp" },
                  { label: "Ollama (레거시)", value: "ollama" },
                ]}
              />
            </SettingsRow>
            <SettingsRow
              label="모델 alias"
              hint="API model 이름 · 캐시 키 (예: nomic-embed-text)"
            >
              <TextInput
                value={embDraft.model}
                onChange={v => setEmbDraft(d => ({ ...d, model: v }))}
              />
            </SettingsRow>
            {embDraft.backend === "llamacpp" && (
              <>
                <SettingsRow
                  label="임베딩 GGUF"
                  hint={
                    ggufScanDir || emb?.gguf_scan_dir
                      ? `${ggufScanDir || emb?.gguf_scan_dir} — e5 / nomic / bge 등`
                      : "D:\\Models 폴더의 임베딩 GGUF"
                  }
                >
                  {ggufOptionsLoading && ggufOptions.length === 0 ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      GGUF 목록 불러오는 중…
                    </div>
                  ) : ggufOptions.length === 0 ? (
                    <div className="flex flex-col gap-2">
                      <p className="text-sm text-amber-300/90">
                        GGUF 목록을 불러오지 못했습니다. webapi 재시작 후 새로고침하세요.
                      </p>
                      <ActionButton variant="ghost" size="sm" onClick={() => void loadGgufOptions()}>
                        GGUF 목록 다시 불러오기
                      </ActionButton>
                    </div>
                  ) : (
                  <SelectInput
                    value={
                      ggufOptions.find(o => o.gguf_path === embDraft.gguf_path)?.id
                      ?? ggufOptions.find(o => {
                        const stem = o.label.replace(/\.gguf$/i, "").toLowerCase();
                        return stem === embDraft.model.trim().toLowerCase();
                      })?.id
                      ?? ""
                    }
                    onChange={v => {
                      const opt = ggufOptions.find(o => o.id === v);
                      const path = opt?.gguf_path ?? "";
                      const stem = path
                        ? path.replace(/^.*[\\/]/, "").replace(/\.gguf$/i, "")
                        : "";
                      setEmbDraft(d => ({
                        ...d,
                        gguf_path: path,
                        ...(path && stem ? { model: stem } : {}),
                      }));
                    }}
                    options={ggufOptions.map(o => ({
                      label: o.label,
                      value: o.id || "",
                    }))}
                  />
                  )}
                </SettingsRow>
                {ggufOptions.length <= 1 && !ggufOptionsLoading ? (
                  <p className="text-xs text-amber-300/90 px-1 -mt-2 mb-1">
                    스캔 폴더에서 임베딩 GGUF를 찾지 못했습니다. `.env`에{" "}
                    <span className="font-mono">JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF</span> 경로를
                    지정하거나 <span className="font-mono">JAVSTORY_LLAMACPP_GGUF_SCAN_DIR</span>
                    를 확인하세요.
                  </p>
                ) : null}
                {embDraft.gguf_path ? (
                  <p className="text-xs text-muted-foreground px-1 break-all -mt-2 mb-1">
                    {embDraft.gguf_path}
                  </p>
                ) : null}
              </>
            )}
            <SettingsRow
              label="최소 유사도"
              hint="이하면 제외 · 낮출수록 결과↑ / 올릴수록 엄격 (기본 0.36)"
            >
              <TextInput
                value={embDraft.search_min_score}
                onChange={v => setEmbDraft(d => ({ ...d, search_min_score: v }))}
              />
            </SettingsRow>
            <SettingsRow
              label="상대 비율"
              hint="1등 점수×비율 미만 제외 · 낮출수록 더 많이 남김 (기본 0.84)"
            >
              <TextInput
                value={embDraft.search_relative_ratio}
                onChange={v => setEmbDraft(d => ({ ...d, search_relative_ratio: v }))}
              />
            </SettingsRow>
            <SettingsRow
              label="최대 격차"
              hint="1등과의 점수 차이 허용폭 · 키우면 결과↑ (기본 0.10)"
            >
              <TextInput
                value={embDraft.search_max_gap}
                onChange={v => setEmbDraft(d => ({ ...d, search_max_gap: v }))}
              />
            </SettingsRow>
            <SettingsRow
              label="병렬 처리 개수"
              hint="텍스트를 한 번에 몇 개씩 묶어 요청할지 · 캐시 안 된 것만 대상 (기본 10, 1~64)"
            >
              <TextInput
                value={embDraft.batch_size}
                onChange={v => setEmbDraft(d => ({ ...d, batch_size: v }))}
              />
            </SettingsRow>
            {emb && (
              <p className="text-sm text-muted-foreground px-1">
                커버리지 {emb.embedded_count.toLocaleString()} / {emb.library_total.toLocaleString()}
                {" "}({emb.coverage_pct}%) · 미생성 {emb.missing_count.toLocaleString()}건
                {(emb.pending_count ?? 0) > emb.missing_count
                  ? ` · Grok 갱신 포함 대기 ${(emb.pending_count ?? 0).toLocaleString()}건`
                  : ""}
                {emb.backfill_running ? " · 백필 진행 중" : ""}
              </p>
            )}
            <div className="flex flex-wrap gap-2 justify-end pt-1">
              <ActionButton
                variant="ghost"
                size="sm"
                loading={embWarming}
                onClick={() => void handleWarmupEmbeddings()}
              >
                우선순위 워밍업
              </ActionButton>
              <ActionButton
                variant="ghost"
                size="sm"
                loading={embWarming}
                onClick={() => void handleBackfillEmbeddings()}
              >
                미생성·갱신 전체
              </ActionButton>
              <ActionButton
                variant="ghost"
                size="sm"
                icon={<RotateCcw className="w-3.5 h-3.5" />}
                onClick={handleResetEmb}
                disabled={!emb}
              >
                되돌리기
              </ActionButton>
              <ActionButton
                variant="primary"
                size="sm"
                loading={embSaving}
                icon={<Save className="w-3.5 h-3.5" />}
                onClick={() => void handleSaveEmb()}
              >
                임베딩 설정 저장
              </ActionButton>
            </div>
          </>
        )}
      </SettingsSection>

      {/* ── 처리 설정 ── */}
      <SettingsSection icon={Cpu} title="처리 설정">
        <SettingsRow label="병렬 작업 수" hint="동시 처리 가능한 최대 작업 수">
          <SelectInput
            value={concurrentTasks}
            onChange={setConcurrentTasks}
            options={[1, 2, 3, 4, 6, 8].map(n => ({ label: `${n}개`, value: String(n) }))}
          />
        </SettingsRow>
        <SettingsRow label="자동 수집" hint="폴더 감시 후 자동으로 수집 시작" control="switch">
          <Toggle checked={autoScrape} onChange={setAutoScrape} />
        </SettingsRow>
      </SettingsSection>

      {/* ── 재생 캐시 ── */}
      <SettingsSection icon={Film} title="재생 캐시 (브라우저 프록시)">
        {cacheLoading && !cacheStats ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            불러오는 중…
          </div>
        ) : (
          <>
            <p className="text-sm text-muted-foreground px-1">
              MKV·TS·HEVC 등 브라우저가 직접 못 여는 영상을 재생용 MP4로 변환해 캐시합니다.
              상한 초과 시 오래 안 본 것부터 자동 삭제되며, <span className="text-sky-300">나중에 볼</span> 영상은 시청 전까지(최대 30일) 보호됩니다.
            </p>
            {cacheStats && (
              <div className="px-1 pt-1">
                <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                  <div
                    className={cacheUsagePct >= 90 ? "h-full rounded-full bg-rose-400" : "h-full rounded-full bg-indigo-400"}
                    style={{ width: `${Math.max(2, cacheUsagePct)}%` }}
                  />
                </div>
                <p className="text-sm text-muted-foreground mt-1.5 tabular-nums">
                  {formatBytes(cacheStats.total_bytes)} / {formatBytes(cacheStats.max_bytes)}
                  {" · "}파일 {cacheStats.file_count.toLocaleString()}개
                  {" · "}{cacheUsagePct.toFixed(0)}% 사용
                </p>
              </div>
            )}
            <div className="flex flex-wrap gap-2 justify-end pt-1">
              <ActionButton
                variant="ghost"
                size="sm"
                icon={<RotateCcw className="w-3.5 h-3.5" />}
                onClick={() => void loadCacheStats()}
                disabled={cacheLoading}
              >
                새로고침
              </ActionButton>
              <ActionButton
                variant="danger"
                size="sm"
                loading={cacheClearing}
                icon={<Trash2 className="w-3.5 h-3.5" />}
                onClick={() => void handleClearCache()}
              >
                캐시 모두 비우기
              </ActionButton>
            </div>
          </>
        )}
      </SettingsSection>

      {/* ── 저장 경로 ── */}
      <SettingsSection icon={HardDrive} title="저장 경로">
        <SettingsRow label="출력 디렉토리" hint="처리된 파일 저장 위치">
          <TextInput value={outputDir} onChange={setOutputDir} />
        </SettingsRow>
        <SettingsRow label="캐시 디렉토리" hint="임시 파일 및 캐시 위치">
          <TextInput value={cacheDir} onChange={setCacheDir} />
        </SettingsRow>
      </SettingsSection>

      {/* ── 앱 설정 ── */}
      <SettingsSection icon={Globe} title="앱 설정">
        <SettingsRow label="다크 모드" hint="다크 테마 적용" control="switch">
          <Toggle checked={darkMode} onChange={setDarkMode} />
        </SettingsRow>
      </SettingsSection>

      <GlassCard variant="subtle" className="flex items-center justify-between text-sm text-muted-foreground">
        <span>JAVSTORY Pro v1.0.0</span>
        <span>Python 3.11 · PySide6 · React 18</span>
      </GlassCard>

    </div>
  );
}
