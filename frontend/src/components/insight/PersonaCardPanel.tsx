import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { fetchPersonaCard, type InsightPersonaCard } from "@/api/insight";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";

/** 데스크톱 앱의 AI 페르소나 카드를 웹 Insight 개요 탭에 이식한 패널. */
export function PersonaCardPanel({ refreshEpoch }: { refreshEpoch: number }) {
  const [card, setCard] = useState<InsightPersonaCard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPersonaCard(false)
      .then(data => {
        if (!cancelled) setCard(data);
      })
      .catch(() => {
        if (!cancelled) setCard(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshEpoch]);

  if (loading) {
    return (
      <GlassCard className="space-y-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </GlassCard>
    );
  }

  if (!card || !card.summary) return null;

  return (
    <GlassCard variant="accent" className="space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-accent-light" />
        <h3 className="text-base font-semibold text-white">
          {card.persona_type || "AI 취향 페르소나"}
        </h3>
        {card.stale && (
          <span className="text-xs text-amber-400 ml-1">갱신 필요 — 새로고침 시 업데이트</span>
        )}
      </div>
      <p className="text-sm text-[#d0d0e8] leading-relaxed whitespace-pre-wrap">{card.summary}</p>
      {card.drift_note && (
        <p className="text-sm text-slate-400 leading-relaxed">{card.drift_note}</p>
      )}
      {card.affinities.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {card.affinities.map(tag => (
            <span
              key={tag}
              className="text-xs px-2 py-0.5 rounded-md bg-accent/15 text-accent-light border border-accent/20"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
