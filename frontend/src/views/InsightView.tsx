import { TrendingUp, Award, Tag, Calendar } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { ProgressIndicator } from "@/components/ui/ProgressIndicator";

// ── Mock data ────────────────────────────────────────────────────

const GENRE_STATS = [
  { label: "단독 작품",  count: 842, pct: 100 },
  { label: "레즈비언",   count: 721, pct: 86 },
  { label: "OL",        count: 598, pct: 71 },
  { label: "미소녀",     count: 487, pct: 58 },
  { label: "코스플레이", count: 364, pct: 43 },
  { label: "하렘",       count: 291, pct: 35 },
  { label: "교복",       count: 244, pct: 29 },
  { label: "간호사",     count: 198, pct: 24 },
];

const TOP_ACTORS = [
  { name: "葵いぶき",  count: 47, score: 4.8 },
  { name: "天使もえ",  count: 43, score: 4.7 },
  { name: "桃乃木かな", count: 38, score: 4.6 },
  { name: "深田えいみ", count: 35, score: 4.5 },
  { name: "河合あすな", count: 31, score: 4.4 },
];

const MONTHLY = [
  { month: "11월", count: 124 },
  { month: "12월", count: 189 },
  { month: "1월",  count: 143 },
  { month: "2월",  count: 201 },
  { month: "3월",  count: 178 },
  { month: "4월",  count: 212 },
];

const MONTHLY_MAX = Math.max(...MONTHLY.map(m => m.count));

const LABEL_STATS = [
  { label: "SOD",    count: 312, color: "bg-indigo-500" },
  { label: "Faleno", count: 287, color: "bg-violet-500" },
  { label: "S1",     count: 264, color: "bg-rose-500" },
  { label: "Idea Pocket", count: 198, color: "bg-amber-500" },
  { label: "Moodyz", count: 176, color: "bg-emerald-500" },
];

// ── Component ────────────────────────────────────────────────────

export default function InsightView() {
  return (
    <div className="space-y-5 animate-fade-in">

      <div>
        <h1 className="text-xl font-bold text-white">인사이트</h1>
        <p className="text-sm text-muted-foreground mt-0.5">라이브러리 분석 · 통계</p>
      </div>

      {/* ── 상단 요약 ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "전체 작품",   value: "2,847", sub: "총 수집량",    icon: "📚", color: "text-white" },
          { label: "평균 평점",   value: "4.2",   sub: "★ 기준",      icon: "⭐", color: "text-amber-400" },
          { label: "배우 수",     value: "1,204", sub: "고유 배우",    icon: "👤", color: "text-indigo-400" },
          { label: "이번 달 수집", value: "212",  sub: "4월 기준",     icon: "📅", color: "text-emerald-400" },
        ].map(({ label, value, sub, icon, color }) => (
          <GlassCard key={label} hoverable>
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className={`text-2xl font-bold tabular-nums mt-1 ${color}`}>{value}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>
              </div>
              <span className="text-2xl">{icon}</span>
            </div>
          </GlassCard>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* ── 월별 수집 추이 ── */}
        <GlassCard className="lg:col-span-2 space-y-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold text-[#d0d0e8]">월별 수집 추이</h2>
          </div>

          <div className="flex items-end gap-3 h-32">
            {MONTHLY.map(({ month, count }) => {
              const height = Math.max(8, (count / MONTHLY_MAX) * 100);
              const isMax = count === MONTHLY_MAX;
              return (
                <div key={month} className="flex-1 flex flex-col items-center gap-1.5">
                  <span className="text-[10px] text-muted-foreground tabular-nums">{count}</span>
                  <div
                    className={`w-full rounded-t-md transition-all duration-500 ${
                      isMax ? "bg-accent" : "bg-accent/40"
                    }`}
                    style={{ height: `${height}%` }}
                  />
                  <span className="text-[10px] text-muted-foreground">{month}</span>
                </div>
              );
            })}
          </div>
        </GlassCard>

        {/* ── 레이블 분포 ── */}
        <GlassCard className="space-y-3">
          <div className="flex items-center gap-2">
            <Tag className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold text-[#d0d0e8]">레이블 TOP 5</h2>
          </div>
          <div className="space-y-3">
            {LABEL_STATS.map(({ label, count, color }) => (
              <div key={label} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-[#c8c8e0]">{label}</span>
                  <span className="text-muted-foreground tabular-nums">{count}</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-white/[0.06] overflow-hidden">
                  <div
                    className={`h-full rounded-full ${color} transition-all duration-700`}
                    style={{ width: `${(count / LABEL_STATS[0].count) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* ── 장르 분포 ── */}
        <GlassCard className="space-y-3">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold text-[#d0d0e8]">장르 분포</h2>
          </div>
          <div className="space-y-2.5">
            {GENRE_STATS.map(({ label, count, pct }) => (
              <div key={label} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-[#c8c8e0]">{label}</span>
                  <span className="text-muted-foreground tabular-nums">{count}</span>
                </div>
                <ProgressIndicator value={pct} size="sm" />
              </div>
            ))}
          </div>
        </GlassCard>

        {/* ── 인기 배우 ── */}
        <GlassCard className="space-y-3">
          <div className="flex items-center gap-2">
            <Award className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold text-[#d0d0e8]">배우 TOP 5</h2>
          </div>
          <div className="space-y-2.5">
            {TOP_ACTORS.map(({ name, count, score }, i) => (
              <div key={name} className="flex items-center gap-3">
                <span className={`text-sm font-bold tabular-nums w-5 text-center ${
                  i === 0 ? "text-amber-400" : i === 1 ? "text-zinc-300" : i === 2 ? "text-orange-400" : "text-muted-foreground"
                }`}>
                  {i + 1}
                </span>
                <span className="text-sm text-[#d0d0e8] flex-1">{name}</span>
                <span className="text-xs text-muted-foreground tabular-nums">{count}편</span>
                <span className="text-xs text-amber-400 font-medium tabular-nums">★ {score}</span>
              </div>
            ))}
          </div>
        </GlassCard>

      </div>
    </div>
  );
}
