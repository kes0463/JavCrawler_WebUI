import { GlassCard } from "@/components/ui/GlassCard";
import type { PipelineReport } from "@/api/insight";

interface PipelineReportCardProps {
  report: PipelineReport;
}

export function PipelineReportCard({ report }: PipelineReportCardProps) {
  const byEvent = report.by_event ?? {};
  const harvest = byEvent.harvest_done ?? byEvent.harvest_complete ?? report.harvest_count ?? 0;
  const analysis = byEvent.analysis_done ?? byEvent.analysis_complete ?? report.analysis_count ?? 0;
  const rows = [
    { label: "로그 이벤트", value: report.total_events ?? 0 },
    { label: "수확", value: harvest },
    { label: "분석", value: analysis },
    { label: "오류", value: report.error_events ?? report.error_count ?? 0 },
  ];

  return (
    <GlassCard className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold text-[#d0d0e8]">파이프라인 리포트</h2>
        <p className="text-sm text-muted-foreground">최근 {report.days ?? 30}일</p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {rows.map(({ label, value }) => (
          <div key={label} className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="text-xl font-bold tabular-nums text-white mt-0.5">{value}</p>
          </div>
        ))}
      </div>
      {report.avg_duration_min != null && report.avg_duration_min > 0 && (
        <p className="text-sm text-slate-400">
          평균 처리 시간: {report.avg_duration_min.toFixed(1)}분/편
        </p>
      )}
    </GlassCard>
  );
}
