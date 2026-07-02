import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import type { WeeklyDigest } from "@/api/insight";

interface WeeklyDigestBannerProps {
  digest: WeeklyDigest;
}

export function WeeklyDigestBanner({ digest }: WeeklyDigestBannerProps) {
  const [expanded, setExpanded] = useState(false);
  const hasData = !!digest.has_data;
  const lines = digest.lines ?? [];
  const showMore = hasData && lines.length > 1;
  const visible = !hasData ? [digest.empty_message ?? "이번 주 시청 이력이 없습니다."] : (showMore && !expanded ? lines.slice(0, 1) : lines);

  return (
    <GlassCard className="border-cyan-500/30 space-y-3">
      <div>
        <h2 className="text-lg font-semibold text-white">지난 주 리포트</h2>
        {digest.week_label && (
          <p className="text-sm text-muted-foreground mt-0.5">{digest.week_label}</p>
        )}
      </div>
      <div className="space-y-1.5">
        {visible.map((line, i) => (
          <p key={i} className={`text-sm ${hasData ? "text-slate-300" : "text-slate-500"}`}>
            {line}
          </p>
        ))}
      </div>
      {showMore && (
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          className="text-sm text-cyan-400 hover:text-cyan-300 underline underline-offset-2"
        >
          {expanded ? "접기" : "펼치기"}
        </button>
      )}
    </GlassCard>
  );
}
