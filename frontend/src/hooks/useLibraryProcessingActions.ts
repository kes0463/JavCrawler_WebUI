import { useCallback } from "react";
import { addProductsToProcessingQueue, type ProcessingKind } from "@/api/processing";
import { useToast, type ToastLevel } from "@/contexts/ToastContext";

function kindLabel(kind: ProcessingKind): string {
  return kind === "stt" ? "STT" : "번역";
}

export async function enqueueLibraryProducts(
  codes: string[],
  kind: ProcessingKind,
  showToast: (message: string, level?: ToastLevel) => void,
): Promise<boolean> {
  const normalized = [...new Set(codes.map(c => c.trim().toUpperCase()).filter(Boolean))];
  if (!normalized.length) return false;

  try {
    const snap = await addProductsToProcessingQueue(kind, normalized);
    const planned = snap.planned ?? 0;
    const label = kindLabel(kind);

    if (normalized.length === 1) {
      showToast(
        `${normalized[0]} → ${label} 큐 (${planned}건). 「전사 · 자막」에서 시작하세요.`,
        "success",
      );
    } else {
      showToast(
        `${normalized.length}개 품번 · ${planned}건 ${label} 큐 추가. 「전사 · 자막」에서 시작하세요.`,
        "success",
      );
    }
    if (snap.warnings?.length) {
      showToast(snap.warnings[0], "warn");
    }
    return true;
  } catch (e) {
    showToast(e instanceof Error ? e.message : "큐 추가 실패", "error");
    return false;
  }
}

export function useLibraryProcessingActions() {
  const { showToast } = useToast();

  const enqueue = useCallback(
    (codes: string[], kind: ProcessingKind) => enqueueLibraryProducts(codes, kind, showToast),
    [showToast],
  );

  return { enqueueLibraryProducts: enqueue };
}
