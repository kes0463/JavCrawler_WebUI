import { useEffect, useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { normalizeCupSize } from "./utils";
import type { ActressProfile } from "@/api/actress";

export type ActressCreatePayload = Partial<ActressProfile> & {
  name_ko?: string;
  name_ja?: string;
};

interface AddActressDialogProps {
  open: boolean;
  prefillName?: string | null;
  onClose: () => void;
  onCreate: (payload: ActressCreatePayload) => Promise<void>;
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
          className="mt-1 w-full rounded-lg bg-white/[0.04] border border-white/[0.08] px-3 py-2 text-sm"
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

const EMPTY = {
  name_ko: "",
  name_ja: "",
  romaji: "",
  genres: "",
  agency: "",
  cup_size: "",
  height: "",
  bust: "",
  waist: "",
  hip: "",
  birth_date: "",
  debut_date: "",
  user_score: "0",
  profile_text: "",
  memo: "",
};

export function AddActressDialog({
  open,
  prefillName,
  onClose,
  onCreate,
}: AddActressDialogProps) {
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({
      ...EMPTY,
      name_ko: prefillName || "",
    });
  }, [open, prefillName]);

  if (!open) return null;

  const set = (key: keyof typeof EMPTY) => (v: string) =>
    setForm(f => ({ ...f, [key]: v }));

  const handleSubmit = async () => {
    if (!form.name_ko.trim() && !form.name_ja.trim()) return;
    setSaving(true);
    try {
      await onCreate({
        name_ko: form.name_ko.trim(),
        name_ja: form.name_ja.trim(),
        romaji: form.romaji.trim(),
        genres: form.genres.trim(),
        agency: form.agency.trim(),
        cup_size: normalizeCupSize(form.cup_size) || undefined,
        height: parseInt(form.height, 10) || 0,
        bust: parseInt(form.bust, 10) || 0,
        waist: parseInt(form.waist, 10) || 0,
        hip: parseInt(form.hip, 10) || 0,
        birth_date: form.birth_date.trim() || undefined,
        debut_date: form.debut_date.trim() || undefined,
        user_score: parseFloat(form.user_score) || 0,
        profile_text: form.profile_text.trim(),
        memo: form.memo.trim(),
        favorite_intensity: 5,
        is_favorite: false,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <GlassCard className="w-full max-w-lg max-h-[90vh] overflow-y-auto p-5 space-y-4">
        <h2 className="text-xl font-bold">새 배우 추가</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="한국어 이름 *" value={form.name_ko} onChange={set("name_ko")} />
          <Field label="일본어 이름 *" value={form.name_ja} onChange={set("name_ja")} />
          <Field label="로마자" value={form.romaji} onChange={set("romaji")} />
          <Field label="생년월일 (YYYY-MM-DD)" value={form.birth_date} onChange={set("birth_date")} />
          <Field label="데뷔 (YYYY-MM)" value={form.debut_date} onChange={set("debut_date")} />
          <Field label="신장(cm)" value={form.height} onChange={set("height")} type="number" />
          <Field label="가슴(B)" value={form.bust} onChange={set("bust")} type="number" />
          <Field label="허리(W)" value={form.waist} onChange={set("waist")} type="number" />
          <Field label="엉덩이(H)" value={form.hip} onChange={set("hip")} type="number" />
          <Field label="컵" value={form.cup_size} onChange={set("cup_size")} />
          <Field label="소속" value={form.agency} onChange={set("agency")} />
          <Field label="장르 (쉼표 구분)" value={form.genres} onChange={set("genres")} />
          <Field label="점수" value={form.user_score} onChange={set("user_score")} type="number" />
        </div>
        <Field label="소개" value={form.profile_text} onChange={set("profile_text")} rows={3} />
        <Field label="메모" value={form.memo} onChange={set("memo")} rows={2} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg border border-white/10">
            취소
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={saving || (!form.name_ko.trim() && !form.name_ja.trim())}
            className="px-4 py-2 rounded-lg bg-violet-600 text-white disabled:opacity-40"
          >
            {saving ? "추가 중…" : "추가"}
          </button>
        </div>
      </GlassCard>
    </div>
  );
}
