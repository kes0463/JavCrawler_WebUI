import { CheckCircle, Circle, Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type StageStatus = "idle" | "running" | "done" | "error" | "skip";

export interface Stage {
  id: string;
  label: string;
  status: StageStatus;
  message?: string;
}

interface PipelineStageProps {
  stages: Stage[];
  orientation?: "horizontal" | "vertical";
  className?: string;
}

function StageIcon({ status }: { status: StageStatus }) {
  if (status === "done")    return <CheckCircle className="w-4 h-4 text-emerald-400" />;
  if (status === "running") return <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />;
  if (status === "error")   return <AlertCircle className="w-4 h-4 text-rose-400" />;
  if (status === "skip")    return <Circle className="w-4 h-4 text-zinc-600" />;
  return <Circle className="w-4 h-4 text-zinc-500" />;
}

const STAGE_TEXT: Record<StageStatus, string> = {
  idle:    "text-muted-foreground",
  running: "text-indigo-300",
  done:    "text-emerald-400",
  error:   "text-rose-400",
  skip:    "text-zinc-600",
};

export function PipelineStage({ stages, orientation = "horizontal", className }: PipelineStageProps) {
  if (orientation === "vertical") {
    return (
      <div className={cn("flex flex-col gap-2", className)}>
        {stages.map((stage, i) => (
          <div key={stage.id} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <StageIcon status={stage.status} />
              {i < stages.length - 1 && (
                <div className="w-px flex-1 min-h-[16px] mt-1 bg-white/[0.08]" />
              )}
            </div>
            <div className="pb-2">
              <p className={cn("text-xs font-medium", STAGE_TEXT[stage.status])}>{stage.label}</p>
              {stage.message && (
                <p className="text-[11px] text-muted-foreground mt-0.5">{stage.message}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={cn("flex items-center gap-1", className)}>
      {stages.map((stage, i) => (
        <div key={stage.id} className="flex items-center gap-1 min-w-0">
          <div className="flex flex-col items-center gap-0.5">
            <StageIcon status={stage.status} />
            <span className={cn("text-[9px] text-center whitespace-nowrap", STAGE_TEXT[stage.status])}>
              {stage.label}
            </span>
          </div>
          {i < stages.length - 1 && (
            <div className="w-4 h-px bg-white/[0.08] shrink-0 mb-3.5" />
          )}
        </div>
      ))}
    </div>
  );
}
