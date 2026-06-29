import { useCallback, useEffect, useRef, useState } from "react";
import { Heart, Pencil, Save, X, Merge } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";
import { updateActress, type ActressProfile, type ActressWork } from "@/api/actress";
import { ActressGallery } from "./ActressGallery";
import { AliasManager } from "./AliasManager";
import { ActressWorksGrid } from "./ActressWorksGrid";
import {
  displayActressName,
  formatAgeLabel,
  formatBodySpec,
  normalizeCupSize,
  parseGenreTags,
} from "./utils";

interface ActressDetailPanelProps {
  profile: ActressProfile | null;
  works: ActressWork[];
  workGenres: string[];
  loading: boolean;
  onBack: () => void;
  onProfileChange: (profile: ActressProfile) => void;
  onRefresh: () => void;
  onListRefresh: () => void;
  onWorkClick: (productCode: string) => void;
  onMergeClick: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
}

function Row({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-slate-500 text-sm">{label}</span>
      <p className="text-white">{value}</p>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  rows,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  rows?: number;
}) {
  return (
    <label className="block">
      <span className="text-slate-400 text-sm">{label}</span>
      {rows ? (
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          rows={rows}
          className="mt-1 w-full rounded-lg bg-white/[0.04] border border-white/[0.08] p-2 text-sm"
        />
      ) : (
        <input
          type={type}
          value={value}
          onChange={e => onChange(e.target.value)}
          className="mt-1 w-full rounded-lg bg-white/[0.04] border border-white/[0.08] px-3 py-2 text-sm"
        />
      )}
    </label>
  );
}

export function ActressDetailPanel({
  profile,
  works,
  workGenres,
  loading,
  onBack,
  onProfileChange,
  onRefresh,
  onListRefresh,
  onWorkClick,
  onMergeClick,
  onError,
  onSuccess,
}: ActressDetailPanelProps) {
  const [editMode, setEditMode] = useState(false);
  const [editDraft, setEditDraft] = useState<Partial<ActressProfile>>({});
  const [profileText, setProfileText] = useState("");
  const [intensity, setIntensity] = useState(0);
  const profileTextTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intensityTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (profile) {
      setProfileText(profile.profile_text || "");
      setIntensity(profile.favorite_intensity ?? 0);
    }
  }, [profile?.id, profile?.profile_text, profile?.favorite_intensity]);

  useEffect(() => {
    setEditMode(false);
    setEditDraft({});
  }, [profile?.id]);

  useEffect(() => () => {
    if (profileTextTimer.current) clearTimeout(profileTextTimer.current);
    if (intensityTimer.current) clearTimeout(intensityTimer.current);
  }, []);

  const saveProfileText = useCallback(async (text: string) => {
    if (!profile) return;
    try {
      const updated = await updateActress(profile.id, { profile_text: text || null });
      onProfileChange(updated);
    } catch (e) {
      onError(String((e as Error).message || e));
    }
  }, [profile, onProfileChange, onError]);

  const saveIntensity = useCallback(async (value: number) => {
    if (!profile) return;
    try {
      const updated = await updateActress(profile.id, { favorite_intensity: value });
      onProfileChange(updated);
      onListRefresh();
    } catch (e) {
      onError(String((e as Error).message || e));
    }
  }, [profile, onProfileChange, onListRefresh, onError]);

  const handleProfileTextChange = (text: string) => {
    setProfileText(text);
    if (profileTextTimer.current) clearTimeout(profileTextTimer.current);
    profileTextTimer.current = setTimeout(() => saveProfileText(text), 1000);
  };

  const handleIntensityChange = (value: number) => {
    setIntensity(value);
    if (intensityTimer.current) clearTimeout(intensityTimer.current);
    intensityTimer.current = setTimeout(() => saveIntensity(value), 500);
  };

  const startEdit = () => {
    if (!profile) return;
    setEditDraft({ ...profile });
    setEditMode(true);
  };

  const saveEdit = async () => {
    if (!profile) return;
    try {
      const updated = await updateActress(profile.id, {
        name_ko: editDraft.name_ko,
        name_ja: editDraft.name_ja,
        romaji: editDraft.romaji,
        birth_date: editDraft.birth_date || null,
        height: editDraft.height || null,
        bust: editDraft.bust || null,
        waist: editDraft.waist || null,
        hip: editDraft.hip || null,
        cup_size: normalizeCupSize(editDraft.cup_size) || editDraft.cup_size || null,
        debut_date: editDraft.debut_date_raw || editDraft.debut_date || null,
        agency: editDraft.agency || null,
        profile_text: editDraft.profile_text || null,
        memo: editDraft.memo || null,
        genres: editDraft.genres || null,
        is_favorite: editDraft.is_favorite,
        favorite_intensity: editDraft.favorite_intensity,
        user_score: editDraft.user_score,
      });
      onProfileChange(updated);
      setProfileText(updated.profile_text || "");
      setIntensity(updated.favorite_intensity ?? 0);
      setEditMode(false);
      onListRefresh();
      onSuccess("프로필이 저장되었습니다.");
    } catch (e) {
      onError(String((e as Error).message || e));
    }
  };

  const toggleFavorite = async () => {
    if (!profile) return;
    try {
      const updated = await updateActress(profile.id, {
        is_favorite: !profile.is_favorite,
      });
      onProfileChange(updated);
      onListRefresh();
    } catch (e) {
      onError(String((e as Error).message || e));
    }
  };

  if (loading || !profile) {
    return (
      <>
        <div className="flex items-center gap-2 p-4 border-b border-white/[0.08] shrink-0">
          <Skeleton className="h-8 w-48" />
        </div>
        <div className="flex-1 overflow-y-auto p-6 space-y-4 min-h-0">
          <Skeleton className="h-48" />
          <Skeleton className="h-32" />
        </div>
      </>
    );
  }

  const ageLabel = formatAgeLabel(profile.birth_date);
  const genreTags = parseGenreTags(profile.genres, 5);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-2 p-4 border-b border-white/[0.08] shrink-0">
        <button type="button" onClick={onBack} className="lg:hidden p-2 rounded-lg hover:bg-white/5">
          <span className="text-lg">←</span>
        </button>
        <h1 className="text-2xl font-bold flex-1 truncate">{displayActressName(profile)}</h1>
        {!editMode && (
          <>
            <button type="button" onClick={toggleFavorite} title="즐겨찾기">
              <Heart className={cn("w-6 h-6", profile.is_favorite && "fill-rose-400 text-rose-400")} />
            </button>
            <button type="button" onClick={startEdit} className="p-2 rounded-lg hover:bg-white/5">
              <Pencil className="w-5 h-5" />
            </button>
            <button
              type="button"
              onClick={onMergeClick}
              className="p-2 rounded-lg hover:bg-white/5"
              title="배우 합치기"
            >
              <Merge className="w-5 h-5" />
            </button>
          </>
        )}
        {editMode && (
          <>
            <button type="button" onClick={saveEdit} className="p-2 text-emerald-300">
              <Save className="w-5 h-5" />
            </button>
            <button type="button" onClick={() => setEditMode(false)} className="p-2">
              <X className="w-5 h-5" />
            </button>
          </>
        )}
      </div>

      <div className="flex-1 overflow-y-auto app-scroll p-4 space-y-6">
        <ActressGallery
          profile={profile}
          onProfileChange={p => {
            onProfileChange(p);
            onListRefresh();
          }}
          onError={onError}
          onSuccess={onSuccess}
        />

        <div className="space-y-3 text-base">
          {editMode ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="한국어 이름" value={editDraft.name_ko ?? ""} onChange={v => setEditDraft(d => ({ ...d, name_ko: v }))} />
              <Field label="일본어 이름" value={editDraft.name_ja ?? ""} onChange={v => setEditDraft(d => ({ ...d, name_ja: v }))} />
              <Field label="로마자" value={editDraft.romaji ?? ""} onChange={v => setEditDraft(d => ({ ...d, romaji: v }))} />
              <Field label="생년월일" value={editDraft.birth_date ?? ""} onChange={v => setEditDraft(d => ({ ...d, birth_date: v }))} />
              <Field label="데뷔(YYYY-MM)" value={editDraft.debut_date_raw ?? editDraft.debut_date ?? ""} onChange={v => setEditDraft(d => ({ ...d, debut_date_raw: v }))} />
              <Field label="신장(cm)" value={String(editDraft.height ?? "")} onChange={v => setEditDraft(d => ({ ...d, height: parseInt(v, 10) || 0 }))} type="number" />
              <Field label="가슴(B)" value={String(editDraft.bust ?? "")} onChange={v => setEditDraft(d => ({ ...d, bust: parseInt(v, 10) || 0 }))} type="number" />
              <Field label="허리(W)" value={String(editDraft.waist ?? "")} onChange={v => setEditDraft(d => ({ ...d, waist: parseInt(v, 10) || 0 }))} type="number" />
              <Field label="엉덩이(H)" value={String(editDraft.hip ?? "")} onChange={v => setEditDraft(d => ({ ...d, hip: parseInt(v, 10) || 0 }))} type="number" />
              <Field label="컵" value={editDraft.cup_size ?? ""} onChange={v => setEditDraft(d => ({ ...d, cup_size: v }))} />
              <Field label="소속" value={editDraft.agency ?? ""} onChange={v => setEditDraft(d => ({ ...d, agency: v }))} />
              <Field label="장르 (쉼표 구분)" value={editDraft.genres ?? ""} onChange={v => setEditDraft(d => ({ ...d, genres: v }))} />
              <Field label="점수" value={String(editDraft.user_score ?? 0)} onChange={v => setEditDraft(d => ({ ...d, user_score: parseFloat(v) || 0 }))} type="number" />
              <div className="sm:col-span-2">
                <Field label="소개" value={editDraft.profile_text ?? ""} onChange={v => setEditDraft(d => ({ ...d, profile_text: v }))} rows={4} />
              </div>
              <div className="sm:col-span-2">
                <Field label="메모" value={editDraft.memo ?? ""} onChange={v => setEditDraft(d => ({ ...d, memo: v }))} rows={3} />
              </div>
            </div>
          ) : (
            <>
              <Row label="일본어" value={profile.name_ja} />
              <Row label="로마자" value={profile.romaji} />
              <Row label="생년월일" value={profile.birth_date ? `${profile.birth_date}${ageLabel ? ` (${ageLabel})` : ""}` : undefined} />
              <Row label="신체" value={formatBodySpec(profile)} />
              <Row label="데뷔" value={profile.debut_date} />
              <Row label="소속" value={profile.agency} />
              {genreTags.length > 0 && (
                <div>
                  <p className="text-slate-500 text-sm mb-1">장르</p>
                  <div className="flex flex-wrap gap-1.5">
                    {genreTags.map(g => (
                      <span key={g} className="px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-200 text-xs">{g}</span>
                    ))}
                  </div>
                </div>
              )}
              {profile.memo && (
                <div>
                  <p className="text-slate-500 text-sm">메모</p>
                  <p className="text-slate-300 whitespace-pre-wrap">{profile.memo}</p>
                </div>
              )}
            </>
          )}
        </div>

        {!editMode && (
          <>
            <label className="block space-y-2">
              <span className="text-slate-400 text-sm">소개 (자동 저장)</span>
              <textarea
                value={profileText}
                onChange={e => handleProfileTextChange(e.target.value)}
                rows={4}
                className="w-full rounded-lg bg-white/[0.04] border border-white/[0.08] p-2 text-sm text-slate-200"
                placeholder="프로필 소개를 입력하세요…"
              />
            </label>

            <label className="block space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-400 text-sm">관심도</span>
                <span className="text-violet-300 text-sm font-medium">{intensity.toFixed(1)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={10}
                step={0.5}
                value={intensity}
                onChange={e => handleIntensityChange(parseFloat(e.target.value))}
                className="w-full accent-violet-500"
              />
            </label>
          </>
        )}

        <AliasManager
          profile={profile}
          onRefresh={onRefresh}
          onError={onError}
          onSuccess={onSuccess}
        />

        <ActressWorksGrid
          works={works}
          genres={workGenres}
          onWorkClick={onWorkClick}
        />
      </div>
    </div>
  );
}
