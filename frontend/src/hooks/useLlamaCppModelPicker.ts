import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchLlamaCppModels,
  fetchLlamaCppStatus,
  selectLlamaCppModel,
  type LlamaCppFeature,
  type LlamaCppModelOption,
  type LlamaCppState,
} from "@/api/llamacpp";
import { useToast } from "@/contexts/ToastContext";

const POLL_INTERVAL_MS = 1200;
const POLL_TIMEOUT_MS = 150_000;

export interface UseLlamaCppModelPicker {
  options: LlamaCppModelOption[];
  selectedId: string;
  status: LlamaCppState;
  personaChatManaged: boolean;
  onSelect: (id: string) => void;
}

/** Insight/Persona Chat 화면이 공유하는 llama.cpp 모델 선택 + 상태 폴링 훅. */
export function useLlamaCppModelPicker(feature: LlamaCppFeature): UseLlamaCppModelPicker {
  const { showToast } = useToast();
  const [options, setOptions] = useState<LlamaCppModelOption[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [status, setStatus] = useState<LlamaCppState>("stopped");
  const [personaChatManaged, setPersonaChatManaged] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastActiveRef = useRef("");

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const models = await fetchLlamaCppModels();
        if (cancelled) return;
        setOptions(models.models);
        const preferred =
          feature === "insight"
            ? models.insight_active_preset_id
            : models.persona_chat_active_preset_id;
        setSelectedId(preferred);
        lastActiveRef.current = preferred;

        const st = await fetchLlamaCppStatus();
        if (cancelled) return;
        setStatus(st.state);
        setPersonaChatManaged(st.persona_chat_managed);
        if (st.active_preset_id && (st.state === "ready" || st.state === "busy")) {
          setSelectedId(st.active_preset_id);
          lastActiveRef.current = st.active_preset_id;
        }
      } catch {
        // 모델 목록/상태 조회 실패는 조용히 무시 — 드롭다운은 빈 목록으로 유지
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [feature]);

  const onSelect = useCallback(
    (id: string) => {
      const previous = lastActiveRef.current;
      setSelectedId(id);
      (async () => {
        try {
          const res = await selectLlamaCppModel(feature, id);
          if (res.already_active) {
            lastActiveRef.current = id;
            setStatus("ready");
            return;
          }
          setStatus("spawning");
          stopPolling();
          const deadline = Date.now() + POLL_TIMEOUT_MS;
          pollRef.current = setInterval(async () => {
            try {
              const st = await fetchLlamaCppStatus();
              setStatus(st.state);
              if (st.state === "ready" && st.active_preset_id === id) {
                stopPolling();
                lastActiveRef.current = id;
                showToast("모델 전환 완료", "success");
              } else if (Date.now() > deadline) {
                stopPolling();
                setSelectedId(previous);
                showToast("모델 전환이 시간 초과되었습니다", "error");
              }
            } catch {
              if (Date.now() > deadline) stopPolling();
            }
          }, POLL_INTERVAL_MS);
        } catch (e) {
          setSelectedId(previous);
          showToast(e instanceof Error ? e.message : "모델 전환 실패", "error");
        }
      })();
    },
    [feature, showToast, stopPolling],
  );

  return { options, selectedId, status, personaChatManaged, onSelect };
}
