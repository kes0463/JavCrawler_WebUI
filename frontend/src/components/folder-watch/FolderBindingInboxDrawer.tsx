import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FolderBindingInboxItem } from "@/api/folderWatch";

interface FolderBindingInboxDrawerProps {
  open: boolean;
  items: FolderBindingInboxItem[];
  onClose: () => void;
  onOpenItem: (item: FolderBindingInboxItem) => void;
  onRemove: (productCode: string) => void | Promise<void>;
  onClear: () => void | Promise<void>;
  onPauseAll: () => void | Promise<void>;
  onTogglePause: (productCode: string, currentlyPaused: boolean) => void | Promise<void>;
}

export function FolderBindingInboxDrawer({
  open,
  items,
  onClose,
  onOpenItem,
  onRemove,
  onClear,
  onPauseAll,
  onTogglePause,
}: FolderBindingInboxDrawerProps) {
  if (!open) return null;

  const btnClass =
    "px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors hover:bg-white/[0.06]";

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-black/50"
        aria-label="닫기"
        onClick={onClose}
      />
      <aside
        className={cn(
          "fixed top-0 right-0 z-50 h-full w-full max-w-md",
          "border-l border-white/[0.08] bg-bg-panel shadow-2xl",
          "flex flex-col",
        )}
      >
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.06] shrink-0">
          <h2 className="text-lg font-semibold text-white flex-1">폴더 연결 알림</h2>
          {items.length > 0 && (
            <>
              <button type="button" className={cn(btnClass, "border-white/10 text-slate-300")} onClick={() => void onPauseAll()}>
                목록 감시 중지
              </button>
              <button type="button" className={cn(btnClass, "border-white/10 text-slate-300")} onClick={() => void onClear()}>
                모두 지우기
              </button>
            </>
          )}
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/[0.06]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="px-5 py-3 text-sm text-slate-400 border-b border-white/[0.06] shrink-0">
          저장된 폴더가 없어진 작품입니다. 항목을 열어 후보 경로를 고르거나 폴더를 직접 지정하세요.
          「감시 중지」는 이 품번에 대한 자동 재검색·후보 탐색을 끕니다(DB 연결은 유지).
        </p>

        <div className="flex-1 overflow-y-auto app-scroll p-4 space-y-3">
          {items.length === 0 ? (
            <p className="text-center text-slate-500 py-16">대기 중인 폴더 알림이 없습니다.</p>
          ) : (
            items.map(item => (
              <div
                key={item.product_code}
                className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 space-y-2"
              >
                <p className="font-semibold text-white">{item.product_code}</p>
                <p className="text-xs text-slate-500 break-all line-clamp-3">{item.old_path || "—"}</p>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <button
                    type="button"
                    className={cn(btnClass, "bg-violet-500/20 border-violet-500/40 text-violet-100")}
                    onClick={() => onOpenItem(item)}
                  >
                    열기
                  </button>
                  <button
                    type="button"
                    className={cn(btnClass, "border-white/10 text-slate-300")}
                    onClick={() => void onRemove(item.product_code)}
                  >
                    목록 제거
                  </button>
                  <button
                    type="button"
                    className={cn(btnClass, "border-white/10 text-slate-300")}
                    onClick={() => void onTogglePause(item.product_code, item.monitoring_paused)}
                  >
                    {item.monitoring_paused ? "감시 재개" : "감시 중지"}
                  </button>
                  {item.candidates.length > 0 && (
                    <span className="text-xs text-slate-500 ml-auto">후보 {item.candidates.length}건</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </aside>
    </>
  );
}
