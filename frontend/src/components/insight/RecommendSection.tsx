import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import type { RecommendItem } from "@/api/insight";
import { RecommendCard } from "./RecommendCard";

const SEGMENTS = [
  { key: "next_watch" as const, label: "다음에 볼", subtitle: "취향 점수 기반" },
  { key: "hidden_gems" as const, label: "놓친 보석", subtitle: "미감상·저평가 + 취향 괴리" },
  { key: "today_recs" as const, label: "오늘", subtitle: "빠른 추천" },
  { key: "favorite_actor_picks" as const, label: "즐겨찾기 배우", subtitle: "팬십 배우 작품" },
];

interface RecommendSectionProps {
  next_watch: RecommendItem[];
  hidden_gems: RecommendItem[];
  today_recs: RecommendItem[];
  favorite_actor_picks: RecommendItem[];
  onOpen: (code: string) => void;
  onPlay?: (code: string) => void;
}

export function RecommendSection({
  next_watch,
  hidden_gems,
  today_recs,
  favorite_actor_picks,
  onOpen,
  onPlay,
}: RecommendSectionProps) {
  const [idx, setIdx] = useState(0);
  const pools = { next_watch, hidden_gems, today_recs, favorite_actor_picks };
  const seg = SEGMENTS[idx];
  const items = pools[seg.key] ?? [];

  const emptyMsg =
    idx === 0
      ? "아직 충분한 취향 데이터가 없습니다.\n영상을 시청하고 별점을 남기면 추천이 시작됩니다."
      : idx === 1
        ? "취향 데이터가 쌓이면 미감상·저평가 작품 중\n취향과 잘 맞는 보석을 찾아 드립니다."
        : "추천할 작품이 없습니다.";

  return (
    <GlassCard className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-[#d0d0e8]">추천</h2>
        <p className="text-sm text-muted-foreground">{seg.subtitle}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {SEGMENTS.map((s, i) => (
          <button
            key={s.key}
            type="button"
            onClick={() => setIdx(i)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              idx === i
                ? "bg-accent/15 border-accent/40 text-accent-light"
                : "border-white/10 text-slate-400 hover:bg-white/[0.04]"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500 whitespace-pre-line py-8 text-center">{emptyMsg}</p>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {items.map(item => (
            <RecommendCard key={item.product_code} item={item} onOpen={onOpen} onPlay={onPlay} />
          ))}
        </div>
      )}
    </GlassCard>
  );
}
