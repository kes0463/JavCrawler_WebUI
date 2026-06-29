import { useEffect, useState } from "react";
import { Merge, User } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import {
  actressPhotoUrl,
  searchActresses,
  type ActressListItem,
  type ActressProfile,
} from "@/api/actress";
import { displayActressName } from "./utils";

interface MergeActressDialogProps {
  open: boolean;
  profile: ActressProfile | null;
  onClose: () => void;
  onMerge: (mergeId: number) => Promise<void>;
}

export function MergeActressDialog({
  open,
  profile,
  onClose,
  onMerge,
}: MergeActressDialogProps) {
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<ActressListItem[]>([]);
  const [merging, setMerging] = useState(false);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setCandidates([]);
      return;
    }
    if (!query.trim()) {
      setCandidates([]);
      return;
    }
    const timer = setTimeout(() => {
      searchActresses(query)
        .then(rows =>
          setCandidates(
            rows
              .filter(r => r.id !== profile?.id)
              .map(r => ({
                id: r.id,
                name_ko: r.name_ko,
                name_ja: r.name_ja,
                profile_image_url: "",
                user_score: r.user_score ?? 0,
                is_favorite: false,
                genres: "",
                work_count: 0,
              } satisfies ActressListItem)),
          ),
        )
        .catch(() => setCandidates([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [open, query, profile?.id]);

  if (!open || !profile) return null;

  const handleMerge = async (mergeId: number, name: string) => {
    if (!confirm(`"${name}" 프로필을 "${displayActressName(profile)}"에 합치시겠습니까?\n합친 프로필은 삭제됩니다.`)) {
      return;
    }
    setMerging(true);
    try {
      await onMerge(mergeId);
      onClose();
    } finally {
      setMerging(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <GlassCard className="w-full max-w-md p-5 space-y-4">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Merge className="w-5 h-5" /> 배우 합치기
        </h2>
        <p className="text-sm text-slate-400">
          현재 프로필: <span className="text-white">{displayActressName(profile)}</span>
        </p>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="합칠 배우 검색…"
          className="w-full px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm"
          autoFocus
        />
        <div className="max-h-64 overflow-y-auto space-y-1">
          {candidates.map(c => (
            <button
              key={c.id}
              type="button"
              disabled={merging}
              onClick={() => handleMerge(c.id, displayActressName(c))}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/5 text-left disabled:opacity-50"
            >
              <div className="w-10 h-12 rounded overflow-hidden bg-black/30 shrink-0">
                {c.profile_image_url ? (
                  <img src={actressPhotoUrl(c.profile_image_url)} alt="" className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <User className="w-5 h-5 text-slate-600" />
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-medium truncate">{displayActressName(c)}</p>
                <p className="text-xs text-slate-500">작품 {c.work_count} · #{c.id}</p>
              </div>
            </button>
          ))}
          {query.trim() && candidates.length === 0 && (
            <p className="text-sm text-slate-500 text-center py-4">검색 결과 없음</p>
          )}
        </div>
        <div className="flex justify-end">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg border border-white/10">
            닫기
          </button>
        </div>
      </GlassCard>
    </div>
  );
}
