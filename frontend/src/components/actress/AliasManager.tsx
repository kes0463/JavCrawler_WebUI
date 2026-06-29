import { useState } from "react";
import { X } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import {
  addActressAlias,
  removeActressAlias,
  type ActressAlias,
  type ActressProfile,
} from "@/api/actress";

const ALIAS_TYPES = ["stage", "old", "korean", "english", "other"] as const;

interface AliasManagerProps {
  profile: ActressProfile;
  onRefresh: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
}

export function AliasManager({
  profile,
  onRefresh,
  onError,
  onSuccess,
}: AliasManagerProps) {
  const [name, setName] = useState("");
  const [aliasType, setAliasType] = useState<string>("stage");
  const [busy, setBusy] = useState(false);

  const handleAdd = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      await addActressAlias(profile.id, trimmed, aliasType);
      setName("");
      onSuccess("별명이 추가되었습니다.");
      onRefresh();
    } catch (err) {
      onError(String((err as Error).message || err));
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (alias: ActressAlias) => {
    if (!confirm(`별명 "${alias.alias_name}"을(를) 삭제하시겠습니까?`)) return;
    setBusy(true);
    try {
      await removeActressAlias(profile.id, alias.alias_id);
      onSuccess("별명이 삭제되었습니다.");
      onRefresh();
    } catch (err) {
      onError(String((err as Error).message || err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <GlassCard className="p-4 space-y-3">
      <h3 className="text-sm font-semibold text-slate-300">
        별명 관리 ({profile.aliases.length})
      </h3>

      <div className="flex flex-wrap gap-2">
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleAdd()}
          placeholder="별명 입력 (예: みやむら れい)"
          className="flex-1 min-w-[160px] px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm"
          disabled={busy}
        />
        <select
          value={aliasType}
          onChange={e => setAliasType(e.target.value)}
          className="px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm"
          disabled={busy}
        >
          {ALIAS_TYPES.map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleAdd}
          disabled={busy || !name.trim()}
          className="px-4 py-2 rounded-lg bg-violet-600/80 text-white text-sm disabled:opacity-40"
        >
          추가
        </button>
      </div>

      {profile.aliases.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-4">
          등록된 별명이 없습니다. 검색 정확도 향상을 위해 별명을 추가하세요.
        </p>
      ) : (
        <div className="space-y-2 max-h-48 overflow-y-auto">
          {profile.aliases.map(alias => (
            <div
              key={alias.alias_id}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.06]"
            >
              <span
                className={alias.is_primary ? "font-bold text-violet-300 flex-1" : "flex-1 text-sm"}
              >
                {alias.alias_name}
              </span>
              <span className="text-xs text-slate-500">{alias.alias_type || "stage"}</span>
              <button
                type="button"
                onClick={() => handleRemove(alias)}
                disabled={busy}
                className="p-1 rounded hover:bg-rose-500/20 text-rose-300"
                title="삭제"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
