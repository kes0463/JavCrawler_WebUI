import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bell, BookOpen, FolderOpen, FolderX, Heart, ImagePlus, Link2, Pause, Pencil, Play, RefreshCw, Save, Upload, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/contexts/ToastContext";
import { useNavigation } from "@/contexts/NavigationContext";
import {
  bindLibraryFolder,
  clearLibraryFolder,
  coverUrl,
  fetchLibraryCoverFromUrl,
  fetchLibraryDetail,
  hasRealLibraryMetadata,
  openLibraryFolder,
  updateLibraryItem,
  uploadLibraryCover,
} from "@/api/library";
import type { LibraryItemDetail, LibraryItemUpdate } from "@/api/library";
import { pickFoldersDialog, recrawlProducts } from "@/api/harvest";
import { pauseFolderMonitoring, resumeFolderMonitoring } from "@/api/folderWatch";
import { useFolderWatch } from "@/contexts/FolderWatchContext";
import { ActorCommaAutocompleteField } from "@/components/library/ActorCommaAutocompleteField";
import { CoverLightbox } from "@/components/library/CoverLightbox";
import { SnapshotGallery } from "@/components/library/SnapshotGallery";

interface LibraryDetailPanelProps {
  code: string;
  onClose: () => void;
  onPlay: () => void;
  onActorClick?: (name: string) => void | Promise<void>;
  onSaved?: (detail: LibraryItemDetail) => void;
}

function EditField({
  label,
  value,
  onChange,
  rows = 1,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  const className =
    "w-full rounded-lg bg-white/[0.06] border border-white/[0.12] px-3 py-2 text-lg text-[#ececf4] focus:outline-none focus:border-violet-400/50";
  return (
    <label className="block">
      <span className="text-slate-400 text-base mb-1 block">{label}</span>
      {rows > 1 ? (
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          rows={rows}
          className={cn(className, "resize-y min-h-[5rem]")}
        />
      ) : (
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          className={className}
        />
      )}
    </label>
  );
}

function ActorNamesRow({
  label,
  value,
  onNameClick,
}: {
  label: string;
  value?: string | null;
  onNameClick: (name: string) => void;
}) {
  if (!value) return null;
  const names = value.split(",").map(s => s.trim()).filter(Boolean);
  return (
    <div className="leading-relaxed">
      <span className="text-slate-400">{label}: </span>
      <span className="inline-flex flex-wrap gap-x-1 gap-y-1">
        {names.map((name, i) => (
          <span key={`${name}-${i}`}>
            <button
              type="button"
              onClick={() => onNameClick(name)}
              className="text-violet-300 hover:text-violet-200 hover:underline underline-offset-2"
            >
              {name}
            </button>
            {i < names.length - 1 && <span className="text-[#ececf4]">, </span>}
          </span>
        ))}
      </span>
    </div>
  );
}

function InfoRow({ label, value, mono = false }: { label: string; value?: string | null; mono?: boolean }) {
  if (!value) return null;
  return (
    <div className="leading-relaxed">
      <span className="text-slate-400">{label}: </span>
      <span className={cn("text-[#ececf4]", mono && "font-mono text-lg break-all")}>{value}</span>
    </div>
  );
}

function detailToDraft(detail: LibraryItemDetail): LibraryItemUpdate {
  return {
    title_ko: detail.title_ko ?? "",
    title_ja: detail.title_ja ?? "",
    title_en: detail.title_en ?? "",
    synopsis_ko: detail.synopsis_ko ?? "",
    synopsis_ja: detail.synopsis_ja ?? "",
    actors_ko: detail.actors_ko ?? "",
    actors_ja: detail.actors_ja ?? "",
    actors_romaji: detail.actors_romaji ?? "",
    genres_ko: detail.genres_ko ?? "",
    genres_ja: detail.genres_ja ?? "",
    maker_ko: detail.maker_ko ?? "",
    maker_ja: detail.maker_ja ?? "",
    release_date: detail.release_date ?? "",
  };
}

function FolderBindingSection({
  folderPath,
  folderDraft,
  onDraftChange,
  binding,
  monitoringPaused,
  monitoringToggling,
  bindingPending,
  onPick,
  onBind,
  onForceBind,
  onClear,
  onOpenFolder,
  onToggleMonitoring,
  onOpenBindingReview,
}: {
  folderPath: string | null | undefined;
  folderDraft: string;
  onDraftChange: (v: string) => void;
  binding: boolean;
  monitoringPaused?: boolean;
  monitoringToggling?: boolean;
  bindingPending?: boolean;
  onPick: () => void;
  onBind: () => void;
  onForceBind: () => void;
  onClear: () => void;
  onOpenFolder: () => void;
  onToggleMonitoring?: () => void;
  onOpenBindingReview?: () => void;
}) {
  const linked = !!(folderPath && folderPath.trim());
  const btnClass =
    "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm font-medium transition-colors disabled:opacity-50";
  return (
    <div className="rounded-xl border border-white/[0.10] bg-white/[0.03] p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <FolderOpen className="w-5 h-5 text-indigo-300 shrink-0" />
        <span className="text-base font-semibold text-slate-200">폴더 연동</span>
        {linked ? (
          <span className="text-xs px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
            연결됨
          </span>
        ) : (
          <span className="text-xs px-2 py-0.5 rounded-md bg-orange-500/15 text-orange-300 border border-orange-500/30">
            미연결
          </span>
        )}
        {monitoringPaused && (
          <span className="text-xs px-2 py-0.5 rounded-md bg-slate-500/15 text-slate-300 border border-slate-500/30">
            감시 중지됨
          </span>
        )}
      </div>

      {bindingPending && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 flex flex-wrap items-center gap-2">
          <Bell className="w-4 h-4 text-amber-300 shrink-0" />
          <p className="text-sm text-amber-100/90 flex-1 min-w-[12rem]">
            저장된 폴더를 찾을 수 없습니다. 후보 경로를 확인하세요.
          </p>
          {onOpenBindingReview && (
            <button
              type="button"
              onClick={onOpenBindingReview}
              className={cn(btnClass, "bg-amber-500/20 border-amber-500/40 text-amber-100 hover:bg-amber-500/30")}
            >
              폴더 확인…
            </button>
          )}
        </div>
      )}
      <input
        type="text"
        value={folderDraft}
        onChange={e => onDraftChange(e.target.value)}
        placeholder="D:\Media\ABC-123"
        className="w-full rounded-lg bg-white/[0.06] border border-white/[0.12] px-3 py-2 text-sm font-mono text-[#ececf4] focus:outline-none focus:border-violet-400/50"
      />
      {linked && folderPath && (
        <p className="text-xs text-slate-500 break-all">현재: {folderPath}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={binding}
          onClick={onPick}
          className={cn(btnClass, "bg-violet-500/20 border-violet-500/40 text-violet-100 hover:bg-violet-500/30")}
        >
          <FolderOpen className="w-4 h-4" />
          찾아보기
        </button>
        <button
          type="button"
          disabled={binding || !linked}
          onClick={onOpenFolder}
          className={cn(btnClass, "bg-indigo-500/20 border-indigo-500/40 text-indigo-100 hover:bg-indigo-500/30")}
        >
          <FolderOpen className="w-4 h-4" />
          폴더 열기
        </button>
        <button
          type="button"
          disabled={binding || !folderDraft.trim()}
          onClick={onBind}
          className={cn(btnClass, "bg-emerald-500/20 border-emerald-500/40 text-emerald-100 hover:bg-emerald-500/30")}
        >
          <Link2 className="w-4 h-4" />
          연결
        </button>
        <button
          type="button"
          disabled={binding || !folderDraft.trim()}
          onClick={onForceBind}
          className={cn(btnClass, "bg-amber-500/15 border-amber-500/35 text-amber-100 hover:bg-amber-500/25")}
        >
          강제 연결
        </button>
        <button
          type="button"
          disabled={binding || !linked}
          onClick={onClear}
          className={cn(btnClass, "bg-white/5 border-white/15 text-slate-300 hover:bg-white/10")}
        >
          <FolderX className="w-4 h-4" />
          해제
        </button>
        {linked && onToggleMonitoring && (
          <button
            type="button"
            disabled={binding || monitoringToggling}
            onClick={onToggleMonitoring}
            className={cn(btnClass, "bg-slate-500/15 border-slate-500/35 text-slate-200 hover:bg-slate-500/25")}
          >
            <Pause className="w-4 h-4" />
            {monitoringPaused ? "감시 재개" : "감시 중지"}
          </button>
        )}
      </div>
    </div>
  );
}

export function LibraryDetailPanel({
  code,
  onClose,
  onPlay,
  onActorClick,
  onSaved,
}: LibraryDetailPanelProps) {
  const { showToast } = useToast();
  const { openActressByName } = useNavigation();
  const { refreshInbox, openReviewForCode, isBindingPending } = useFolderWatch();
  const [detail, setDetail] = useState<LibraryItemDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [recrawling, setRecrawling] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editDraft, setEditDraft] = useState<LibraryItemUpdate>({});
  const [coverOk, setCoverOk] = useState(true);
  const [coverEpoch, setCoverEpoch] = useState(0);
  const [coverUploading, setCoverUploading] = useState(false);
  const [coverDragOver, setCoverDragOver] = useState(false);
  const [folderBinding, setFolderBinding] = useState(false);
  const [folderDraft, setFolderDraft] = useState("");
  const [monitoringToggling, setMonitoringToggling] = useState(false);
  const [coverLightboxOpen, setCoverLightboxOpen] = useState(false);
  const [snapshotStackOpen, setSnapshotStackOpen] = useState(false);
  const coverInputRef = useRef<HTMLInputElement>(null);
  const recrawlPollRef = useRef<number | null>(null);
  const backdropCloseReadyRef = useRef(false);

  const handleActorClick = useCallback(async (name: string) => {
    try {
      if (onActorClick) {
        await onActorClick(name);
      } else {
        onClose();
        await openActressByName(name);
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "배우 정보를 불러오지 못했습니다.", "error");
    }
  }, [onActorClick, onClose, openActressByName, showToast]);

  useEffect(() => {
    backdropCloseReadyRef.current = false;
    const timer = window.setTimeout(() => {
      backdropCloseReadyRef.current = true;
    }, 0);
    setLoading(true);
    setEditMode(false);
    setCoverOk(true);
    setCoverEpoch(0);
    setCoverLightboxOpen(false);
    fetchLibraryDetail(code)
      .then(d => {
        setDetail(d);
        setFolderDraft(d.folder_path ?? "");
      })
      .finally(() => setLoading(false));
    return () => window.clearTimeout(timer);
  }, [code]);

  const handleBackdropClose = useCallback(() => {
    if (!backdropCloseReadyRef.current) return;
    if (editMode || coverLightboxOpen || snapshotStackOpen) return;
    onClose();
  }, [coverLightboxOpen, editMode, onClose, snapshotStackOpen]);

  const applyCoverUpdate = useCallback((updated: LibraryItemDetail) => {
    setDetail(updated);
    setCoverOk(true);
    setCoverEpoch(Date.now());
    onSaved?.(updated);
  }, [onSaved]);

  const uploadCoverFile = useCallback(async (file: File) => {
    if (!file.type.startsWith("image/")) {
      showToast("이미지 파일만 업로드할 수 있습니다.", "error");
      return;
    }
    setCoverUploading(true);
    try {
      const res = await uploadLibraryCover(code, file);
      if (res.detail) {
        applyCoverUpdate(res.detail);
      } else {
        setCoverOk(true);
        setCoverEpoch(Date.now());
        setDetail(await fetchLibraryDetail(code));
      }
      showToast("표지가 저장되었습니다.", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "표지 업로드 실패", "error");
    } finally {
      setCoverUploading(false);
      setCoverDragOver(false);
    }
  }, [applyCoverUpdate, code, showToast]);

  const handleCoverFetchUrl = useCallback(async () => {
    setCoverUploading(true);
    try {
      const res = await fetchLibraryCoverFromUrl(code);
      if (res.detail) {
        applyCoverUpdate(res.detail);
      } else {
        setCoverOk(true);
        setCoverEpoch(Date.now());
        setDetail(await fetchLibraryDetail(code));
      }
      showToast("표지를 다운로드했습니다.", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "표지 다운로드 실패", "error");
    } finally {
      setCoverUploading(false);
    }
  }, [applyCoverUpdate, code, showToast]);

  useEffect(() => {
    return () => {
      if (recrawlPollRef.current != null) {
        window.clearInterval(recrawlPollRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && coverLightboxOpen) {
        setCoverLightboxOpen(false);
        return;
      }
      if (e.key === "Escape" && snapshotStackOpen) {
        return;
      }
      if (e.key === "Escape" && !editMode) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, editMode, coverLightboxOpen, snapshotStackOpen]);

  const detailHasMeta = detail ? hasRealLibraryMetadata(detail) : false;

  const startEdit = () => {
    if (!detail) return;
    setEditDraft(detailToDraft(detail));
    setFolderDraft(detail.folder_path ?? "");
    setEditMode(true);
  };

  const applyDetailUpdate = useCallback((updated: LibraryItemDetail) => {
    setDetail(updated);
    setFolderDraft(updated.folder_path ?? "");
    onSaved?.(updated);
  }, [onSaved]);

  const bindFolder = useCallback(async (folderPath: string, force = false) => {
    const path = folderPath.trim();
    if (!path) {
      showToast("연결할 폴더 경로를 입력하거나 선택하세요.", "error");
      return;
    }
    setFolderBinding(true);
    try {
      const res = await bindLibraryFolder(code, path, force);
      if (res.detail) {
        applyDetailUpdate(res.detail);
      } else {
        setDetail(await fetchLibraryDetail(code));
      }
      showToast(
        force ? `강제 연결됨: ${res.path ?? path}` : `폴더가 연결되었습니다.`,
        force ? "warn" : "success",
      );
      void refreshInbox();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "폴더 연결 실패", "error");
    } finally {
      setFolderBinding(false);
    }
  }, [applyDetailUpdate, code, refreshInbox, showToast]);

  const handlePickFolder = useCallback(async () => {
    try {
      const paths = await pickFoldersDialog();
      if (!paths.length) return;
      setFolderDraft(paths[0]);
      await bindFolder(paths[0], false);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "폴더 선택 실패", "error");
    }
  }, [bindFolder, showToast]);

  const handleClearFolder = useCallback(async () => {
    setFolderBinding(true);
    try {
      const res = await clearLibraryFolder(code);
      if (res.detail) {
        applyDetailUpdate(res.detail);
      } else {
        const refreshed = await fetchLibraryDetail(code);
        setDetail(refreshed);
        setFolderDraft("");
      }
      showToast("폴더 연결이 해제되었습니다.", "success");
      void refreshInbox();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "연결 해제 실패", "error");
    } finally {
      setFolderBinding(false);
    }
  }, [applyDetailUpdate, code, refreshInbox, showToast]);

  const handleToggleMonitoring = useCallback(async () => {
    if (!detail) return;
    const paused = !!detail.folder_monitoring_paused;
    setMonitoringToggling(true);
    try {
      await (paused ? resumeFolderMonitoring(code) : pauseFolderMonitoring(code));
      setDetail(prev =>
        prev ? { ...prev, folder_monitoring_paused: !paused } : prev,
      );
      void refreshInbox();
      showToast(
        paused ? `${code} — 폴더 감시를 재개했습니다.` : `${code} — 폴더 감시를 중지했습니다.`,
        "info",
      );
    } catch (e) {
      showToast(e instanceof Error ? e.message : "감시 설정 변경 실패", "error");
    } finally {
      setMonitoringToggling(false);
    }
  }, [code, detail, refreshInbox, showToast]);

  const handleOpenBindingReview = useCallback(() => {
    void openReviewForCode(code);
  }, [code, openReviewForCode]);

  const handleOpenFolder = useCallback(async () => {
    try {
      const res = await openLibraryFolder(code);
      showToast(`폴더 열림: ${res.path ?? detail?.folder_path ?? code}`, "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "폴더 열기 실패", "error");
    }
  }, [code, detail?.folder_path, showToast]);

  const folderBindingProps = {
    folderPath: detail?.folder_path,
    folderDraft,
    onDraftChange: setFolderDraft,
    binding: folderBinding,
    monitoringPaused: !!detail?.folder_monitoring_paused,
    monitoringToggling,
    bindingPending: isBindingPending(code) || !!detail?.folder_binding_pending,
    onPick: () => void handlePickFolder(),
    onBind: () => void bindFolder(folderDraft, false),
    onForceBind: () => void bindFolder(folderDraft, true),
    onClear: () => void handleClearFolder(),
    onOpenFolder: () => void handleOpenFolder(),
    onToggleMonitoring: () => void handleToggleMonitoring(),
    onOpenBindingReview: () => handleOpenBindingReview(),
  };

  const saveEdit = async () => {
    setSaving(true);
    try {
      const updated = await updateLibraryItem(code, editDraft);
      setDetail(updated);
      setEditMode(false);
      onSaved?.(updated);
      showToast("작품 정보가 저장되었습니다.", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "저장 실패", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleRecrawl = useCallback(async () => {
    setRecrawling(true);
    try {
      const res = await recrawlProducts([code], true);
      const added = res.planned ?? 0;
      const alreadyRunning = res.items.some(
        i => i.product_code?.toUpperCase() === code.toUpperCase() && i.status === "running",
      );
      if (added > 0) {
        showToast(`${code} 재크롤 시작`, "success");
      } else if (alreadyRunning) {
        showToast(`${code} 이미 수집 중입니다`, "info");
      } else {
        showToast(`${code} 재크롤 큐에 추가됨`, "success");
      }
      if (recrawlPollRef.current != null) {
        window.clearInterval(recrawlPollRef.current);
      }
      let attempts = 0;
      recrawlPollRef.current = window.setInterval(async () => {
        attempts += 1;
        if (attempts > 24) {
          if (recrawlPollRef.current != null) window.clearInterval(recrawlPollRef.current);
          recrawlPollRef.current = null;
          return;
        }
        try {
          const refreshed = await fetchLibraryDetail(code);
          setDetail(refreshed);
          onSaved?.(refreshed);
        } catch {
          /* ignore */
        }
      }, 5000);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "재크롤 실패", "error");
    } finally {
      setRecrawling(false);
    }
  }, [code, onSaved, showToast]);

  const patchDraft = (patch: Partial<LibraryItemUpdate>) => {
    setEditDraft(d => ({ ...d, ...patch }));
  };

  return createPortal(
    <div
      data-modal-overlay
      className="fixed inset-0 z-[110] flex items-center justify-center p-3 lg:p-4 bg-black/70 backdrop-blur-sm animate-fade-in"
      onMouseDown={e => {
        if (e.target === e.currentTarget) handleBackdropClose();
      }}
    >
      <GlassCard
        variant="strong"
        className="relative w-full max-w-[min(1720px,98vw)] max-h-[94vh] overflow-hidden animate-scale-in !p-6 lg:!p-8 flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="absolute top-4 right-4 flex items-center gap-1 z-10">
          {detail && !loading && !editMode && (
            <button
              type="button"
              onClick={startEdit}
              className="w-10 h-10 rounded-full bg-white/[0.08] hover:bg-white/[0.14] flex items-center justify-center transition-colors"
              aria-label="편집"
            >
              <Pencil className="w-5 h-5" />
            </button>
          )}
          {editMode && (
            <>
              <button
                type="button"
                onClick={saveEdit}
                disabled={saving}
                className="w-10 h-10 rounded-full bg-emerald-500/20 hover:bg-emerald-500/30 flex items-center justify-center transition-colors disabled:opacity-50"
                aria-label="저장"
              >
                <Save className="w-5 h-5 text-emerald-300" />
              </button>
              <button
                type="button"
                onClick={() => setEditMode(false)}
                className="w-10 h-10 rounded-full bg-white/[0.08] hover:bg-white/[0.14] flex items-center justify-center transition-colors"
                aria-label="편집 취소"
              >
                <X className="w-5 h-5" />
              </button>
            </>
          )}
          {!editMode && (
            <button
              type="button"
              onClick={onClose}
              className="w-10 h-10 rounded-full bg-white/[0.08] hover:bg-white/[0.14] flex items-center justify-center transition-colors"
              aria-label="닫기"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {loading ? (
          <div className="space-y-4 pr-10">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-3/4" />
          </div>
        ) : detail ? (
          <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[minmax(220px,280px)_minmax(0,1fr)_minmax(380px,44%)] gap-5 lg:gap-8 pr-14 lg:min-h-[calc(94vh-5rem)]">
            <div className="shrink-0 mx-auto lg:mx-0 w-full max-w-[280px] lg:max-w-none">
              <div
                className={cn(
                  "relative rounded-xl bg-[#0a0a12] flex items-center justify-center overflow-hidden min-h-[200px]",
                  coverDragOver && "ring-2 ring-violet-400/70",
                )}
                onDragOver={e => {
                  if (editMode) return;
                  e.preventDefault();
                  setCoverDragOver(true);
                }}
                onDragLeave={() => setCoverDragOver(false)}
                onDrop={e => {
                  if (editMode) return;
                  e.preventDefault();
                  setCoverDragOver(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file) void uploadCoverFile(file);
                }}
              >
                {coverOk ? (
                  <button
                    type="button"
                    onClick={() => !editMode && setCoverLightboxOpen(true)}
                    disabled={editMode}
                    className={cn(
                      "w-full block",
                      !editMode && "cursor-zoom-in group",
                    )}
                    aria-label="표지 확대"
                  >
                    <img
                      src={coverUrl(detail.product_code, coverEpoch || undefined)}
                      alt={detail.product_code}
                      draggable={false}
                      onError={() => setCoverOk(false)}
                      className={cn(
                        "w-full h-auto block object-contain max-h-[min(58vh,420px)]",
                        !editMode && "transition-transform group-hover:scale-[1.02]",
                      )}
                    />
                  </button>
                ) : (
                  <div className="flex flex-col items-center justify-center gap-3 p-6 text-center">
                    <ImagePlus className="w-12 h-12 text-slate-500" />
                    <p className="text-lg text-slate-400">표지 없음</p>
                  </div>
                )}
                {!editMode && (
                  <div className="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/80 to-transparent flex flex-wrap gap-2 justify-center">
                    <button
                      type="button"
                      disabled={coverUploading}
                      onClick={() => coverInputRef.current?.click()}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-violet-500/25 border border-violet-500/40 text-violet-100 text-sm font-medium hover:bg-violet-500/35 disabled:opacity-50"
                    >
                      <Upload className="w-4 h-4" />
                      {coverOk ? "표지 변경" : "표지 추가"}
                    </button>
                    {!coverOk && detail.cover_image_url && (
                      <button
                        type="button"
                        disabled={coverUploading}
                        onClick={() => void handleCoverFetchUrl()}
                        className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-slate-200 text-sm font-medium hover:bg-white/15 disabled:opacity-50"
                      >
                        <RefreshCw className={cn("w-4 h-4", coverUploading && "animate-spin")} />
                        URL에서 받기
                      </button>
                    )}
                  </div>
                )}
                <input
                  ref={coverInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={e => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (file) void uploadCoverFile(file);
                  }}
                />
              </div>
              <div className="mt-2 space-y-2">
                {(detail.scene_count ?? 0) > 0 && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-violet-500/15 border border-violet-500/30 text-violet-200">
                    <BookOpen className="w-6 h-6 shrink-0" />
                    <span className="text-lg font-semibold">씬 {detail.scene_count}개</span>
                  </div>
                )}
                {(Number(detail.favorite_score) || 0) > 0 && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/25 text-rose-300">
                    <Heart className="w-6 h-6 shrink-0 fill-current" />
                    <span className="text-lg font-semibold tabular-nums">
                      {Number(detail.favorite_score).toLocaleString()}
                    </span>
                  </div>
                )}
                {detail.metadata_manual && (
                  <div className="px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/25 text-amber-200 text-sm text-center">
                    수동 편집됨 · 재크롤 실패 시 보호
                  </div>
                )}
                {detail.has_hardcoded_subtitle && (
                  <div className="px-3 py-2 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-200 text-lg font-semibold text-center">
                    자체자막
                  </div>
                )}
                {detail.has_mosaic_removed && (
                  <div className="px-3 py-2 rounded-lg bg-cyan-400/10 border border-cyan-400/30 text-cyan-300 text-lg font-semibold text-center">
                    모자이크 제거
                  </div>
                )}
                {detail.has_subtitle && (
                  <div className="px-3 py-2 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-200 text-lg font-semibold text-center">
                    자막
                  </div>
                )}
              </div>
              {!editMode && (
                <SnapshotGallery
                  className="mt-3"
                  productCode={detail.product_code}
                  count={detail.snapshot_count ?? 0}
                  onStackOpenChange={setSnapshotStackOpen}
                />
              )}
            </div>

            <div className="flex flex-col min-h-0 min-w-0 overflow-y-auto">
              {!editMode && (
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <button
                    type="button"
                    onClick={onPlay}
                    className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-emerald-500/20 border border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/30 transition-colors text-xl font-semibold"
                  >
                    <Play className="w-6 h-6" />
                    재생
                  </button>
                  <button
                    type="button"
                    onClick={handleRecrawl}
                    disabled={recrawling}
                    className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-violet-500/15 border border-violet-500/35 text-violet-200 hover:bg-violet-500/25 transition-colors text-xl font-semibold disabled:opacity-50"
                  >
                    <RefreshCw className={cn("w-6 h-6", recrawling && "animate-spin")} />
                    재크롤
                  </button>
                </div>
              )}

              <p className="text-4xl font-mono font-bold text-indigo-400">{detail.product_code}</p>

              {editMode ? (
                <div className="mt-4 space-y-3">
                  <EditField
                    label="제목 (한국어)"
                    value={editDraft.title_ko ?? ""}
                    onChange={v => patchDraft({ title_ko: v })}
                  />
                  <EditField
                    label="제목 (일본어)"
                    value={editDraft.title_ja ?? ""}
                    onChange={v => patchDraft({ title_ja: v })}
                  />
                  <ActorCommaAutocompleteField
                    label="배우 (한국어, 쉼표 구분 · 자동완성)"
                    actorsKo={editDraft.actors_ko ?? ""}
                    actorsJa={editDraft.actors_ja ?? ""}
                    onChange={patch => patchDraft(patch)}
                  />
                  <EditField
                    label="배우 (일본어, 쉼표 구분)"
                    value={editDraft.actors_ja ?? ""}
                    onChange={v => patchDraft({ actors_ja: v })}
                  />
                  <EditField
                    label="장르 (한국어)"
                    value={editDraft.genres_ko ?? ""}
                    onChange={v => patchDraft({ genres_ko: v })}
                  />
                  <EditField
                    label="장르 (일본어)"
                    value={editDraft.genres_ja ?? ""}
                    onChange={v => patchDraft({ genres_ja: v })}
                  />
                  <EditField
                    label="제작사 (한국어)"
                    value={editDraft.maker_ko ?? ""}
                    onChange={v => patchDraft({ maker_ko: v })}
                  />
                  <EditField
                    label="제작사 (일본어)"
                    value={editDraft.maker_ja ?? ""}
                    onChange={v => patchDraft({ maker_ja: v })}
                  />
                  <EditField
                    label="발매일"
                    value={editDraft.release_date ?? ""}
                    onChange={v => patchDraft({ release_date: v })}
                  />
                  <EditField
                    label="시놉시스 (한국어)"
                    value={editDraft.synopsis_ko ?? ""}
                    onChange={v => patchDraft({ synopsis_ko: v })}
                    rows={5}
                  />
                  <EditField
                    label="시놉시스 (일본어)"
                    value={editDraft.synopsis_ja ?? ""}
                    onChange={v => patchDraft({ synopsis_ja: v })}
                    rows={5}
                  />
                  <FolderBindingSection {...folderBindingProps} />
                </div>
              ) : (
                <>
                  <h2 className="text-3xl font-semibold text-white leading-snug mt-2">
                    {detailHasMeta ? (detail.title_ko || detail.title_ja || "—") : "미수집"}
                  </h2>
                  {detailHasMeta && detail.title_ja && detail.title_ko && (
                    <p className="text-2xl text-slate-300 mt-1.5 leading-snug line-clamp-3">{detail.title_ja}</p>
                  )}

                  <div className="mt-4 space-y-2.5 text-xl">
                    <ActorNamesRow
                      label="배우"
                      value={detail.actors_ko || detail.actors_ja}
                      onNameClick={handleActorClick}
                    />
                    <InfoRow label="장르" value={detail.genres_ko || detail.genres_ja} />
                    <InfoRow label="제작사" value={detail.maker_ko || detail.maker_ja} />
                    <InfoRow label="발매일" value={detail.release_date} />
                    <InfoRow label="폴더" value={detail.folder_path} mono />
                  </div>

                  <div className="mt-4">
                    <FolderBindingSection {...folderBindingProps} />
                  </div>

                  {(detail.overall_summary || detail.synopsis_ko || detail.synopsis_ja) && (
                    <div className="mt-5 flex-1 min-h-0">
                      <p className="text-xl font-semibold text-slate-300 mb-2">시놉시스</p>
                      <p className="text-2xl text-[#e8e8f4] leading-relaxed whitespace-pre-wrap">
                        {detail.overall_summary || detail.synopsis_ko || detail.synopsis_ja}
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>

            {!editMode && detail.scenes && detail.scenes.length > 0 ? (
              <div className="flex flex-col min-h-0 min-w-0 lg:max-h-full max-h-80 lg:border-l lg:border-white/[0.08] lg:pl-6 border-t lg:border-t-0 border-white/[0.08] pt-5 lg:pt-0">
                <p className="text-xl font-semibold text-slate-300 mb-3 shrink-0">
                  씬별 스토리{detail.scenes_source === "grok" ? " (Grok)" : ""}
                  <span className="text-slate-400 font-normal ml-2 text-lg">{detail.scenes.length}개</span>
                </p>
                <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
                  {detail.scenes.map(scene => (
                    <div
                      key={scene.scene_id}
                      className="rounded-xl border border-white/[0.10] bg-white/[0.04] p-4"
                    >
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        {scene.scene_id && (
                          <span className="text-base font-mono text-violet-300">{scene.scene_id}</span>
                        )}
                        {scene.scene_label && (
                          <span className="text-xl font-semibold text-white">{scene.scene_label}</span>
                        )}
                        {scene.time_range && (
                          <span className="text-lg font-mono text-indigo-300">{scene.time_range}</span>
                        )}
                      </div>
                      {scene.tone && (
                        <p className="text-lg text-slate-400 mb-2">{scene.tone}</p>
                      )}
                      {scene.key_tags && scene.key_tags.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-2">
                          {scene.key_tags.map(tag => (
                            <span
                              key={tag}
                              className="text-sm px-2.5 py-1 rounded-md bg-indigo-500/20 text-indigo-100 border border-indigo-500/30"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      {scene.scene_summary && (
                        <p className="text-xl text-slate-200 leading-relaxed">{scene.scene_summary}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : !editMode ? (
              <div className="hidden lg:flex items-center justify-center text-xl text-slate-500 border-l border-white/[0.06] pl-6">
                씬별 스토리 없음
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-muted-foreground text-xl">불러오기 실패</p>
        )}
      </GlassCard>

      {detail && coverOk && (
        <CoverLightbox
          open={coverLightboxOpen}
          src={coverUrl(detail.product_code, coverEpoch || undefined)}
          alt={detail.product_code}
          onClose={() => setCoverLightboxOpen(false)}
        />
      )}
    </div>,
    document.body,
  );
}
