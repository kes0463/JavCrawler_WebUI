import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  clearFolderBindingInbox,
  fetchFolderBindingInbox,
  pauseAllListedFolderMonitoring,
  pauseFolderMonitoring,
  refreshFolderBindingCandidates,
  removeFolderBindingInboxItem,
  resumeFolderMonitoring,
  type FolderBindingInboxItem,
  type FolderBindingInboxResponse,
} from "@/api/folderWatch";
import { useToast } from "@/contexts/ToastContext";
import { FolderBindingInboxDrawer } from "@/components/folder-watch/FolderBindingInboxDrawer";
import { FolderBindingReviewDialog } from "@/components/folder-watch/FolderBindingReviewDialog";

interface ReviewTarget {
  product_code: string;
  old_path: string;
  candidates: string[];
}

interface FolderWatchContextValue {
  alertCount: number;
  items: FolderBindingInboxItem[];
  inboxOpen: boolean;
  openInbox: () => void;
  closeInbox: () => void;
  refreshInbox: () => Promise<void>;
  openReviewForCode: (productCode: string) => Promise<void>;
  isBindingPending: (productCode: string) => boolean;
}

const FolderWatchContext = createContext<FolderWatchContextValue | null>(null);

const POLL_IDLE_MS = 30_000;
const POLL_ACTIVE_MS = 5_000;

export function FolderWatchProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();
  const [items, setItems] = useState<FolderBindingInboxItem[]>([]);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const knownCodesRef = useRef<Set<string>>(new Set());
  const initialLoadRef = useRef(true);
  const revisionRef = useRef(-1);

  const applyInboxResponse = useCallback(
    (res: FolderBindingInboxResponse, notifyNew: boolean) => {
      revisionRef.current = res.revision;
      if (notifyNew && !initialLoadRef.current) {
        const prev = knownCodesRef.current;
        for (const item of res.items) {
          if (!prev.has(item.product_code)) {
            showToast(
              `폴더 연결 확인 대기: ${item.product_code} — 사이드바 「폴더 알림」에서 확인하세요.`,
              "info",
            );
          }
        }
      }
      knownCodesRef.current = new Set(res.items.map(i => i.product_code));
      initialLoadRef.current = false;
      setItems(res.items);
    },
    [showToast],
  );

  const refreshInbox = useCallback(async () => {
    try {
      const res = await fetchFolderBindingInbox();
      if (!initialLoadRef.current && res.revision === revisionRef.current) {
        return;
      }
      applyInboxResponse(res, true);
    } catch {
      /* webapi 미기동 시 무시 */
    }
  }, [applyInboxResponse]);

  useEffect(() => {
    void refreshInbox();
    const pollMs = items.length > 0 ? POLL_ACTIVE_MS : POLL_IDLE_MS;
    const id = window.setInterval(() => void refreshInbox(), pollMs);
    return () => window.clearInterval(id);
  }, [items.length, refreshInbox]);

  const openReview = useCallback((item: FolderBindingInboxItem) => {
    setReview({
      product_code: item.product_code,
      old_path: item.old_path,
      candidates: [...item.candidates],
    });
  }, []);

  const openReviewForCode = useCallback(
    async (productCode: string) => {
      const pc = productCode.trim().toUpperCase();
      const cached = items.find(i => i.product_code === pc);
      if (cached) {
        openReview(cached);
        return;
      }
      try {
        const res = await fetchFolderBindingInbox();
        applyInboxResponse(res, false);
        const item = res.items.find(i => i.product_code === pc);
        if (item) {
          openReview(item);
        } else {
          showToast(`${pc} — 대기 중인 폴더 알림이 없습니다.`, "info");
        }
      } catch (e) {
        showToast(e instanceof Error ? e.message : "폴더 알림을 불러오지 못했습니다", "error");
      }
    },
    [applyInboxResponse, items, openReview, showToast],
  );

  const handleResolved = useCallback(
    async (productCode: string) => {
      try {
        const res = await removeFolderBindingInboxItem(productCode);
        applyInboxResponse(res, false);
        showToast(`${productCode} 폴더 연결이 변경되었습니다.`, "success");
      } catch (e) {
        showToast(e instanceof Error ? e.message : "인박스 갱신 실패", "error");
      }
      setReview(null);
    },
    [applyInboxResponse, showToast],
  );

  const value = useMemo<FolderWatchContextValue>(
    () => ({
      alertCount: items.length,
      items,
      inboxOpen,
      openInbox: () => setInboxOpen(true),
      closeInbox: () => setInboxOpen(false),
      refreshInbox,
      openReviewForCode,
      isBindingPending: (productCode: string) =>
        items.some(i => i.product_code === productCode.trim().toUpperCase()),
    }),
    [items, inboxOpen, openReviewForCode, refreshInbox],
  );

  return (
    <FolderWatchContext.Provider value={value}>
      {children}
      <FolderBindingInboxDrawer
        open={inboxOpen}
        items={items}
        onClose={() => setInboxOpen(false)}
        onOpenItem={openReview}
        onRemove={async pc => {
          const res = await removeFolderBindingInboxItem(pc);
          applyInboxResponse(res, false);
        }}
        onClear={async () => {
          const res = await clearFolderBindingInbox();
          applyInboxResponse(res, false);
        }}
        onPauseAll={async () => {
          const codes = items.map(i => i.product_code);
          if (!codes.length) return;
          await pauseAllListedFolderMonitoring(codes);
          await refreshInbox();
          showToast("목록에 있는 작품의 폴더 감시를 중지했습니다. (항목은 유지 · DB 연결 유지)", "info");
        }}
        onTogglePause={async (pc, paused) => {
          const res = paused
            ? await resumeFolderMonitoring(pc)
            : await pauseFolderMonitoring(pc);
          applyInboxResponse(res, false);
          showToast(
            paused
              ? `${pc} — 폴더 감시를 재개했습니다.`
              : `${pc} — 폴더 감시를 중지했습니다. (연결 정보는 유지)`,
            "info",
          );
        }}
      />
      <FolderBindingReviewDialog
        open={!!review}
        productCode={review?.product_code ?? ""}
        oldPath={review?.old_path ?? ""}
        candidates={review?.candidates ?? []}
        onClose={() => setReview(null)}
        onResolved={handleResolved}
        onRescan={async () => {
          if (!review) return;
          const res = await refreshFolderBindingCandidates(review.product_code, review.old_path);
          const item = res.items.find(i => i.product_code === review.product_code);
          if (item) {
            setReview({
              product_code: item.product_code,
              old_path: item.old_path,
              candidates: [...item.candidates],
            });
          }
          applyInboxResponse(res, false);
        }}
      />
    </FolderWatchContext.Provider>
  );
}

export function useFolderWatch() {
  const ctx = useContext(FolderWatchContext);
  if (!ctx) throw new Error("useFolderWatch must be used within FolderWatchProvider");
  return ctx;
}
