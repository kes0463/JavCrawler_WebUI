import { useState } from "react";
import { Save, RotateCcw, HardDrive, Cpu, Globe, Shield } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { ActionButton } from "@/components/ui/ActionButton";
import {
  SettingsSection, SettingsRow,
  TextInput, SecretInput, SelectInput, Toggle,
} from "@/components/ui/SettingsControls";

export default function SettingsView() {
  const [apiKey, setApiKey] = useState("");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [whisperModel, setWhisperModel] = useState("large-v3");
  const [outputDir, setOutputDir] = useState("D:\\JAVSTORY\\output");
  const [cacheDir, setCacheDir] = useState("D:\\JAVSTORY\\cache");
  const [concurrentTasks, setConcurrentTasks] = useState("2");
  const [autoScrape, setAutoScrape] = useState(true);
  const [darkMode, setDarkMode] = useState(true);

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl">

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">설정</h1>
          <p className="text-sm text-muted-foreground mt-0.5">JAVSTORY Pro 환경 설정</p>
        </div>
        <div className="flex gap-2">
          <ActionButton variant="ghost" size="sm" icon={<RotateCcw className="w-3.5 h-3.5" />}>
            초기화
          </ActionButton>
          <ActionButton variant="primary" size="sm" icon={<Save className="w-3.5 h-3.5" />}>
            저장
          </ActionButton>
        </div>
      </div>

      {/* ── API 설정 ── */}
      <SettingsSection icon={Shield} title="API 설정">
        <SettingsRow label="Fanza API Key" hint="메타데이터 수집에 사용">
          <SecretInput value={apiKey} onChange={setApiKey} placeholder="sk-..." />
        </SettingsRow>
        <SettingsRow label="Ollama 서버 URL" hint="로컬 LLM 번역 엔드포인트">
          <TextInput value={ollamaUrl} onChange={setOllamaUrl} />
        </SettingsRow>
      </SettingsSection>

      {/* ── 처리 설정 ── */}
      <SettingsSection icon={Cpu} title="처리 설정">
        <SettingsRow label="Whisper 모델" hint="STT 전사 모델 크기">
          <SelectInput
            value={whisperModel}
            onChange={setWhisperModel}
            options={[
              { label: "tiny (빠름)",     value: "tiny" },
              { label: "base",           value: "base" },
              { label: "small",          value: "small" },
              { label: "medium",         value: "medium" },
              { label: "large-v3 (권장)", value: "large-v3" },
            ]}
          />
        </SettingsRow>
        <SettingsRow label="병렬 작업 수" hint="동시 처리 가능한 최대 작업 수">
          <SelectInput
            value={concurrentTasks}
            onChange={setConcurrentTasks}
            options={[1, 2, 3, 4, 6, 8].map(n => ({ label: `${n}개`, value: String(n) }))}
          />
        </SettingsRow>
        <SettingsRow label="자동 수집" hint="폴더 감시 후 자동으로 수집 시작">
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
        <SettingsRow label="다크 모드" hint="다크 테마 적용">
          <Toggle checked={darkMode} onChange={setDarkMode} />
        </SettingsRow>
      </SettingsSection>

      {/* ── 앱 정보 ── */}
      <GlassCard variant="subtle" className="flex items-center justify-between text-xs text-muted-foreground">
        <span>JAVSTORY Pro v1.0.0</span>
        <span>Python 3.11 · PySide6 · React 18</span>
      </GlassCard>

    </div>
  );
}
