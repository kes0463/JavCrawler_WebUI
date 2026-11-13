import { useEffect, useState } from "react";
import { MessageCircle, Sparkles } from "lucide-react";
import { fetchPersonaCard, type InsightPersonaCard } from "@/api/insight";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { useNavigation } from "@/contexts/NavigationContext";

/** 페르소나 카드 요약을 Persona Chat 프리필 메시지로 — turn_ons를 우선하고 부족하면 affinities로 채운다. */
function personaChatPrefill(card: InsightPersonaCard): string {
  const traits = [...card.turn_ons, ...card.affinities].filter(Boolean).slice(0, 3);
  const personaType = card.persona_type ? `"${card.persona_type}"` : "지금 내 취향";
  if (traits.length === 0) {
    return `내 페르소나 카드 요약이 ${personaType}인데, 이 성향 더 파고들어서 작품 추천해줘.`;
  }
  return `내 페르소나 카드에 ${personaType} 성향이고 ${traits.join(", ")} 쪽에 끌린다고 나와 있어. 이 성향 더 파고들어서 작품 추천해줘.`;
}

/** 데스크톱 앱의 AI 페르소나 카드를 웹 Insight 개요 탭에 이식한 패널. */
export function PersonaCardPanel({ refreshEpoch }: { refreshEpoch: number }) {
  const { openPersonaChat } = useNavigation();
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
      <button
        type="button"
        onClick={() => openPersonaChat({ prefillMessage: personaChatPrefill(card) })}
        className="inline-flex items-center gap-1.5 text-sm text-accent-light hover:text-white pt-1"
      >
        <MessageCircle className="w-3.5 h-3.5" />
        이 성향 더 파고들기
      </button>
    </GlassCard>
  );
}
