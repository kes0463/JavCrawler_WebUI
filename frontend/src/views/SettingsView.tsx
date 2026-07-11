import { useCallback, useEffect, useState } from "react";
import { Save, RotateCcw, HardDrive, Cpu, Globe, Shield, Mic2, Loader2, Languages, FileText, Sparkles } from "lucide-react";
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
  patchEmbeddingsSettings,
  type SttSettings,
  type TranslationSettings,
  type TranslationPromptSettings,
  type EmbeddingsSettings,
} from "@/api/settings";
import { warmupLibraryEmbeddings } from "@/api/library";
import { useToast } from "@/contexts/ToastContext";

const WHISPER_MODEL_OPTIONS = [
  { label: "large-v2 (기본)", value: "large-v2" },
  { label: "large-v3", value: "large-v3" },
  { label: "medium", value: "medium" },
  { label: "small", value: "small" },
  { label: "turbo", value: "turbo" },
];

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
      const snap = await patchSttSettings({
        engine: sttDraft.engine,
        whisper_model: sttDraft.whisper_model,
        faster_whisper_model: sttDraft.faster_whisper_model,
        hf_whisper_model: sttDraft.hf_whisper_model,
        vad_threshold: vad,
        dialogue_only: sttDraft.dialogue_only,
      });
      setStt(snap);
      showToast("전사(STT) 설정 저장됨", "success");
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
    });
  };

  const engineOptions = (stt?.engine_options ?? [])
    .filter(o => o.implemented)
    .map(o => ({ label: o.label, value: o.id }));

  const selectedEngineHint = stt?.engine_options.find(o => o.id === sttDraft.engine)?.description;

  const [embLoading, setEmbLoading] = useState(true);
  const [embSaving, setEmbSaving] = useState(false);
  const [embWarming, setEmbWarming] = useState(false);
  const [emb, setEmb] = useState<EmbeddingsSettings | null>(null);
  const [embDraft, setEmbDraft] = useState({ enabled: false, model: "nomic-embed-text" });

  const loadEmb = useCallback(async () => {
    setEmbLoading(true);
    try {
      const snap = await fetchEmbeddingsSettings();
      setEmb(snap);
      setEmbDraft({ enabled: snap.enabled, model: snap.model });
    } catch (e) {
      showToast(e instanceof Error ? e.message : "임베딩 설정 불러오기 실패", "error");
    } finally {
      setEmbLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadEmb();
  }, [loadEmb]);

  const handleSaveEmb = async () => {
    setEmbSaving(true);
    try {
      const model = embDraft.model.trim();
      if (!model) {
        showToast("임베딩 모델 이름을 입력하세요", "error");
        return;
      }
      const snap = await patchEmbeddingsSettings({
        enabled: embDraft.enabled,
        model,
      });
      setEmb(snap);
      setEmbDraft({ enabled: snap.enabled, model: snap.model });
      showToast("임베딩 설정 저장됨", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "임베딩 설정 저장 실패", "error");
    } finally {
      setEmbSaving(false);
    }
  };

  const handleResetEmb = () => {
    if (!emb) return;
    setEmbDraft({ enabled: emb.enabled, model: emb.model });
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

  const [trLoading, setTrLoading] = useState(true);
  const [trSaving, setTrSaving] = useState(false);
  const [tr, setTr] = useState<TranslationSettings | null>(null);
  const [trDraft, setTrDraft] = useState({
    provider: "llamacpp",
    openrouter_profile: "default",
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
  });

  const applyTrSnap = useCallback((snap: TranslationSettings) => {
    const lc = snap.llamacpp;
    setTrDraft({
      provider: snap.provider,
      openrouter_profile: snap.openrouter_profile,
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
      const snap = await patchTranslationSettings({
        provider: trDraft.provider,
        openrouter_profile: trDraft.openrouter_profile,
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
      });
      setTr(snap);
      applyTrSnap(snap);
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
  };

  const providerOptions = (tr?.provider_options ?? []).map(o => ({ label: o.label, value: o.id }));
  const modelOptions = (tr?.model_options ?? []).map(o => ({ label: o.label, value: o.id }));
  const orProfileOptions = (tr?.openrouter_profile_options ?? []).map(o => ({ label: o.label, value: o.id }));
  const commandPreview = tr?.llamacpp.command_preview ?? "";

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

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl">

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">설정</h1>
          <p className="text-base text-muted-foreground mt-0.5">JAVSTORY Pro 환경 설정</p>
        </div>
      </div>

      {/* ── STT / 전사 ── */}
      <SettingsSection icon={Mic2} title="전사 (STT)">
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
                  { label: "Stable TS + Faster-Whisper", value: "stable_ts_fw" },
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
              <SettingsRow
                label="Faster-Whisper 모델"
                hint="HuggingFace CTranslate2 가중치 (예: kotoba-whisper-v2.0-faster)"
              >
                <TextInput
                  value={sttDraft.faster_whisper_model}
                  onChange={v => setSttDraft(d => ({ ...d, faster_whisper_model: v }))}
                />
              </SettingsRow>
            )}

            {sttDraft.engine === "anime_whisper" && (
              <SettingsRow label="HF 모델 ID" hint="litagin/anime-whisper 권장">
                <TextInput
                  value={sttDraft.hf_whisper_model}
                  onChange={v => setSttDraft(d => ({ ...d, hf_whisper_model: v }))}
                />
              </SettingsRow>
            )}

            <SettingsRow
              label="VAD 임계값"
              hint="높을수록 헛소리·배경음 자막 억제 (대사만 모드 시 최소 0.45)"
            >
              <TextInput
                value={sttDraft.vad_threshold}
                onChange={v => setSttDraft(d => ({ ...d, vad_threshold: v }))}
              />
            </SettingsRow>

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
                STT 설정 저장
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
                ]}
              />
            </SettingsRow>

            {trDraft.provider === "openrouter" && (
              <SettingsRow label="OpenRouter 프로필">
                <SelectInput
                  value={trDraft.openrouter_profile}
                  onChange={v => setTrDraft(d => ({ ...d, openrouter_profile: v }))}
                  options={orProfileOptions.length ? orProfileOptions : [
                    { label: "DeepSeek V3.2 (기본)", value: "default" },
                  ]}
                />
              </SettingsRow>
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

      {/* ── 시맨틱 검색 / 임베딩 ── */}
      <SettingsSection icon={Sparkles} title="시맨틱 검색 (임베딩)">
        {embLoading && !emb ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            불러오는 중…
          </div>
        ) : (
          <>
            <SettingsRow
              label="임베딩 사용"
              hint="Ollama로 작품 벡터를 만들어 자연어 검색·추천에 사용"
              control="switch"
            >
              <Toggle
                checked={embDraft.enabled}
                onChange={v => setEmbDraft(d => ({ ...d, enabled: v }))}
              />
            </SettingsRow>
            <SettingsRow label="Ollama 임베딩 모델" hint="예: nomic-embed-text">
              <TextInput
                value={embDraft.model}
                onChange={v => setEmbDraft(d => ({ ...d, model: v }))}
              />
            </SettingsRow>
            {emb && (
              <p className="text-sm text-muted-foreground px-1">
                커버리지 {emb.embedded_count.toLocaleString()} / {emb.library_total.toLocaleString()}
                {" "}({emb.coverage_pct}%) · 미생성 {emb.missing_count.toLocaleString()}건
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
