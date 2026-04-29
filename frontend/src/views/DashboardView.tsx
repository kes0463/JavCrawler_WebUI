import { BookOpen, FolderOpen, Tag, Clock, TrendingUp, Activity } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ProgressIndicator } from "@/components/ui/ProgressIndicator";
import { LogPanel, type LogEntry } from "@/components/log/LogPanel";
import { useNavigation } from "@/contexts/NavigationContext";
import { cn } from "@/lib/utils";

// ── Mock data ────────────────────────────────────────────────────

const STATS = [
  {
    label: "전체 작품",
    value: "2,847",
    delta: "+12 오늘",
    icon: BookOpen,
    valueColor: "text-white",
    iconBg: "bg-stat-zinc",
    iconColor: "text-zinc-300",
  },
  {
    label: "메타데이터 완료",
    value: "2,391",
    delta: "84%",
    icon: Tag,
    valueColor: "text-emerald-400",
    iconBg: "bg-stat-emerald",
    iconColor: "text-emerald-400",
  },
  {
    label: "폴더 연결",
    value: "1,924",
    delta: "68%",
    icon: FolderOpen,
    valueColor: "text-indigo-400",
    iconBg: "bg-stat-indigo",
    iconColor: "text-indigo-400",
  },
  {
    label: "미수집",
    value: "456",
    delta: "처리 필요",
    icon: Clock,
    valueColor: "text-amber-400",
    iconBg: "bg-stat-amber",
    iconColor: "text-amber-400",
  },
];

const QUEUE_STATS = [
  { label: "하이라이트 큐", count: 3,  status: "running" as const,  color: "text-violet-400" },
  { label: "프리뷰 큐",    count: 0,  status: "inactive" as const, color: "text-zinc-500" },
  { label: "몽타주 큐",    count: 1,  status: "pending" as const,  color: "text-amber-400" },
  { label: "모자이크 큐",  count: 12, status: "running" as const,  color: "text-rose-400" },
];

const RECENT_HARVEST = [
  { code: "STARS-001", status: "done" as const,    ts: "2분 전" },
  { code: "IPX-789",   status: "done" as const,    ts: "15분 전" },
  { code: "MIDE-456",  status: "error" as const,   ts: "34분 전" },
  { code: "SSIS-234",  status: "running" as const, ts: "진행 중" },
  { code: "MIFD-111",  status: "pending" as const, ts: "대기 중" },
];

const MOCK_LOGS: LogEntry[] = [
  { id: 1, text: "수집 완료: STARS-001 (메타데이터 + 표지)", level: "success", ts: "14:23:01" },
  { id: 2, text: "수집 완료: IPX-789", level: "success", ts: "14:08:44" },
  { id: 3, text: "수집 실패: MIDE-456 - 404 Not Found", level: "error", ts: "13:49:12" },
  { id: 4, text: "모자이크 처리 시작: SSIS-234 (job=abc12345)", level: "info", ts: "13:47:30" },
  { id: 5, text: "폴더 연결 대기: MIFD-111 후보 3개", level: "warn", ts: "13:45:00" },
  { id: 6, text: "DB 마이그레이션 v9 완료", level: "info", ts: "13:40:00" },
];

const QUICK_NAV = [
  { label: "수집 시작",  view: "harvest",    icon: "🔍", accent: "hover:border-indigo-500/30 hover:shadow-[0_0_20px_rgba(99,102,241,0.1)]" },
  { label: "전사·자막",  view: "processing", icon: "🎤", accent: "hover:border-violet-500/30 hover:shadow-[0_0_20px_rgba(139,92,246,0.1)]" },
  { label: "모자이크",   view: "mosaic",     icon: "🧩", accent: "hover:border-rose-500/30 hover:shadow-[0_0_20px_rgba(244,63,94,0.1)]" },
  { label: "라이브러리", view: "library",    icon: "📚", accent: "hover:border-emerald-500/30 hover:shadow-[0_0_20px_rgba(16,185,129,0.1)]" },
];

// ── Section header ───────────────────────────────────────────────

function SectionHeader({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <div className="w-0.5 h-3.5 rounded-full bg-accent opacity-60" />
        <h2 className="text-sm font-semibold text-[#d8d8ec]">{children}</h2>
      </div>
      {action}
    </div>
  );
}

// ── Component ────────────────────────────────────────────────────

export default function DashboardView() {
  const { navigateTo } = useNavigation();

  return (
    <div className="space-y-7 animate-fade-in max-w-[1200px]">

      {/* ── 페이지 헤더 ── */}
      <div className="pt-1">
        <h1 className="text-[22px] font-bold text-white tracking-tight">대시보드</h1>
        <p className="text-sm text-muted-foreground mt-1">JAVSTORY Pro — 전체 현황</p>
      </div>

      {/* ── 주요 통계 카드 ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        {STATS.map(({ label, value, delta, icon: Icon, valueColor, iconBg, iconColor }, i) => (
          <GlassCard
            key={label}
            hoverable
            className="space-y-4"
            style={{ animationDelay: `${i * 50}ms` }}
          >
            <div className="flex items-start justify-between">
              <span className="text-xs text-muted-foreground leading-tight">{label}</span>
              <div className={cn(
                "w-9 h-9 rounded-xl flex items-center justify-center shrink-0",
                "border border-white/[0.06]",
                iconBg,
              )}>
                <Icon className={cn("w-[17px] h-[17px]", iconColor)} />
              </div>
            </div>
            <div>
              <p className={cn("text-[26px] font-bold tabular-nums leading-none tracking-tight", valueColor)}>
                {value}
              </p>
              <p className="text-[11px] text-muted-foreground mt-1.5 flex items-center gap-1">
                <TrendingUp className="w-3 h-3 shrink-0" />
                {delta}
              </p>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* ── 수집 진행률 ── */}
      <GlassCard className="space-y-4">
        <SectionHeader>
          <span className="flex items-center gap-1.5">
            메타데이터 수집 현황
          </span>
        </SectionHeader>

        <div>
          <div className="flex justify-between text-xs text-muted-foreground mb-2">
            <span>2,391 완료</span>
            <span>전체 2,847</span>
          </div>
          <ProgressIndicator value={2391} total={2847} size="lg" />
        </div>

        <div className="grid grid-cols-3 divide-x divide-white/[0.06]">
          {[
            { pct: "84%", label: "메타 완료",   color: "text-emerald-400" },
            { pct: "68%", label: "폴더 연결",   color: "text-indigo-400" },
            { pct: "16%", label: "미수집",      color: "text-amber-400" },
          ].map(({ pct, label, color }) => (
            <div key={label} className="text-center px-4 py-1">
              <p className={cn("text-xl font-bold tabular-nums", color)}>{pct}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* ── 3단 그리드 ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 큐 현황 */}
        <GlassCard className="space-y-0">
          <SectionHeader>
            <span className="flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-muted-foreground" />
              큐 현황
            </span>
          </SectionHeader>
          <div className="space-y-1">
            {QUEUE_STATS.map(({ label, count, status, color }) => (
              <div
                key={label}
                className="flex items-center justify-between py-2 px-3 -mx-3 rounded-xl hover:bg-white/[0.03] transition-colors duration-150"
              >
                <div className="flex items-center gap-2.5">
                  <StatusBadge status={status} showDot />
                  <span className="text-xs text-[#c0c0dc]">{label}</span>
                </div>
                <span className={cn("text-sm font-bold tabular-nums", color)}>{count}</span>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* 최근 수집 */}
        <GlassCard className="space-y-0">
          <SectionHeader
            action={
              <button
                onClick={() => navigateTo("harvest")}
                className="text-[11px] text-accent-light/70 hover:text-accent-light transition-colors duration-150"
              >
                전체 보기 →
              </button>
            }
          >
            최근 수집
          </SectionHeader>
          <div className="space-y-1">
            {RECENT_HARVEST.map(({ code, status, ts }) => (
              <div
                key={code}
                className="flex items-center justify-between py-2 px-3 -mx-3 rounded-xl hover:bg-white/[0.03] transition-colors duration-150"
              >
                <div className="flex items-center gap-2.5">
                  <StatusBadge status={status} showDot />
                  <span className="font-mono text-xs text-indigo-300">{code}</span>
                </div>
                <span className="text-[11px] text-muted-foreground">{ts}</span>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* 빠른 이동 */}
        <GlassCard className="space-y-0">
          <SectionHeader>빠른 이동</SectionHeader>
          <div className="grid grid-cols-2 gap-2">
            {QUICK_NAV.map(({ label, view, icon, accent }) => (
              <button
                key={view}
                onClick={() => navigateTo(view as never)}
                className={cn(
                  "flex flex-col items-center gap-2.5 py-5 rounded-xl",
                  "bg-bg-surface border border-white/[0.06]",
                  "hover:bg-bg-hover hover:border-white/[0.12] hover:-translate-y-0.5",
                  "transition-all duration-200 ease-spring gpu",
                  "text-center",
                  accent,
                )}
              >
                <span className="text-[22px] leading-none">{icon}</span>
                <span className="text-[11px] text-[#c0c0dc] font-medium">{label}</span>
              </button>
            ))}
          </div>
        </GlassCard>

      </div>

      {/* ── 로그 ── */}
      <GlassCard className="space-y-0">
        <SectionHeader>최근 로그</SectionHeader>
        <LogPanel entries={MOCK_LOGS} maxHeight="160px" autoScroll={false} />
      </GlassCard>

    </div>
  );
}
