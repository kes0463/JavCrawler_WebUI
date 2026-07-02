import { useState } from "react";
import { FolderOpen, Loader2 } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { cn } from "@/lib/utils";
import { bindLibraryFolder } from "@/api/library";
import { pickFoldersDialog } from "@/api/harvest";

interface FolderBindingReviewDialogProps {
  open: boolean;
  productCode: string;
  oldPath: string;
  candidates: string[];
  onClose: () => void;
  onResolved: (productCode: string) => void | Promise<void>;
  onRescan: () => void | Promise<void>;
}

export function FolderBindingReviewDialog({
  open,
  productCode,
  oldPath,
  candidates,
  onClose,
  onResolved,
  onRescan,
}: FolderBindingReviewDialogProps) {
  const [binding, setBinding] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open || !productCode) return null;

  const bindTo = async (folderPath: string) => {
    setBinding(true);
    setError(null);
    try {
      await bindLibraryFolder(productCode, folderPath, true);
      await onResolved(productCode);
    } catch (e) {
      setError(e instanceof Error ? e.message : "폴더 연결에 실패했습니다");
    } finally {
      setBinding(false);
    }
  };

  const handlePickFolder = async () => {
    const paths = await pickFoldersDialog();
    if (paths[0]) await bindTo(paths[0]);
  };

  const handleRescan = async () => {
    setRescanning(true);
    setError(null);
    try {
      await onRescan();
    } catch (e) {
      setError(e instanceof Error ? e.message : "후보 검색 실패");
    } finally {
      setRescanning(false);
    }
  };

  const btnClass =
    "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm font-medium transition-colors disabled:opacity-50";

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
      <GlassCard className="w-full max-w-xl max-h-[90vh] overflow-y-auto p-5 space-y-4">
        <h2 className="text-xl font-bold text-white">폴더 연결 확인</h2>
        <p className="text-sm text-slate-400">
          로컬 디스크에서 품번이 폴더 이름에 포함된 위치를 검색했습니다. 목록에서 고르거나 탐색기로 직접 지정할 수 있습니다.
        </p>

        <div className="space-y-1 text-sm">
          <p>
            <span className="text-slate-400">품번 </span>
            <span className="font-semibold text-white">{productCode}</span>
          </p>
          <p className="break-all">
            <span className="text-slate-400">저장된 경로 </span>
            <span className="text-slate-200">{oldPath || "—"}</span>
          </p>
        </div>

        {candidates.length === 0 && (
          <p className="text-sm text-amber-300/90">
            자동으로 찾은 후보 경로가 없습니다. 폴더를 직접 지정해 주세요.
          </p>
        )}

        {error && <p className="text-sm text-rose-400">{error}</p>}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={rescanning || binding}
            onClick={() => void handleRescan()}
            className={cn(btnClass, "border-white/10 text-slate-300 hover:bg-white/[0.06]")}
          >
            {rescanning ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            후보 다시 검색
          </button>
          <button
            type="button"
            disabled={binding}
            onClick={() => void handlePickFolder()}
            className={cn(btnClass, "border-white/10 text-slate-300 hover:bg-white/[0.06]")}
          >
            <FolderOpen className="w-4 h-4" />
            폴더 직접 지정…
          </button>
          {candidates.length > 0 && (
            <span className="text-xs text-slate-500 self-center ml-auto">
              후보 {candidates.length}건 (유사 순)
            </span>
          )}
        </div>

        {candidates.length > 0 && (
          <div className="space-y-2 max-h-64 overflow-y-auto app-scroll">
            {candidates.map((path, idx) => (
              <button
                key={path}
                type="button"
                disabled={binding}
                onClick={() => void bindTo(path)}
                className={cn(
                  "w-full text-left px-3 py-2.5 rounded-lg border border-white/[0.08]",
                  "text-sm font-mono text-slate-200 hover:bg-white/[0.05] transition-colors",
                  "disabled:opacity-50",
                )}
              >
                {idx + 1}. 연결 → {path}
              </button>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={binding}
            className="px-4 py-2 rounded-lg border border-white/10 text-slate-300"
          >
            닫기
          </button>
        </div>
      </GlassCard>
    </div>
  );
}
